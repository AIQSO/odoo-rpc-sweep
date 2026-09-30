# odoo-rpc-sweep

Find the code that still calls Odoo through XML-RPC or JSON-RPC, before Odoo removes those APIs.

```bash
pipx run odoo-rpc-sweep ./my-integrations          # Markdown report
odoo-rpc-sweep ./my-integrations --format csv > sweep.csv
odoo-rpc-sweep workflow-export.json                 # a single n8n export
```

Until the first PyPI release, install from GitHub: `pipx install git+https://github.com/AIQSO/odoo-rpc-sweep`.

No dependencies. Python 3.9+. It reads files and prints a report. Nothing is sent anywhere.

## Why

From Odoo's own documentation:

- `/xmlrpc`, `/xmlrpc/2` and `/jsonrpc` are **deprecated in Odoo 19**.
- The **`db` service** (create, duplicate, drop or list databases) is **removed in Odoo 20** (fall 2026) and in Odoo Online 19.1.
- The `common` and `object` services are **scheduled for removal in Odoo 22** (fall 2028) and Odoo Online 21.1 (winter 2027).
- The replacement is **JSON-2**: `POST /json/2/<model>/<method>`, an API key as a bearer token, named arguments only, one transaction per request.

Sources: [Odoo 19.0 External API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html#migrating-from-xml-rpc-json-rpc) ·
[Odoo 20.0 External API](https://www.odoo.com/documentation/20.0/developer/reference/external_api.html#migrating-from-xml-rpc-json-rpc)

**So not everything breaks on Odoo 20.** Only database-management calls do. The rest keeps working, with deprecation warnings, until Odoo 22. This tool tells you which is which.

## What it reports

| Severity | Meaning |
|---|---|
| `BREAKS-ON-20` | `db`-service calls: `/xmlrpc/2/db`, `"service": "db"`, `create_database`, `duplicate_database`, `db_exist`, `change_admin_password` |
| `REMOVED-IN-22` | `/xmlrpc/2/common`, `/xmlrpc/2/object`, `/jsonrpc`, `execute_kw`, the `odoorpc` / `erppeek` / `odoo-xmlrpc` / `ripcord` client libraries, and n8n Odoo nodes that still use JSON-RPC |
| `CHECK` | Likely legacy but needs a person to look: an XML-RPC client import, or an n8n Odoo node that can't be classified |

It reads `.py .js .mjs .cjs .ts .php .rb .java .cs .go .sh .json .yml .yaml`. It skips `.git`, `node_modules`, virtualenvs, build output and tool caches, and any file over 2 MB (listed as "not read").

**n8n:** workflow exports are parsed, not just searched. The Odoo node's v2 uses JSON-2 when it's set up with the API-key credential,
and `/jsonrpc` with the older username/password credential. v1 always uses `/jsonrpc`. So a v2 node on an API-key credential is reported as clean
([n8n source](https://github.com/n8n-io/n8n/tree/master/packages/nodes-base/nodes/Odoo)).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Nothing found |
| `1` | Legacy calls found |
| `3` | Couldn't tell: the path doesn't exist, it held no readable files, or files were skipped and nothing was found |

`3` is never reported as clean, so it's safe to use as a CI gate:

```yaml
- run: pipx run odoo-rpc-sweep .   # fails the build while legacy calls remain
```

## Limits (read these)

- It's a **pattern match**. It finds candidates, and a person confirms each one. A URL built from pieces (`base + "/xml" + "rpc"`) can slip past it.
- It only sees the code you point it at. For the calls actually hitting your Odoo, including ones from code you don't have, install the free
  [RPC Migration Scanner](https://apps.odoo.com/apps/modules/19.0/aiq_rpc_scanner) module on Odoo 19. It records every legacy caller by user, API key and method.
  Store modules can't be installed on Odoo Online, and that's where this tool comes in.
- Third-party connectors (Zapier, Make, a vendor's packaged app) have to be migrated by their vendors.

## Help with the migration

Built and maintained by [AIQSO](https://aiqso.io), which offers fixed-price Odoo API migrations. Questions and bugs: [GitHub issues](https://github.com/AIQSO/odoo-rpc-sweep/issues), or `odoo-apps@aiqso.io`.

## License

MIT
