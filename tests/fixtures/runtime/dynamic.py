import os
import xmlrpc.client

url = os.environ["ODOO_URL"]
common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/{svc}")
obj = "%s/xmlrpc/2/%s" % (url, "object")
ep = url + "/xmlrpc/2/" + service
models.execute(db, uid, pw, "res.partner", "read", ids)
cur.execute(query, params)
cur.execute("SELECT a, b, c, d FROM t WHERE x = %s", (x,))
