"""Գործարկում՝ python test_api.py"""
import os, tempfile
os.environ["ADMIN_PASSWORD"] = "test-pass"
os.environ["AUTOSERVICE_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient

from api import app

c = TestClient(app)

r = c.get("/services", params={"q": "արգելակ"})
assert r.status_code == 200 and len(r.json()) == 1

offers = c.get("/services/2/garages").json()
prices = [o["price"] for o in offers]
assert prices == sorted(prices) and prices[0] == 14000, prices

assert c.get("/garages").json().__len__() == 3
assert c.get("/garages/2").json()["name"] == "Garage Kentron"
assert c.get("/garages/99").status_code == 404
assert c.get("/services/99/garages").status_code == 404
assert c.get("/garages/open").status_code == 200
print("Բոլոր թեստերը անցան ✓")

# ---- Փուլ 3/4. chat (առանց բանալու՝ պարզ ռեժիմ) ----
import os, json
os.environ.pop("ANTHROPIC_API_KEY", None)
r = c.post("/chat", json={"messages": [{"role": "user", "content": "արգելակելիս ճռռոց է լսվում"}]})
assert r.status_code == 200 and r.json()["mode"] == "simple"
assert "Speed Service" in r.json()["reply"] and "14,000" in r.json()["reply"], r.json()
assert c.post("/chat", json={"messages": []}).status_code == 400
assert c.get("/app").status_code == 200

import chat
assert json.loads(chat.run_tool("garages_for_service", {"service_id": 6}))[0]["name"] == "Garage Kentron"
assert "error" in json.loads(chat.run_tool("garage_info", {"garage_id": 99}))
print("Chat-ի թեստերն անցան ✓")

# ---- Փուլ 5. բազա ----
import db, queries
assert db.DB_PATH.exists()
assert queries.set_price(3, 2, 13000) is True
assert queries.set_price(3, 6, 1000) is False          # Speed Service-ը օդորակիչ չունի
assert c.get("/services/2/garages").json()[0]["price"] == 13000   # API-ն տեսնում է փոփոխությունը
assert "13,000" in c.post("/chat", json={"messages": [{"role": "user", "content": "արգելակ ճռռոց"}]}).json()["reply"]
db._ready.clear()                                        # նոր կապ՝ տվյալները մնացել են ֆայլում
assert queries.get_garage(3).services[2].price == 13000
db.reset()
assert queries.get_garage(3).services[2].price == 14000  # reset-ը վերադարձնում է սկզբնականը
print("Բազայի թեստերն անցան ✓")


# ---- Փուլ 6. ադմին ----
assert c.get("/admin/data").status_code == 401                       # առանց token-ի՝ փակ է
assert c.post("/admin/login", json={"password": "wrong"}).status_code == 401
tok = c.post("/admin/login", json={"password": "test-pass"}).json()["token"]
H = {"Authorization": "Bearer " + tok}
assert c.get("/admin/data", headers={"Authorization": "Bearer x.y"}).status_code == 401
data = c.get("/admin/data", headers=H).json()
assert len(data["garages"]) == 3 and len(data["services"]) == 6

gid = c.post("/admin/garages", headers=H, json={"name": "Նոր գարաժ", "address": "Ա 1", "phone": "+374 10 999999"}).json()["id"]
sid = c.post("/admin/services", headers=H, json={"name": "Լուսարձակների փայլեցում", "category": "Դետեյլինգ", "keywords": ["լուսարձակ", " փայլ "]}).json()["id"]
assert c.put(f"/admin/garages/{gid}/services/{sid}", headers=H, json={"price": 7000, "duration_min": 45}).status_code == 200
assert c.put(f"/admin/garages/{gid}/services/{sid}", headers=H, json={"price": -5, "duration_min": 45}).status_code == 422
assert c.put(f"/admin/garages/999/services/{sid}", headers=H, json={"price": 1, "duration_min": 5}).status_code == 404
assert c.get(f"/services/{sid}/garages").json()[0]["price"] == 7000        # հանրային API-ն տեսնում է
assert "7,000" in c.post("/chat", json={"messages": [{"role": "user", "content": "լուսարձակները մթագնել են"}]}).json()["reply"]  # keyword-ը աշխատում է

good = {"days": [{"weekday": 0, "open": "08:00", "close": "17:00"}, {"weekday": 6, "open": "10:00", "close": "14:00"}]}
assert c.put(f"/admin/garages/{gid}/hours", headers=H, json=good).status_code == 200
g = next(x for x in c.get("/admin/data", headers=H).json()["garages"] if x["id"] == gid)
assert [h["weekday"] for h in g["hours"]] == [0, 6]
assert c.put(f"/admin/garages/{gid}/hours", headers=H, json={"days": [{"weekday": 0, "open": "18:00", "close": "09:00"}]}).status_code == 422
assert c.put(f"/admin/garages/{gid}/hours", headers=H, json={"days": [{"weekday": 0, "open": "9:00", "close": "18:00"}]}).status_code == 422

assert c.put(f"/admin/garages/{gid}", headers=H, json={"name": "Վերանվանված", "address": "", "phone": ""}).status_code == 200
assert c.delete(f"/admin/garages/{gid}/services/{sid}", headers=H).status_code == 200
assert c.delete(f"/admin/garages/{gid}", headers=H).status_code == 200
assert c.delete(f"/admin/garages/{gid}", headers=H).status_code == 404
assert c.delete(f"/admin/services/{sid}", headers=H).status_code == 200
assert c.get("/panel").status_code == 200
print("Ադմինի թեստերն անցան ✓")

# ---- Փուլ 7. հայտեր ----
r = c.post("/requests", json={"name": "Արամ", "phone": "+374 91 123456", "garage_id": 1, "service_id": 2, "message": "Վաղը առավոտյան"})
assert r.status_code == 201
assert c.post("/requests", json={"name": "X", "phone": "abc"}).status_code == 422          # անվավեր հեռախոս
assert c.post("/requests", json={"name": "X", "phone": "123456", "garage_id": 999}).status_code == 400
reqs = c.get("/admin/data", headers=H).json()["requests"]
assert reqs[0]["name"] == "Արամ" and reqs[0]["garage"] == "AutoPro Երևան" and reqs[0]["status"] == "new"
assert c.patch(f"/admin/requests/{reqs[0]['id']}", headers=H, json={"status": "done"}).status_code == 200
assert c.patch(f"/admin/requests/{reqs[0]['id']}", headers=H, json={"status": "bad"}).status_code == 422
assert c.get("/admin/data", headers=H).json()["requests"][0]["status"] == "done"
c.delete("/admin/garages/1", headers=H)                                                     # գարաժ ջնջելիս հայտը մնում է
assert c.get("/admin/data", headers=H).json()["requests"][0]["garage"] is None
print("Հայտերի թեստերն անցան ✓")

# ---- Rate limit ----
import auth
for _ in range(12):
    last = c.post("/admin/login", json={"password": "wrong"})
assert last.status_code == 429
print("Rate limit-ը աշխատում է ✓")
