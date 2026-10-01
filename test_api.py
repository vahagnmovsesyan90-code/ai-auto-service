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


# =====================================================================
# Գարաժների դերեր. յուրաքանչյուրը տեսնում է միայն իր հայտերը և գործում է միայն իր գարաժի հետ
# =====================================================================
import auth, db, telegram
auth.login_limiter.hits.clear()
auth.request_limiter.limit = 1000
H = {"Authorization": "Bearer " + c.post("/admin/login", json={"password": "test-pass"}).json()["token"]}

# մուտքի ստեղծում (միայն գլխավոր ադմին)
assert c.put("/admin/garages/2/account", headers=H, json={"login": "Kentron", "password": "kentron-pass"}).status_code == 200
assert c.put("/admin/garages/3/account", headers=H, json={"login": "speed", "password": "speed-pass-1"}).status_code == 200
assert c.put("/admin/garages/3/account", headers=H, json={"login": "kentron", "password": "another-pass"}).status_code == 409   # մուտքանունը զբաղված է
assert c.put("/admin/garages/3/account", headers=H, json={"login": "speed", "password": "short"}).status_code == 422          # կարճ գաղտնաբառ
assert c.put("/admin/garages/3/account", headers=H, json={"login": "ADMIN", "password": "long-enough-1"}).status_code == 422   # վերապահված
assert c.put("/admin/garages/3/account", headers=H, json={"login": "a b", "password": "long-enough-1"}).status_code == 422     # անթույլատրելի նիշ
assert c.put("/admin/garages/999/account", headers=H, json={"login": "nobody", "password": "long-enough-1"}).status_code == 404
with db.connect() as cn:
    stored = cn.execute("SELECT password_hash FROM garages WHERE id=2").fetchone()[0]
assert stored.startswith("pbkdf2$") and "kentron-pass" not in stored                                                          # գաղտնաբառը հեշավորված է

# մուտք
assert c.post("/admin/login", json={"login": "kentron", "password": "wrong"}).status_code == 401
assert c.post("/admin/login", json={"login": "nobody", "password": "kentron-pass"}).status_code == 401
assert c.post("/admin/login", json={"login": "kentron", "password": "test-pass"}).status_code == 401        # ադմինի գաղտնաբառը գարաժի մուտքին չի ենթարկվում
rk = c.post("/admin/login", json={"login": "KENTRON", "password": "kentron-pass"}).json()                   # մեծատառը ընդունվում է
assert rk["role"] == "garage"
HK = {"Authorization": "Bearer " + rk["token"]}
HS = {"Authorization": "Bearer " + c.post("/admin/login", json={"login": "speed", "password": "speed-pass-1"}).json()["token"]}

# հայտեր երեք գարաժների համար + առանց գարաժի
def new_req(name, garage_id=None):
    body = {"name": name, "phone": "+374 91 000000", "message": "թեստ"}
    if garage_id:
        body["garage_id"] = garage_id
    r = c.post("/requests", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]
r2, r3, r0 = new_req("ԱրամK", 2), new_req("ԱնիS", 3), new_req("ՎարդանԱռանց")

dk, ds, da = (c.get("/admin/data", headers=x).json() for x in (HK, HS, H))
assert dk["role"] == "garage" and [g["id"] for g in dk["garages"]] == [2]
names = lambda d: {r["name"] for r in d["requests"]}
assert "ԱրամK" in names(dk) and "ԱնիS" not in names(dk) and "ՎարդանԱռանց" not in names(dk)
assert "ԱնիS" in names(ds) and "ԱրամK" not in names(ds)
assert {"ԱրամK", "ԱնիS", "ՎարդանԱռանց"} <= names(da) and len(da["garages"]) >= 2
assert all(r["garage_id"] == 2 for r in dk["requests"])
assert all("login" in g for g in dk["garages"]) and "password_hash" not in str(dk)                          # հեշը երբեք չի ուղարկվում

# այլ գարաժին դիպչելը արգելված է
assert c.put("/admin/garages/3", headers=HK, json={"name": "Հաքեր"}).status_code == 403
assert c.put("/admin/garages/3/services/1", headers=HK, json={"price": 1, "duration_min": 5}).status_code == 403
assert c.delete("/admin/garages/3/services/1", headers=HK).status_code == 403
assert c.put("/admin/garages/3/hours", headers=HK, json={"days": []}).status_code == 403
assert c.post("/admin/garages/3/telegram/link", headers=HK).status_code == 403
assert c.delete("/admin/garages/3/telegram", headers=HK).status_code == 403
# գլխավոր ադմինի գործողությունները փակ են գարաժի համար
assert c.delete("/admin/garages/2", headers=HK).status_code == 403
assert c.post("/admin/garages", headers=HK, json={"name": "X"}).status_code == 403
assert c.post("/admin/services", headers=HK, json={"name": "X"}).status_code == 403
assert c.delete("/admin/services/1", headers=HK).status_code == 403
assert c.put("/admin/garages/2/account", headers=HK, json={"login": "evil", "password": "evil-pass-1"}).status_code == 403
assert c.put(f"/admin/requests/{r0}/garage", headers=HK, json={"garage_id": 2}).status_code == 403
assert c.post("/admin/telegram/link", headers=HK).status_code == 403
# այլ գարաժի հայտը «գոյություն չունի»
assert c.patch(f"/admin/requests/{r3}", headers=HK, json={"status": "done"}).status_code == 404
assert c.patch(f"/admin/requests/{r0}", headers=HK, json={"status": "done"}).status_code == 404
assert next(r for r in c.get("/admin/data", headers=H).json()["requests"] if r["id"] == r3)["status"] == "new"   # չի փոխվել
# սեփականը՝ թույլատրված
assert c.patch(f"/admin/requests/{r2}", headers=HK, json={"status": "done"}).status_code == 200
assert c.put("/admin/garages/2", headers=HK, json={"name": "Kentron Plus", "address": "Նոր 1", "phone": "+374 10 777777"}).status_code == 200
assert c.put("/admin/garages/2/services/1", headers=HK, json={"price": 6500, "duration_min": 40}).status_code == 200
assert c.get("/garages/2").json()["name"] == "Kentron Plus"
assert next(o for o in c.get("/services/1/garages").json() if o["garage"]["id"] == 2)["price"] == 6500
# կեղծված token (գարաժի id-ն փոխած) չի անցնում
assert c.get("/admin/data", headers={"Authorization": "Bearer " + rk["token"].replace("g:2:", "g:3:", 1)}).status_code == 401

# ադմինը հայտը նշանակում է գարաժի
assert c.put(f"/admin/requests/{r0}/garage", headers=H, json={"garage_id": 3}).status_code == 200
assert "ՎարդանԱռանց" in names(c.get("/admin/data", headers=HS).json())
assert "ՎարդանԱռանց" not in names(c.get("/admin/data", headers=HK).json())
assert c.put(f"/admin/requests/{r0}/garage", headers=H, json={"garage_id": 999}).status_code == 400
assert c.put("/admin/requests/99999/garage", headers=H, json={"garage_id": 3}).status_code == 404
assert c.put(f"/admin/requests/{r0}/garage", headers=H, json={"garage_id": None}).status_code == 200
assert "ՎարդանԱռանց" not in names(c.get("/admin/data", headers=HS).json())
print("Գարաժների դերերի թեստերն անցան ✓")

# =====================================================================
# Telegram (կեղծ Telegram API-ով, իրական բոտ պետք չէ)
# =====================================================================
assert c.post("/admin/garages/2/telegram/link", headers=HK).status_code == 400      # առանց TELEGRAM_BOT_TOKEN-ի
assert c.post("/telegram/webhook", json={}).status_code == 403
os.environ["TELEGRAM_BOT_TOKEN"] = "123:abc"
telegram.SYNC = True
telegram.BOT_USERNAME = None
sent = []
def fake_call(method, payload):
    sent.append((method, payload))
    return {"ok": True, "result": {"username": "autoservice_test_bot"}}
telegram._call = fake_call
SEC = {"X-Telegram-Bot-Api-Secret-Token": telegram.webhook_secret()}
def tg(chat, text):
    return c.post("/telegram/webhook", headers=SEC, json={"message": {"chat": {"id": chat}, "text": text}})
def msgs(): return [(p["chat_id"], p["text"]) for m, p in sent if m == "sendMessage"]

assert c.get("/admin/data", headers=HK).json()["telegram"]["enabled"] is True
link = c.post("/admin/garages/2/telegram/link", headers=HK).json()
assert link["url"] == f"https://t.me/autoservice_test_bot?start={link['code']}" and link["command"] == f"/start {link['code']}"
# webhook-ի պաշտպանություն
assert c.post("/telegram/webhook", json={}).status_code == 403
assert c.post("/telegram/webhook", headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}, json={}).status_code == 403
assert tg(5550002, "/start " + link["code"]).status_code == 200
assert any(ch == 5550002 and "Kentron Plus" in t and "Միացված է" in t for ch, t in msgs())
assert c.get("/admin/data", headers=HK).json()["garages"][0]["telegram_linked"] is True
sent.clear()
tg(5550009, "/start " + link["code"])                                              # կոդը մեկանգամյա է
assert "սխալ" in msgs()[-1][1]
tg(5550009, "/start"); tg(5550009, "բարև")                                         # առանց կոդի՝ օգնության տեքստ
assert all("Բարև" in t for _, t in msgs()[-2:])
# ժամկետանց կոդ
old = c.post("/admin/garages/3/telegram/link", headers=HS).json()["code"]
with db.connect() as cn:
    cn.execute("UPDATE link_codes SET created_at='2000-01-01 00:00:00'")
sent.clear(); tg(5550003, "/start " + old); assert "սխալ" in msgs()[-1][1]
assert c.get("/admin/data", headers=HS).json()["garages"][0]["telegram_linked"] is False
# ադմինի և 3-րդ գարաժի կապը
tg(5550003, "/start " + c.post("/admin/garages/3/telegram/link", headers=HS).json()["code"])
assert c.get("/admin/data", headers=H).json()["telegram"]["admin_linked"] is False
tg(5550001, "/start " + c.post("/admin/telegram/link", headers=H).json()["code"])
assert c.get("/admin/data", headers=H).json()["telegram"]["admin_linked"] is True

# նոր հայտ գարաժ 2-ի համար -> գարաժ 2 + ադմին, բայց ոչ գարաժ 3
sent.clear(); new_req("ՏիգրանTG", 2)
got = {ch: t for ch, t in msgs()}
assert set(got) == {5550002, 5550001}, got
assert "ՏիգրանTG" in got[5550002] and "Kentron Plus" in got[5550002] and "+374 91 000000" in got[5550002]
# առանց գարաժի -> միայն ադմին
sent.clear(); rid = new_req("ՍեդաԱռանց")
assert [ch for ch, _ in msgs()] == [5550001] and "նշանակված չէ" in msgs()[0][1]
# նշանակում -> միայն գարաժը (ադմինը ինքն է արել)
sent.clear(); assert c.put(f"/admin/requests/{rid}/garage", headers=H, json={"garage_id": 3}).status_code == 200
assert [ch for ch, _ in msgs()] == [5550003] and "ՍեդաԱռանց" in msgs()[0][1]
# անջատում -> գարաժը այլևս չի ստանում
assert c.delete("/admin/garages/2/telegram", headers=HK).status_code == 200
sent.clear(); new_req("ԼևոնԱնջատած", 2)
assert [ch for ch, _ in msgs()] == [5550001]
# Telegram-ի անկումը չի խանգարում հայտ ստանալուն
def boom(method, payload): raise OSError("network down")
telegram._call = boom
assert c.post("/requests", json={"name": "ՆարեԱնկում", "phone": "+374 91 000000", "garage_id": 3}).status_code == 201
telegram._call = fake_call
# ադմինի անջատում
assert c.delete("/admin/telegram", headers=H).status_code == 200
assert c.get("/admin/data", headers=H).json()["telegram"]["admin_linked"] is False
os.environ.pop("TELEGRAM_BOT_TOKEN")
sent.clear(); new_req("Առանց TG", 3); assert sent == []                              # առանց token-ի ոչինչ չի ուղարկվում
print("Telegram-ի թեստերն անցան ✓")

# =====================================================================
# Մուտքի հանում / գարաժի ջնջում -> արդեն տրված token-ները դադարում են աշխատել
# =====================================================================
assert c.delete("/admin/garages/2/account", headers=H).status_code == 200
assert c.get("/admin/data", headers=HK).status_code == 401
assert c.post("/admin/login", json={"login": "kentron", "password": "kentron-pass"}).status_code == 401
assert c.delete("/admin/garages/3", headers=H).status_code == 200
assert c.get("/admin/data", headers=HS).status_code == 401
print("Մուտքի հանման թեստերն անցան ✓")

# =====================================================================
# Հին բազայի migration (Փուլ 5-ի բազան չի կորչում)
# =====================================================================
import sqlite3, importlib
old_path = os.path.join(tempfile.mkdtemp(), "old.db")
oc = sqlite3.connect(old_path)
oc.executescript("""CREATE TABLE services (id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, keywords TEXT NOT NULL DEFAULT '');
CREATE TABLE garages (id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL, phone TEXT NOT NULL);
INSERT INTO services VALUES (1,'Յուղ','Սպասարկում','յուղ'); INSERT INTO garages VALUES (7,'Հին գարաժ','Ա 1','+374 1');""")
oc.commit(); oc.close()
db.DB_PATH = db.Path(old_path); db._ready.clear()
assert queries.get_garage(7).name == "Հին գարաժ"                                      # հին տվյալները մնացել են
assert queries.set_garage_login(7, "old", auth.hash_password("old-password")) == "ok"  # նոր սյուները ավելացել են
assert queries.find_garage_login("old")[0] == 7
print("Migration-ի թեստը անցավ ✓")
