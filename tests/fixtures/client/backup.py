import xmlrpc.client
dbs = xmlrpc.client.ServerProxy("https://erp.example.com/xmlrpc/2/db")
dbs.duplicate_database(master, "prod", "prod-copy")
