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


class Sweep(unittest.TestCase):
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
