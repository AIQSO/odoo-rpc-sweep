import requests
r = requests.post("https://erp.example.com/json/2/res.partner/search_read",
                  headers={"Authorization": f"bearer {key}"}, json={"domain": [], "limit": 5})
