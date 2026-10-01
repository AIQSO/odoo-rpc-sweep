import io
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)
from odoo_rpc_sweep import sweep  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def run(*args):
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.run([sys.executable, "-m", "odoo_rpc_sweep", *args], capture_output=True, text=True, env=env)


class ScanLine(unittest.TestCase):
    def test_db_wins_over_generic(self):
        self.assertEqual(sweep.scan_line('ServerProxy(url + "/xmlrpc/2/db")')[0], "BREAKS-ON-20")

    def test_jsonrpc_db_service(self):
        self.assertEqual(sweep.scan_line('{"service": "db", "method": "list"}')[0], "BREAKS-ON-20")

    def test_object_endpoint(self):
        self.assertEqual(sweep.scan_line('"/xmlrpc/2/object"')[0], "REMOVED-IN-22")

    def test_json2_is_clean(self):
        self.assertIsNone(sweep.scan_line('post(url + "/json/2/res.partner/read")'))

    def test_jsonrpc_word_boundary(self):
        self.assertIsNone(sweep.scan_line('"/jsonrpcx"'))
        self.assertEqual(sweep.scan_line('"/jsonrpc"')[0], "REMOVED-IN-22")


    def test_runtime_service_is_check(self):
        for line in ('ServerProxy(f"{url}/xmlrpc/2/{svc}")', '"%s/xmlrpc/2/%s" % (url, svc)',
                     'url + "/xmlrpc/2/" + service', "path: `/xmlrpc/2/${service}`", "ODOO_RPC_PATH=/xmlrpc/2",
                     "ODOO_RPC_PATH=/xmlrpc/2/$SERVICE", '"#{url}/xmlrpc/2/#{service}"',
                     "ODOO_RPC_PATH=/xmlrpc/2 # service appended at runtime", "endpoint=/xmlrpc/2 ; legacy"):
            self.assertEqual(sweep.scan_line(line), ("CHECK", "XML-RPC endpoint, service set at runtime (could be db)"), line)

    def test_definitive_rule_beats_runtime_check(self):
        line = 'models = ServerProxy(f"{url}/xmlrpc/2/{service}"); models.execute_kw(db, uid, pw, "res.partner", "read", [ids])'
        self.assertEqual(sweep.scan_line(line), ("REMOVED-IN-22", "execute_kw call"))
        self.assertEqual(sweep.scan_line('odoorpc.ODOO(host); path = base + "/xmlrpc/2/" + svc')[0], "REMOVED-IN-22")

    def test_literal_db_still_breaks(self):
        self.assertEqual(sweep.scan_line('url + "/xmlrpc/2/db"')[0], "BREAKS-ON-20")

    def test_legacy_execute_not_sql(self):
        self.assertEqual(sweep.scan_line('models.execute(db, uid, pw, "res.partner", "read", ids)')[0], "CHECK")
        self.assertIsNone(sweep.scan_line("cur.execute(query, params)"))
        self.assertIsNone(sweep.scan_line('cur.execute("SELECT a, b, c, d FROM t WHERE x = %s", (x,))'))
        for line in ('models.execute(config["db"], uid, get_password(), "res.partner", "read")',
                     'models.execute("prod", 2, pw, "sale.order", "search", [])',
                     'models.execute(db, uid, pw, "res.partner",',
                     r'models.execute("prod", uid, "p\"w", "res.partner", "read")',
                     r"models.execute('prod', uid, 'it\'s', 'res.partner', 'read')",
                     '$models->execute($db, $uid, $password, "res.partner", "read")'):
            self.assertEqual(sweep.scan_line(line), ("CHECK", "execute() call (legacy object service)"), line)
        self.assertIsNone(sweep.scan_line('cur.execute(sql, (a, b, c, d, e))'))
        self.assertIsNone(sweep.scan_line("cur.execute(f\"INSERT INTO t VALUES ({a}, {b}, {c}, {d}, {e})\")"))

    def test_js_xmlrpc_client(self):
        self.assertEqual(sweep.scan_line("xmlrpc.createClient({ host, path })")[0], "CHECK")
        self.assertEqual(sweep.scan_line('const rpc = require("xmlrpc");')[0], "CHECK")
        self.assertEqual(sweep.scan_line("import rpc from 'xmlrpc';")[0], "CHECK")
        self.assertIsNone(sweep.scan_line('const x = require("xmlrpc-lite-thing");'))

    def test_redact_userinfo(self):
        self.assertEqual(sweep.redact("https://sync:hunter2@erp.example.com/jsonrpc"), "https://***@erp.example.com/jsonrpc")
        self.assertEqual(sweep.redact(r"https:\/\/sync:hunter2@erp.example.com\/jsonrpc"), r"https:\/\/***@erp.example.com\/jsonrpc")
        self.assertEqual(sweep.redact("see https://erp.example.com/jsonrpc"), "see https://erp.example.com/jsonrpc")
        self.assertEqual(sweep.redact("fetch('//sync:hunter2@erp.example.com/jsonrpc')"), "fetch('//***@erp.example.com/jsonrpc')")


class Sweep(unittest.TestCase):
    def test_config_fixture(self):
        """Endpoints that live in env/config/deploy files, not in code (silent 0 before 0.1.1)."""
        hits, skipped, scanned = sweep.sweep(os.path.join(FIX, "config"))
        by_file = {h["file"]: h for h in hits}
        self.assertEqual(set(by_file), {".env", ".env.example", "settings.ini", "config.toml", "app.properties", "Dockerfile"})
        self.assertEqual(by_file[".env"]["severity"], "BREAKS-ON-20")
        self.assertNotIn("hunter2", by_file["settings.ini"]["text"])
        self.assertEqual(scanned, 7)  # deploy/clean.toml is read too
        self.assertEqual(run(os.path.join(FIX, "config", ".env")).returncode, 1)

    def test_execute_split_over_lines(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "multi.py"), "w") as fh:
                fh.write('ids = models.execute(\n    db,\n    uid,\n    password,\n    "res.partner",\n    "search",\n    [],\n)\n'
                         'cur.execute(\n    """\n    SELECT a, b, c, d, e FROM t\n    """,\n    (x,),\n)\n'
                         'cur.execute(\n    query,\n    params,\n)\nlater(a, b, c, d, e)\n'
                         'odoo.execute("res.partner", "write", [1])\n'
                         'odoo.execute(db, uid, pw, "res.partner", "read")\n')
            hits, _, _ = sweep.sweep(d)
            self.assertEqual([(h["line"], h["rule"]) for h in hits], [(1, "execute() call (legacy object service)"), (21, "execute() call (legacy object service)")])

    def test_runtime_fixture(self):
        hits, _, _ = sweep.sweep(os.path.join(FIX, "runtime"))
        lines = {(h["file"], h["line"]) for h in hits}
        for want in [("dynamic.py", 5), ("dynamic.py", 6), ("dynamic.py", 7), ("dynamic.py", 8),
                     ("client.js", 2), ("client.js", 3)]:
            self.assertIn(want, lines)
        self.assertNotIn(("dynamic.py", 9), lines)
        self.assertNotIn(("dynamic.py", 10), lines)

    def test_client_fixture(self):
        hits, skipped, scanned = sweep.sweep(os.path.join(FIX, "client"))
        files = {h["file"] for h in hits}
        self.assertEqual(files, {"sync.py", "backup.py", "push.js", "workflow.json"})
        self.assertFalse(any("node_modules" in f or ".mypy_cache" in f for f in files))
        sev = {(h["file"], h["severity"]) for h in hits}
        self.assertIn(("backup.py", "BREAKS-ON-20"), sev)
        self.assertIn(("workflow.json", "REMOVED-IN-22"), sev)

    def test_exit_codes(self):
        self.assertEqual(run(os.path.join(FIX, "client")).returncode, 1)
        self.assertEqual(run(os.path.join(FIX, "clean")).returncode, 0)
        self.assertEqual(run(os.path.join(FIX, "nope")).returncode, 3)
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(run(empty).returncode, 3)

    def test_formats(self):
        for fmt in ("md", "csv", "json"):
            r = run(os.path.join(FIX, "client"), "--format", fmt)
            self.assertIn("backup.py", r.stdout, fmt)
        self.assertIn("## By file (4)", run(os.path.join(FIX, "client")).stdout)


class N8n(unittest.TestCase):
    def test_node_versions_and_credentials(self):
        hits, _, _ = sweep.sweep(os.path.join(FIX, "n8n"))
        by_file = {}
        for h in hits:
            by_file.setdefault(h["file"], []).append(h["severity"])
        self.assertNotIn("v2_apikey.json", by_file)  # JSON-2: clean
        self.assertEqual(by_file["v2_password.json"], ["REMOVED-IN-22"])
        self.assertEqual(by_file["v1.json"], ["REMOVED-IN-22"])
        self.assertEqual(by_file["v2_nocreds.json"], ["CHECK"])
        self.assertEqual(sorted(by_file["mixed.json"]), ["REMOVED-IN-22"])  # 1 legacy + 1 JSON-2 node

    def test_json2_workflow_exits_clean(self):
        self.assertEqual(run(os.path.join(FIX, "n8n", "v2_apikey.json")).returncode, 0)


if __name__ == "__main__":
    unittest.main()
