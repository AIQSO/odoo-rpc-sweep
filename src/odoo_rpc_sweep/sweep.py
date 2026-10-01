"""Find legacy Odoo external-API calls (XML-RPC / JSON-RPC) in a source tree.

Odoo deprecated /xmlrpc, /xmlrpc/2 and /jsonrpc in version 19. This sweep reads
the code that calls Odoo (scripts, services, n8n exports) and lists every call
that has to move to JSON-2. It is a pattern match: every hit is a candidate a
person confirms.

Severity (Odoo external API docs, 19.0 and 20.0):
  BREAKS-ON-20   db-service call: removed in Odoo 20 / Online 19.1
  REMOVED-IN-22  common/object call: removed in Odoo 22 / Online 21.1
  CHECK          likely legacy, confirm by reading the code

Exit: 0 no hits, 1 hits found, 3 input unreadable (UNKNOWN, never a silent 0).
"""
import argparse
import csv
import json
import os
import re
import sys

from . import __version__

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".tox", "site-packages",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", ".next", "coverage", "htmlcov"}
EXTS = {".py", ".js", ".mjs", ".cjs", ".ts", ".php", ".rb", ".java", ".cs", ".go", ".sh", ".json", ".yml", ".yaml",
        # Config and deploy files: an endpoint often lives here, not in the code that uses it.
        ".env", ".ini", ".cfg", ".conf", ".toml", ".properties", ".tf", ".tfvars"}
# Files without a useful extension: .env, .env.local, .env.example, Dockerfile, Dockerfile.prod, Containerfile.
NAME_PREFIXES = (".env", "Dockerfile", "Containerfile")
MAX_BYTES = 2 * 1024 * 1024

N8N_RULE = "n8n Odoo node"

class ExecuteCall:
    """Matches .execute( with 5+ top-level arguments: execute(db, uid, password, model, method, ...).

    Counting arguments instead of matching their shape catches config["db"] or get_password(),
    while SQL cursor.execute(query, params) never has more than 2. sweep() passes a call that is
    split over several lines as one joined string (see EXECUTE_SPAN).
    """
    START = re.compile(r"\.execute\(")

    def search(self, line, starts_before=None):
        for m in self.START.finditer(line):
            if starts_before is not None and m.start() >= starts_before:
                break  # a later call in the joined text: it is reported on its own line
            depth, quote, commas, escaped = 0, None, 0, False
            for ch in line[m.end():]:
                if quote:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == quote:
                        quote = None
                elif ch in "\"'":
                    quote = ch
                elif ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                elif ch == "," and depth == 0:
                    commas += 1
            if commas >= 4:
                return m
        return None


EXECUTE = ExecuteCall()
EXECUTE_RULE = ("CHECK", "execute() call (legacy object service)")
EXECUTE_SPAN = 20  # lines joined when an .execute( call is not closed on its first line


# Order matters: the first rule that matches a line wins, so db rules come first.
RULES = [
    ("BREAKS-ON-20", "db service endpoint", re.compile(r"/xmlrpc(?:/2)?/db\b")),
    ("BREAKS-ON-20", "db service (JSON-RPC)", re.compile(r"""["']service["']\s*:\s*["']db["']""")),
    ("BREAKS-ON-20", "db service method", re.compile(r"\b(?:create_database|duplicate_database|db_exist|change_admin_password)\b")),
    ("REMOVED-IN-22", "XML-RPC endpoint", re.compile(r"/xmlrpc(?:/2)?/(?:common|object)\b")),
    ("REMOVED-IN-22", "JSON-RPC endpoint", re.compile(r"/jsonrpc\b")),
    # /xmlrpc or /xmlrpc/2 followed by a quote, a template/format placeholder or a concatenation:
    # the service is chosen at runtime, so it may be db and break on 20.
    ("CHECK", "XML-RPC endpoint, service set at runtime (could be db)",
     re.compile(r"""/xmlrpc(?:/2)?/?(?=["'`]|\$[\w{]|#\{|\{|%s|%\(|\s*\+|\s*$)""")),
    ("REMOVED-IN-22", "execute_kw call", re.compile(r"\bexecute_kw\b")),
    # The older positional object call: execute(db, uid, password, model, method, ...).
    (*EXECUTE_RULE, EXECUTE),
    ("REMOVED-IN-22", "legacy client library", re.compile(r"\b(?:odoorpc|OdooRPC|erppeek|odoo-xmlrpc|ripcord)\b")),
    ("CHECK", N8N_RULE, re.compile(r'"n8n-nodes-base\.odoo"')),
    ("CHECK", "XML-RPC client", re.compile(r"""\b(?:xmlrpc\.client|xmlrpclib|ServerProxy|xmlrpc_encode_request|xmlrpc\.create(?:Secure)?Client)\b"""
                r"""|\brequire\(\s*["']xmlrpc["']\s*\)|\bfrom\s+["']xmlrpc["']""")),
]


# Plain, scheme-relative (//user:pass@host) and JSON slash-escaped (https:\/\/user:pass@host) URLs.
USERINFO = re.compile(r"((?:\\?/){2})[^/\\\s@'\"]+@")


def redact(text):
    """Mask user:password@ in URLs: config files are now read, and reports get shared."""
    return USERINFO.sub(r"\1***@", text)


def scan_line(line):
    for severity, label, rx in RULES:
        if rx.search(line):
            return severity, label
    return None


def n8n_verdicts(text):
    """Per n8n Odoo node, in document order: (severity, label), or None when it uses JSON-2.

    n8n's Odoo node v2 calls /json/2 when its credential is the API-key type
    (odooApiKeyApi) and /jsonrpc with the older username/password credential
    (odooApi). Node v1 always calls /jsonrpc.
    """
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    out = []

    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("type") == "n8n-nodes-base.odoo":
                creds = obj.get("credentials") or {}
                version = obj.get("typeVersion", 1)
                if "odooApiKeyApi" in creds and version >= 2:
                    out.append(None)
                elif "odooApi" in creds or version < 2:
                    out.append(("REMOVED-IN-22", "n8n Odoo node on JSON-RPC (v1 or odooApi credential)"))
                else:
                    out.append(("CHECK", "n8n Odoo node v2: JSON-2 only with an API-key credential"))
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(doc)
    return out


def iter_files(root):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() in EXTS or name.startswith(NAME_PREFIXES):
                yield os.path.join(dirpath, name)


def sweep(root):
    hits, skipped, scanned = [], [], 0
    for path in iter_files(root):
        try:
            if os.path.getsize(path) > MAX_BYTES:
                skipped.append(path)
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            scanned += 1
            n8n = n8n_verdicts(text) if path.endswith(".json") and "n8n-nodes-base.odoo" in text else None
            lines = text.splitlines()
            for lineno, line in enumerate(lines, 1):
                found = scan_line(line)
                if not found and ".execute(" in line and EXECUTE.search(" ".join(lines[lineno - 1:lineno - 1 + EXECUTE_SPAN]), len(line)):
                    found = EXECUTE_RULE
                if found and found[1] == N8N_RULE:
                    if n8n:
                        found = n8n.pop(0)
                    elif n8n is not None:
                        found = ("CHECK", "n8n Odoo node (could not match to a parsed node)")
                    else:
                        found = ("CHECK", "n8n Odoo node reference")
                if found:
                    hits.append({
                        "file": os.path.relpath(path, root) if os.path.isdir(root) else path,
                        "line": lineno,
                        "severity": found[0],
                        "rule": found[1],
                        "text": redact(line.strip())[:160],
                    })
        except OSError:
            skipped.append(path)
    return hits, skipped, scanned


def render(hits, skipped, fmt, out):
    if fmt == "json":
        json.dump({"hits": hits, "skipped": skipped}, out, indent=2)
        out.write("\n")
    elif fmt == "csv":
        w = csv.DictWriter(out, fieldnames=["severity", "rule", "file", "line", "text"])
        w.writeheader()
        for h in hits:
            w.writerow({k: h[k] for k in w.fieldnames})
    else:
        counts = {s: sum(h["severity"] == s for h in hits) for s in ("BREAKS-ON-20", "REMOVED-IN-22", "CHECK")}
        out.write("# Legacy Odoo RPC sweep\n\n")
        out.write("| Severity | Hits |\n|---|---|\n")
        for s, n in counts.items():
            out.write(f"| {s} | {n} |\n")
        by_file = {}
        for h in hits:
            by_file.setdefault(h["file"], {"BREAKS-ON-20": 0, "REMOVED-IN-22": 0, "CHECK": 0})[h["severity"]] += 1
        out.write(f"\n## By file ({len(by_file)})\n\n| File | BREAKS-ON-20 | REMOVED-IN-22 | CHECK |\n|---|---|---|---|\n")
        for f, c in sorted(by_file.items(), key=lambda kv: (-kv[1]["BREAKS-ON-20"], -sum(kv[1].values()), kv[0])):
            out.write(f"| `{f}` | {c['BREAKS-ON-20']} | {c['REMOVED-IN-22']} | {c['CHECK']} |\n")
        out.write("\n## Every hit\n\n| Severity | Rule | Location | Line |\n|---|---|---|---|\n")
        rank = {"BREAKS-ON-20": 0, "REMOVED-IN-22": 1, "CHECK": 2}
        for h in sorted(hits, key=lambda h: (rank[h["severity"]], h["file"], h["line"])):
            text = h["text"].replace("|", "\\|").replace("`", "'")
            out.write(f"| {h['severity']} | {h['rule']} | `{h['file']}:{h['line']}` | `{text}` |\n")
        if skipped:
            out.write(f"\n**Not read ({len(skipped)}):** " + ", ".join(f"`{p}`" for p in skipped) + "\n")
        out.write(f"\n---\nodoo-rpc-sweep {__version__}. A pattern match: confirm each hit by reading the code. "
                  "Migration help: https://aiqso.io\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="odoo-rpc-sweep", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("path", help="source tree or single file (e.g. an n8n workflow export)")
    ap.add_argument("--format", choices=["md", "csv", "json"], default="md")
    args = ap.parse_args(argv)
    if not os.path.exists(args.path):
        print(f"UNKNOWN: {args.path} does not exist", file=sys.stderr)
        return 3
    hits, skipped, scanned = sweep(args.path)
    if not hits and (skipped or not scanned):
        # Nothing found, but input went unread or there was nothing to read: not a clean result.
        print(f"UNKNOWN: {scanned} file(s) read, {len(skipped)} skipped", file=sys.stderr)
        render(hits, skipped, args.format, sys.stdout)
        return 3
    render(hits, skipped, args.format, sys.stdout)
    return 1 if hits else 0
