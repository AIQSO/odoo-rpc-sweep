import xmlrpc.client
url = "https://erp.example.com"
common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
rows = models.execute_kw(db, uid, key, "res.partner", "search_read", [[]], {"limit": 5})
