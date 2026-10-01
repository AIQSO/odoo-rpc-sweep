# Changelog

## 0.1.1 (2026-10-01)

- Reads config and deploy files: `.env` / `.env.*`, `.ini`, `.cfg`, `.conf`, `.toml`, `.properties`, `.tf`, `.tfvars`, `Dockerfile*`, `Containerfile*`.
  Before this, a repo whose only legacy endpoint sat in `.env` (for example `ODOO_DB_PATH=/xmlrpc/2/db`) got exit 0.
- New `CHECK` rule: an `/xmlrpc` or `/xmlrpc/2` endpoint whose service is set at runtime (f-strings, `%` formatting, concatenation, JS template strings).
  The service may be `db`, so it may break on Odoo 20.
- New `CHECK` rule: the old positional `execute(db, uid, password, model, method, ...)` call. SQL `cursor.execute(query, params)` is not matched.
- The JS `xmlrpc` package (`xmlrpc.createClient` / `createSecureClient`) is reported as an XML-RPC client.
- `user:password@` in URLs is masked in the report.

## 0.1.0 (2026-09-30)

- First release: sweeps Python, JS/TS, PHP, Ruby, Java, C#, Go, shell, YAML and n8n workflow exports for legacy Odoo RPC calls.
- Output as Markdown (with a per-file summary), CSV or JSON. Exit codes 0 / 1 / 3.
