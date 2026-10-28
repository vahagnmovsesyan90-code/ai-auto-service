"""Գործարկում՝ python test_api.py"""
import os, tempfile
import testdb
os.environ["ADMIN_PASSWORD"] = "test-pass"
os.environ["DATABASE_URL"] = testdb.create()          # ժամանակավոր Postgres բազա, ավարտին ջնջվում է

from fastapi.testclient import TestClient

from api import app

c = TestClient(app)

r = c.get("/services", params={"q": "արգելակ"})
assert r.status_code == 200 and len(r.json()) == 1

offers = c.get("/services/2/garages").json()
prices = [o["price"] for o in offers]
assert prices == sorted(prices) and prices[0] == 14000, prices

assert c.get("/garages").json().__len__() == 3

# գարաժների էջ՝ սերվերի կողմից որոնում և էջավորում (հազարավոր գարաժների համար)
cat = c.get("/api/catalog").json()
assert cat["total"] == 3 and cat["page"] == 1 and [g["name"] for g in cat["items"]] == sorted(g["name"] for g in cat["items"])
kentron = next(g for g in cat["items"] if g["name"] == "Garage Kentron")
assert {"id", "open_now", "rating", "address", "phone", "services_count"} <= set(kentron) and kentron["services_count"] >= 2
p1 = c.get("/api/catalog", params={"per_page": 2}).json(); p2 = c.get("/api/catalog", params={"per_page": 2, "page": 2}).json()
assert len(p1["items"]) == 2 and len(p2["items"]) == 1 and p1["total"] == p2["total"] == 3            # էջավորում
assert c.get("/api/catalog", params={"per_page": 999}).json()["per_page"] == 50                        # առավելագույնը 50
assert [g["name"] for g in c.get("/api/catalog", params={"q": "speed"}).json()["items"]] == ["Speed Service"]   # անունով
assert c.get("/api/catalog", params={"q": "Տերյան"}).json()["items"][0]["name"] == "Garage Kentron"             # հասցեով
by_service = c.get("/api/catalog", params={"q": "Կախոցի ստուգում"}).json()
assert "Garage Kentron" in {g["name"] for g in by_service["items"]} and "AutoPro Երևան" not in {g["name"] for g in by_service["items"]}   # ծառայությամբ
assert by_service["matched_services"] == ["Կախոցի ստուգում"] and by_service["mode"] == "simple"      # առանց բանալու՝ բանալի բառերով
for syn in ("ակ", "անիվ", "պագրիշկա", "pagrishka", "Ակերը թրթռում են"):                               # հոմանիշները նույն արդյունքն են տալիս
    assert c.get("/api/catalog", params={"q": syn}).json()["matched_services"] == ["Անվադողերի փոխարինում և հավասարակշռում"], syn
assert "Անվադողերի փոխարինում և հավասարակշռում" not in c.get("/api/catalog", params={"q": "արգելակ"}).json()["matched_services"]   # «ակ»-ը «արգելակ»-ի մեջ չի հաշվվում
sem = c.get("/api/catalog", params={"q": "փոսերի վրա թակոց է լսվում"}).json()                           # նկարագրությամբ, ոչ թե անունով
assert sem["matched_services"] == ["Կախոցի ստուգում"] and "AutoPro Երևան" not in {g["name"] for g in sem["items"]} and sem["total"] == 2
assert c.get("/api/catalog", params={"q": "zzz"}).json() == {"items": [], "total": 0, "page": 1, "per_page": 20, "matched_services": [], "mode": "simple"}
svcs = c.get(f"/garages/{kentron['id']}/services").json()
assert any(s["name"] == "Կախոցի ստուգում" for s in svcs) and all({"service_id", "name", "category", "price_amd", "duration_min"} <= set(s) for s in svcs)
assert [(s["category"], s["name"]) for s in svcs] == sorted((s["category"], s["name"]) for s in svcs)
assert c.get("/garages/999/services").status_code == 404
assert c.get("/catalog").status_code == 200 and c.get(f"/catalog/{kentron['id']}").status_code == 200 and c.get("/catalog/999").status_code == 404
assert "open_now" in c.get(f"/garages/{kentron['id']}").json()

# ---- Փուլ 3/4. chat (առանց բանալու՝ պարզ ռեժիմ) ----
import os, json
os.environ.pop("ANTHROPIC_API_KEY", None)
r = c.post("/chat", json={"messages": [{"role": "user", "content": "արգելակելիս ճռռոց է լսվում"}]})
assert r.status_code == 200 and r.json()["mode"] == "simple"
cards = r.json()["cards"]
assert [(x["name"], x["price_amd"]) for x in cards] == [("Speed Service", 14000), ("AutoPro Երևան", 15000), ("Garage Kentron", 18000)], cards
assert cards[0]["service_name"] and cards[0]["rating"] == {"avg": None, "count": 0, "score": None}
assert c.post("/chat", json={"messages": []}).status_code == 400
assert c.get("/app").status_code == 200

import chat
assert json.loads(chat.run_tool("garages_for_service", {"service_id": 6}))[0]["name"] == "Garage Kentron"
assert "error" in json.loads(chat.run_tool("garage_info", {"garage_id": 99}))
print("Chat-ի թեստերն անցան ✓")

# ---- Փուլ 5. բազա ----
import db, queries
assert db.DATABASE_URL == os.environ["DATABASE_URL"]
assert queries.set_price(3, 2, 13000) is True
assert queries.set_price(3, 6, 1000) is False          # Speed Service-ը օդորակիչ չունի
assert c.get("/services/2/garages").json()[0]["price"] == 13000   # API-ն տեսնում է փոփոխությունը
assert c.post("/chat", json={"messages": [{"role": "user", "content": "արգելակ ճռռոց"}]}).json()["cards"][0]["price_amd"] == 13000
db._ready.clear()                                        # նոր կապ՝ տվյալները մնացել են բազայում
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
assert c.post("/chat", json={"messages": [{"role": "user", "content": "լուսարձակները մթագնել են"}]}).json()["cards"][0]["price_amd"] == 7000  # keyword-ը աշխատում է

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
assert c.patch(f"/admin/requests/{reqs[0]['id']}", headers=H, json={"status": "called"}).status_code == 200
assert c.patch(f"/admin/requests/{reqs[0]['id']}", headers=H, json={"status": "bad"}).status_code == 422
assert c.get("/admin/data", headers=H).json()["requests"][0]["status"] == "called"
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
    stored = cn.execute("SELECT password_hash FROM garages WHERE id=2").fetchone()["password_hash"]
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
assert c.patch(f"/admin/requests/{r3}", headers=HK, json={"status": "called"}).status_code == 404
assert c.patch(f"/admin/requests/{r0}", headers=HK, json={"status": "called"}).status_code == 404
assert next(r for r in c.get("/admin/data", headers=H).json()["requests"] if r["id"] == r3)["status"] == "new"   # չի փոխվել
# սեփականը՝ թույլատրված
assert c.patch(f"/admin/requests/{r2}", headers=HK, json={"status": "called"}).status_code == 200
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
# Հայտերի փուլեր, արձագանքման ժամանակ, ամսական հաշվետվություն
# =====================================================================
auth.login_limiter.hits.clear()
gA = c.post("/admin/garages", headers=H, json={"name": "Report A"}).json()["id"]
gB = c.post("/admin/garages", headers=H, json={"name": "Report B"}).json()["id"]
c.put(f"/admin/garages/{gA}/account", headers=H, json={"login": "repa", "password": "repa-pass-1"})
c.put(f"/admin/garages/{gB}/account", headers=H, json={"login": "repb", "password": "repb-pass-1"})
HA = {"Authorization": "Bearer " + c.post("/admin/login", json={"login": "repa", "password": "repa-pass-1"}).json()["token"]}
HB = {"Authorization": "Bearer " + c.post("/admin/login", json={"login": "repb", "password": "repb-pass-1"}).json()["token"]}

# --- փուլերի անցումներ ---
rq = new_req("ՓուլՏեստ", gA)
row = lambda: next(r for r in c.get("/admin/data", headers=HA).json()["requests"] if r["id"] == rq)
assert row()["status"] == "new" and row()["first_response_at"] is None
assert c.patch(f"/admin/requests/{rq}", headers=HA, json={"status": "called"}).status_code == 200
first = row()["first_response_at"]
assert row()["status"] == "called" and first is not None and row()["status_changed_at"] is not None
for st in ("no_answer", "booked", "visited"):
    assert c.patch(f"/admin/requests/{rq}", headers=HA, json={"status": st}).status_code == 200 and row()["status"] == st
assert row()["first_response_at"] == first                                              # արձագանքման պահը չի փոխվում
assert c.patch(f"/admin/requests/{rq}", headers=HA, json={"status": "declined"}).status_code == 422     # պատճառը պարտադիր է
assert c.patch(f"/admin/requests/{rq}", headers=HA, json={"status": "declined", "decline_reason": "bad"}).status_code == 422
assert c.patch(f"/admin/requests/{rq}", headers=HA, json={"status": "bogus"}).status_code == 422
assert c.patch(f"/admin/requests/{rq}", headers=HA, json={"status": "declined", "decline_reason": "price"}).status_code == 200
assert row()["status"] == "declined" and row()["decline_reason"] == "price"
assert c.patch(f"/admin/requests/{rq}", headers=HA, json={"status": "booked", "decline_reason": "price"}).status_code == 200
assert row()["decline_reason"] is None                                                   # պատճառը մաքրվում է
assert c.patch(f"/admin/requests/{rq}", headers=HA, json={"status": "new"}).status_code == 200
assert row()["first_response_at"] == first                                               # նորից բացելը չի զրոյացնում
assert c.patch(f"/admin/requests/{rq}", headers=HB, json={"status": "visited"}).status_code == 404       # այլ գարաժ

# --- հաշվետվություն. վերահսկվող տվյալներ՝ ուղիղ բազայում ---
def ins(garage, status, created, first=None, reason=None):
    with db.connect() as cn:
        cn.execute("INSERT INTO requests(name,phone,garage_id,status,created_at,first_response_at,decline_reason) VALUES ('R','+374 91 000000',%s,%s,%s,%s,%s)",
                   (garage, status, created, first, reason))
with db.connect() as cn:
    cn.execute("DELETE FROM requests WHERE garage_id IN (%s,%s)", (gA, gB))
# Հոկտեմբեր (Երևան UTC+4). 2030-02-28 20:30 UTC = 2030-03-01 00:30 Երևան -> հոկտեմբեր
ins(gA, "visited",  "2030-03-05 08:00:00", "2030-03-05 08:10:00")           # արձագանք 10 ր
ins(gA, "booked",   "2030-03-06 08:00:00", "2030-03-06 08:30:00")           # 30 ր
ins(gA, "declined", "2030-03-07 08:00:00", "2030-03-07 09:00:00", "price")  # 60 ր
ins(gA, "declined", "2030-03-08 08:00:00", "2030-03-08 08:20:00", "price")
ins(gA, "declined", "2030-03-09 08:00:00", "2030-03-09 08:20:00", "far")
ins(gA, "new",      "2030-03-10 08:00:00")
ins(gA, "no_answer","2030-02-28 20:30:00", "2030-02-28 21:00:00")           # Երևանում՝ 1 հոկտեմբեր 00:30 -> հոկտեմբեր
ins(gA, "visited",  "2030-02-28 19:59:00", "2030-02-28 20:10:00")           # Երևանում՝ 30 սեպտեմբեր 23:59 -> սեպտեմբեր
ins(gA, "visited",  "2030-03-31 19:59:00", "2030-03-31 20:10:00")           # Երևանում՝ 31 հոկտեմբեր 23:59 -> հոկտեմբեր
ins(gA, "visited",  "2030-03-31 20:00:00", "2030-03-31 20:10:00")           # Երևանում՝ 1 նոյեմբեր 00:00 -> նոյեմբեր
ins(gB, "called",   "2030-03-12 08:00:00", "2030-03-12 08:05:00")
ins(None, "new",    "2030-03-13 08:00:00")                                   # առանց գարաժի

rep = c.get("/admin/report?month=2030-03", headers=H).json()
assert rep["month"] == "2030-03"
A = next(g for g in rep["garages"] if g["garage_id"] == gA)
assert A["total"] == 8, A                                                    # 6 սովորական + 1 թվագրված 01.03 00:30 + 1 թվագրված 31.03 23:59
assert (A["visited"], A["booked"], A["declined"], A["new"], A["no_answer"]) == (2, 1, 3, 1, 1), A
assert A["responded"] == 7 and A["booked_plus"] == 3
assert A["decline_reasons"] == {"price": 2, "far": 1}
assert A["median_response_min"] == 20, A                                     # {10,11,20,20,30,30,60} -> միջնային 20
B = next(g for g in rep["garages"] if g["garage_id"] == gB)
assert B["total"] == 1 and B["called"] == 1 and B["median_response_min"] == 5
assert rep["garages"][-1]["garage_id"] is None and rep["garages"][-1]["new"] == 1      # նշանակված չեղածները
assert rep["total"]["total"] == sum(g["total"] for g in rep["garages"]) == 8 + 1 + 1
# ամսվա սահմանները (Երևանի ժամանակով)
sep = c.get("/admin/report?month=2030-02", headers=H).json()
assert next(g for g in sep["garages"] if g["garage_id"] == gA)["total"] == 1          # միայն 23:59-ը
nov = c.get("/admin/report?month=2030-04", headers=H).json()
assert next(g for g in nov["garages"] if g["garage_id"] == gA)["total"] == 1          # 1 նոյեմբեր 00:00
empty = c.get("/admin/report?month=2020-01", headers=H).json()
assert empty["total"]["total"] == 0 and empty["total"]["median_response_min"] is None
# դեկտեմբերից հունվար անցումը
assert c.get("/admin/report?month=2030-12", headers=H).status_code == 200
# անվավեր ամիս
for bad in ("2026-13", "2026-00", "abc", "2026-1"):
    assert c.get("/admin/report?month=" + bad, headers=H).status_code == 422, bad
# գարաժին՝ միայն իրենը
ra = c.get("/admin/report?month=2030-03", headers=HA).json()
assert [g["garage_id"] for g in ra["garages"]] == [gA] and ra["total"]["total"] == 8
rb = c.get("/admin/report?month=2030-03", headers=HB).json()
assert [g["garage_id"] for g in rb["garages"]] == [gB] and rb["total"]["total"] == 1 and rb["total"]["decline_reasons"] == {}
assert c.get("/admin/report").status_code == 401                                        # առանց մուտքի
assert c.get("/admin/report").status_code == 401 and c.get("/admin/report?month=2030-03").status_code == 401
print("Փուլերի և հաշվետվության թեստերն անցան ✓")

# =====================================================================
# Վարորդի գնահատականներ. հաստատում, կեղծելու դեմ պաշտպանություն, վարկանիշ
# =====================================================================
import api as apimod
apimod.review_limiter.limit = 1000
auth.login_limiter.hits.clear()
R1 = c.post("/admin/garages", headers=H, json={"name": "Rate One"}).json()["id"]
R2 = c.post("/admin/garages", headers=H, json={"name": "Rate Two"}).json()["id"]
c.put(f"/admin/garages/{R1}/account", headers=H, json={"login": "rate1", "password": "rate1-pass-1"})
c.put(f"/admin/garages/{R2}/account", headers=H, json={"login": "rate2", "password": "rate2-pass-1"})
H1 = {"Authorization": "Bearer " + c.post("/admin/login", json={"login": "rate1", "password": "rate1-pass-1"}).json()["token"]}
H2 = {"Authorization": "Bearer " + c.post("/admin/login", json={"login": "rate2", "password": "rate2-pass-1"}).json()["token"]}
def mk(garage, phone, name="Վ"):
    rid = queries.create_request(name, phone, garage, None, "")
    return rid, queries.request_row(rid)["review_token"]
def review(token, **kw): return c.post(f"/reviews/{token}", json=kw)

# հայտի պատասխանում վարորդը ստանում է գնահատման հղում (միայն եթե գարաժ կա)
r = c.post("/requests", json={"name": "Գ", "phone": "+374 91 100001", "garage_id": R1}).json()
assert len(r["review_token"]) > 20 and r["garage"] == "Rate One"
assert c.post("/requests", json={"name": "Գ", "phone": "+374 91 100002"}).json()["review_token"] is None
tok = r["review_token"]
chk = c.post("/my-requests/check", json={"tokens": [tok]}).json()["requests"]
assert chk[0]["garage"] == "Rate One" and chk[0]["already_reviewed"] is False and chk[0]["rating"] is None
assert c.get("/review/anything").status_code == 404                              # առանձին գնահատման էջ այլևս չկա

# վալիդացիա
assert review(tok, went=True).status_code == 422                                # «գնացի»՝ առանց աստղերի
assert review(tok, went=True, rating=0).status_code == 422 and review(tok, went=True, rating=6).status_code == 422
assert review(tok, went=False).status_code == 422                               # «չգնացի»՝ առանց պատճառի
assert review(tok, went=False, reason="bogus").status_code == 422
assert review(tok, went=True, rating=5, comment="x" * 501).status_code == 422
assert review("nonexistent-token", went=True, rating=5).status_code == 404
nog_rid, nog_tok = mk(None, "+374 91 100003")
assert review(nog_tok, went=True, rating=5).status_code == 400                  # առանց գարաժի հայտը չի գնահատվում

# մեկ հայտ = մեկ կարծիք
assert review(tok, went=True, rating=5, comment="Շատ լավ սպասարկում", display_name="Արամ").status_code == 201
assert review(tok, went=True, rating=1).status_code == 409
chk = c.post("/my-requests/check", json={"tokens": [tok]}).json()["requests"][0]
assert chk["already_reviewed"] is True and chk["rating"] == 5 and chk["went"] is True   # ցուցակը ցույց է տալիս տրված աստղերը
assert chk["comment"] == "Շատ լավ սպասարկում" and chk["display_name"] == "Արամ"          # և գրած կարծիքը

# կրկնակի կարծիք նույն համարից նույն գարաժին (հեռախոսի տարբեր գրելաձևով)
_, tok_dup = mk(R1, "091100001")
r_dup = review(tok_dup, went=True, rating=4, comment="Երկրորդ այցը՝ նույնպես լավ", display_name="Արամ Ա.")
assert r_dup.status_code == 200 and r_dup.json() == {"ok": True, "updated": True}        # կրկնակի չի ստեղծվում. նախորդը թարմացվում է
chk = c.post("/my-requests/check", json={"tokens": [tok_dup, tok]}).json()["requests"]
assert len(chk) == 2 and all(x["already_reviewed"] and x["rating"] == 4 and x["went"] and x["comment"] == "Երկրորդ այցը՝ նույնպես լավ"
                             and x["display_name"] == "Արամ Ա." for x in chk)           # երկու հայտն էլ ցույց են տալիս թարմացվածը
assert c.get(f"/garages/{R1}").json()["rating"]["count"] == 1 and c.get(f"/garages/{R1}").json()["rating"]["avg"] == 4.0   # գարաժը դեռ մեկ կարծիք ունի
assert review(tok_dup, went=False, reason="far").status_code == 201
chk = c.post("/my-requests/check", json={"tokens": [tok_dup]}).json()["requests"][0]
assert chk["already_reviewed"] is True and chk["went"] is False and chk["rating"] is None


# վարկանիշ. միջին, կարծիքների թիվ, «չգնացի»-ն չի հաշվվում
g = c.get(f"/garages/{R1}").json()
assert g["rating"]["avg"] == 4.0 and g["rating"]["count"] == 1 and g["rating"]["score"] is not None   # թարմացված 4-ը, մեկ կարծիք
for i, st in enumerate((4, 4, 3)):
    _, t = mk(R1, f"+374 91 2000{i:02d}"); assert review(t, went=True, rating=st).status_code == 201
g = c.get(f"/garages/{R1}").json()["rating"]
assert g["count"] == 4 and g["avg"] == 3.8                                      # (4+4+4+3)/4 = 3.75 -> 3.8
# 20 կարծիք 4.7 միջինով՝ Rate Two
for i in range(20):
    _, t = mk(R2, f"+374 91 3000{i:02d}"); review(t, went=True, rating=5 if i % 3 else 4)
g2 = c.get(f"/garages/{R2}").json()["rating"]
assert g2["count"] == 20 and 4.5 <= g2["avg"] <= 4.8
# 1 կարծիք 5.0-ով չի հաղթում շատ կարծիքով լավ գնահատականին
_, solo = mk(R1, "+374 91 400001")
R3 = c.post("/admin/garages", headers=H, json={"name": "Rate Solo"}).json()["id"]
_, ts = mk(R3, "+374 91 400002"); review(ts, went=True, rating=5)
solo = c.get(f"/garages/{R3}").json()["rating"]
assert solo["avg"] == 5.0 and solo["count"] == 1 and solo["score"] < g2["score"], (solo, g2)
assert c.get(f"/garages/{R3}").json()["rating"]["score"] < 5.0
# անկարծիք գարաժ
R4 = c.post("/admin/garages", headers=H, json={"name": "Rate None"}).json()["id"]
assert c.get(f"/garages/{R4}").json()["rating"] == {"avg": None, "count": 0, "score": None}

# հրապարակային կարծիքներ. առանց հեռախոսի, միայն «գնացի»
pub = c.get(f"/garages/{R1}/reviews").json()
assert len(pub) == 4 and pub[-1]["comment"] == "Երկրորդ այցը՝ նույնպես լավ" and pub[-1]["display_name"] == "Արամ Ա."   # թարմացված տեքստը
assert set(pub[0]) == {"rating", "comment", "display_name", "created_at", "service"}
assert "091100001" not in str(pub) and "91 100001" not in str(pub)
assert c.get("/garages/99999/reviews").status_code == 404

# գարաժը չի տեսնում գաղտնի հղումը (հակառակ դեպքում կկարողանար կեղծ կարծիք գրել)
d1 = c.get("/admin/data", headers=H1)
assert "review_token" not in d1.text and tok not in d1.text
assert "review_token" not in c.get("/admin/data", headers=H).text

# ադմինի և գարաժի տեսածը
ar = c.get("/admin/reviews", headers=H).json()
assert any(r["went"] == 0 for r in ar["reviews"]) and any(r["went"] == 1 for r in ar["reviews"])
r1v = c.get("/admin/reviews", headers=H1).json()
assert [x["garage_id"] for x in r1v["ratings"]] == [R1] and r1v["ratings"][0]["count"] == 4
assert all(r["garage_id"] == R1 and r["went"] == 1 and r["hidden"] == 0 for r in r1v["reviews"]) and len(r1v["reviews"]) == 4
r2v = c.get("/admin/reviews", headers=H2).json()
assert all(r["garage_id"] == R2 for r in r2v["reviews"])
assert c.get("/admin/reviews").status_code == 401

# մոդերացիա. միայն ադմինը, պատճառով
rv_id = next(r["id"] for r in ar["reviews"] if r["garage_id"] == R1 and r["comment"] == "Երկրորդ այցը՝ նույնպես լավ")
assert c.patch(f"/admin/reviews/{rv_id}", headers=H1, json={"hidden": True, "reason": "կեղծ"}).status_code == 403     # գարաժը չի կարող թաքցնել
assert c.patch(f"/admin/reviews/{rv_id}", headers=H, json={"hidden": True}).status_code == 422
assert c.patch("/admin/reviews/99999", headers=H, json={"hidden": True, "reason": "x"}).status_code == 404
assert c.patch(f"/admin/reviews/{rv_id}", headers=H, json={"hidden": True, "reason": "կեղծ"}).status_code == 200
g = c.get(f"/garages/{R1}").json()["rating"]
assert g["count"] == 3 and g["avg"] == 3.7                                      # 5-ը հանվեց. (4+4+3)/3
assert len(c.get(f"/garages/{R1}/reviews").json()) == 3
assert len(c.get("/admin/reviews", headers=H1).json()["reviews"]) == 3          # գարաժը թաքցվածը չի տեսնում
assert any(r["id"] == rv_id and r["hidden"] == 1 for r in c.get("/admin/reviews", headers=H).json()["reviews"])
assert c.patch(f"/admin/reviews/{rv_id}", headers=H, json={"hidden": False}).status_code == 200
assert c.get(f"/garages/{R1}").json()["rating"]["count"] == 4                   # վերականգնվեց

# հաշվետվություն. վարորդի հաստատում և անհամապատասխանություն
rid_m, tok_m = mk(R2, "+374 91 500001")
assert c.patch(f"/admin/requests/{rid_m}", headers=H2, json={"status": "visited"}).status_code == 200   # գարաժը՝ «այցելեց»
assert review(tok_m, went=False, reason="other_garage").status_code == 201                              # վարորդը՝ «չգնացի»
rp = next(x for x in c.get("/admin/report", headers=H).json()["garages"] if x["garage_id"] == R2)
assert rp["mismatch"] == 1 and rp["driver_no_visit"] == 1 and rp["confirmed_visits"] == 20, rp
rp2 = c.get("/admin/report", headers=H2).json()["garages"][0]
assert rp2["mismatch"] == 1                                                     # գարաժը նույնպես տեսնում է
assert c.get("/admin/report", headers=H1).json()["garages"][0]["mismatch"] == 0

# chat-ի քարտերը ցույց են տալիս գնահատականները
queries.upsert_garage_service(R1, 1, 1000, 30); queries.upsert_garage_service(R2, 1, 2000, 30)
cards = {x["garage_id"]: x for x in c.post("/chat", json={"messages": [{"role": "user", "content": "յուղ"}]}).json()["cards"]}
assert cards[R1]["rating"]["count"] == 4 and cards[R2]["rating"]["count"] == 20 and cards[R2]["rating"]["avg"] >= 4.5
assert c.get("/services/1/garages").json()[0]["garage"]["rating"]["count"] in (0, 4)

# rate limit
apimod.review_limiter.limit = 3; apimod.review_limiter.hits.clear()
codes = [review("nonexistent-token", went=True, rating=5).status_code for _ in range(5)]
assert codes[:3] == [404, 404, 404] and codes[3:] == [429, 429], codes
apimod.review_limiter.limit = 1000
print("Գնահատականների թեստերն անցան ✓")

# =====================================================================
# Էջերը. no-cache և տարբերակի նշում (թարմացումից հետո հին էջը չպետք է մնա քեշում)
# =====================================================================
for page_path in ("/app", "/panel", "/my", "/catalog", f"/catalog/{c.get('/garages').json()[0]['id']}"):
    r = c.get(page_path)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", page_path
    assert "__APP_VERSION__" not in r.text and f"v{apimod.APP_VERSION}" in r.text, page_path
assert c.get("/").json()["version"] == apimod.APP_VERSION
print("Էջերի no-cache և տարբերակի թեստերն անցան ✓")

# =====================================================================
# «Իմ հայտերը». սերվերի ստուգում (անվավեր հղումները չեն երևա) և հայերեն տառերի ուղղորդում
# =====================================================================
apimod.review_limiter.limit = 1000; apimod.review_limiter.hits.clear()
_, good_tok = mk(R1, "+374 91 600001")
_, rev_tok = mk(R2, "+374 91 600002"); review(rev_tok, went=True, rating=5)
_, nog_tok2 = mk(None, "+374 91 600003")
res = c.post("/my-requests/check", json={"tokens": [good_tok, "fake-token-123", rev_tok, nog_tok2, good_tok]}).json()["requests"]
by = {x["token"]: x for x in res}
assert set(by) == {good_tok, rev_tok}, by                                    # կեղծը և առանց գարաժի հայտը չեն վերադառնում
assert by[good_tok]["garage"] == "Rate One" and by[good_tok]["already_reviewed"] is False
assert by[rev_tok]["already_reviewed"] is True and by[rev_tok]["garage"] == "Rate Two"
assert c.post("/my-requests/check", json={"tokens": []}).json() == {"requests": [], "total": 0, "page": 1, "per_page": 20, "all_total": 0, "pending_total": 0, "rated_total": 0, "valid": []}
assert c.post("/my-requests/check", json={"tokens": ["x"] * 201}).status_code == 422  # առավելագույնը 200
pg = c.post("/my-requests/check", json={"tokens": [good_tok, rev_tok], "per_page": 1}).json()        # էջավորումը սերվերում
assert pg["total"] == 2 and pg["page"] == 1 and pg["per_page"] == 1 and len(pg["requests"]) == 1 and len(pg["valid"]) == 2
assert pg["requests"][0]["token"] == rev_tok and "created_at" in pg["requests"][0]                   # նորը վերևում է
pg2 = c.post("/my-requests/check", json={"tokens": [good_tok, rev_tok], "per_page": 1, "page": 2}).json()
assert [x["token"] for x in pg2["requests"]] == [good_tok] and {v["token"]: v["done"] for v in pg2["valid"]} == {good_tok: False, rev_tok: True}
assert c.post("/my-requests/check", json={"tokens": [good_tok], "per_page": 51}).status_code == 422
assert c.post("/my-requests/check", json={"tokens": ["a" * 65]}).json()["requests"] == []
assert "phone" not in str(res) and "name" not in {k for x in res for k in x}           # անձնական տվյալ չի հայտնվում
apimod.check_limiter.limit = 2; apimod.check_limiter.hits.clear()
assert [c.post("/my-requests/check", json={"tokens": [good_tok]}).status_code for _ in range(3)] == [200, 200, 429]
apimod.check_limiter.limit = 1000
# ստուգումը չի ծախսում գնահատման սահմանաչափը. 30 ստուգումից հետո գնահատումը դեռ աշխատում է
apimod.review_limiter.limit = 3; apimod.review_limiter.hits.clear(); apimod.check_limiter.hits.clear(); apimod.check_limiter.limit = 100
for _ in range(30): assert c.post("/my-requests/check", json={"tokens": [good_tok]}).status_code == 200
assert review(good_tok, went=True, rating=4).status_code == 201
apimod.review_limiter.limit = 1000

# հայերեն տառեր. լատինատառ/ռուսերեն ձեռնարկ՝ առանց խանգարելու մակնիշներին ու համընկնումներին
def simple(text): return c.post("/chat", json={"messages": [{"role": "user", "content": text}]}).json()
for txt in ("arrgelak chrrroc", "tormoza skripyat", "тормоза скрипят", "problem with my car"):
    r = simple(txt)
    assert "հայերեն տառերով" in r["reply"] and r["cards"] == [], txt
assert simple("check engine լամպը վառվում է")["cards"]                         # համընկնում կա -> աշխատում է
assert simple("BMW-ի արգելակները ճռռում են")["cards"]                          # մակնիշը լատինատառ՝ խնդիր չէ
assert "հայերեն տառերով" not in simple("արգելակելիս ճռռոց է լսվում")["reply"]
assert "հայերեն տառերով" not in simple("բլա բլա")["reply"] and "Չհասկացա" in simple("բլա բլա")["reply"]   # հայերեն անհասկանալին՝ նախկինի պես
assert "հայերեն տառերով" not in simple("12 34")["reply"]                                  # թվերը հայերեն հուշում չեն առաջացնում
assert chat.mostly_non_armenian("hello world") and not chat.mostly_non_armenian("BMW արգելակ") and not chat.mostly_non_armenian("ok")
assert "մի խնդրիր նրան գրել հայերեն տառերով" in "".join(b["text"] for b in chat.system_prompt())   # AI-ն հայերեն գրել չի խնդրում
print("«Իմ հայտերը»-ի ստուգման և հայերեն տառերի թեստերն անցան ✓")

# =====================================================================
# Գարաժի տեղը քարտեզում և «Երթուղի»
# =====================================================================
import geo
assert all(g["lat"] is None for g in c.get("/garages").json())                                  # սկզբում կետ չկա
cards0 = c.post("/chat", json={"messages": [{"role": "user", "content": "արգելակ ճռռոց"}]}).json()["cards"]
assert all(x["lat"] is None and x["lng"] is None for x in cards0)                                # չհաստատված կետը չի ուղարկվում
LOC = {"lat": 40.1811, "lng": 44.5136}
assert c.put(f"/admin/garages/{R1}/location", json=LOC).status_code == 401                      # առանց մուտքի
assert c.put(f"/admin/garages/{R2}/location", json=LOC, headers=H1).status_code == 403          # ուրիշի գարաժը՝ չի կարելի
assert c.put(f"/admin/garages/{R1}/location", json={"lat": 95, "lng": 44}, headers=H1).status_code == 422
assert c.put(f"/admin/garages/{R1}/location", json={"lat": 0, "lng": 0}, headers=H1).status_code == 422   # Հայաստանից դուրս
assert c.put(f"/admin/garages/{R1}/location", json={"lat": "x", "lng": 1}, headers=H1).status_code == 422
assert c.put(f"/admin/garages/{R1}/location", json=LOC, headers=H1).status_code == 200
assert c.put("/admin/garages/9999/location", json=LOC, headers=H).status_code == 404
g1 = [g for g in c.get("/admin/data", headers=H1).json()["garages"]][0]
assert g1["lat"] == LOC["lat"] and g1["lng"] == LOC["lng"]
assert c.get(f"/garages/{R1}").json()["lat"] == LOC["lat"]
assert c.put(f"/admin/garages/{cards0[0]['garage_id']}/location", json=LOC, headers=H).status_code == 200            # ադմինը կարող է ցանկացած գարաժի
cards1 = c.post("/chat", json={"messages": [{"role": "user", "content": "արգելակ ճռռոց"}]}).json()["cards"]
assert {x["garage_id"]: x["lat"] for x in cards1}[cards0[0]["garage_id"]] == LOC["lat"] and all(x["lat"] is None for x in cards1 if x["garage_id"] != cards0[0]["garage_id"])
assert json.loads(chat.run_tool("garage_info", {"garage_id": cards0[0]["garage_id"]}))["has_location"] is True
assert c.delete(f"/admin/garages/{cards0[0]['garage_id']}/location", headers=H).status_code == 200
# հասցեն չփոխելով (միայն հեռախոս)՝ կետը մնում է
cur = c.get("/admin/data", headers=H1).json()["garages"][0]
assert c.put(f"/admin/garages/{R1}", json={"name": cur["name"], "address": cur["address"], "phone": "+374 99 000000"}, headers=H1).status_code == 200
assert c.get(f"/garages/{R1}").json()["lat"] == LOC["lat"]
# հասցեն փոխվեց՝ հին կետը հանվում է (վարորդին սխալ տեղ չենք ուղարկում)
assert c.put(f"/admin/garages/{R1}", json={"name": cur["name"], "address": "Նոր փողոց 5", "phone": "+374 99 000000"}, headers=H1).status_code == 200
assert c.get(f"/garages/{R1}").json()["lat"] is None
assert c.put(f"/admin/garages/{R1}/location", json=LOC, headers=H1).status_code == 200
assert c.delete(f"/admin/garages/{R1}/location", headers=H1).status_code == 200 and c.get(f"/garages/{R1}").json()["lat"] is None
assert c.delete(f"/admin/garages/{R2}/location", headers=H1).status_code == 403

# geocode. Nominatim-ը փոխարինված է, իրական հարցում չկա
calls = []
def fake_fetch(query):
    calls.append(query)
    return [{"lat": "40.1792", "lon": "44.4991", "display_name": "Երևան"}] if "երևան" in query.lower() else (
        [{"lat": "51.5", "lon": "0.1", "display_name": "London"}] if "london" in query else [])
geo._fetch = fake_fetch; geo._last_call = 0
geo.time.sleep = lambda s: None                          # թեստում սպասելու կարիք չկա
assert c.post("/admin/geocode", json={"query": "Երևան, Արշակունյաց 1"}).status_code == 401
rg = c.post("/admin/geocode", json={"query": "Երևան, Արշակունյաց 1"}, headers=H1).json()
assert rg["found"] and abs(rg["lat"] - 40.1792) < 1e-6
assert c.get(f"/garages/{R1}").json()["lat"] is None     # geocode-ը ինքն չի պահպանում
c.post("/admin/geocode", json={"query": "  ԵՐԵՎԱՆ,  Արշակունյաց 1 ".replace("ԵՐԵՎԱՆ", "երևան")}, headers=H1)
assert len(calls) == 1, calls
assert c.post("/admin/geocode", json={"query": "zzz unknown street"}, headers=H1).json() == {"found": False}
assert c.post("/admin/geocode", json={"query": "London Bridge"}, headers=H1).json() == {"found": False}   # Հայաստանից դուրս արդյունքը չի ընդունվում
assert c.post("/admin/geocode", json={"query": "ab"}, headers=H1).status_code == 422
def boom(query): raise OSError("net down")
geo._fetch = boom
assert c.post("/admin/geocode", json={"query": "ուրիշ հասցե 77"}, headers=H1).status_code == 503
geo._fetch = fake_fetch
auth.geocode_limiter.limit = 3; auth.geocode_limiter.hits.clear()
codes = [c.post("/admin/geocode", json={"query": f"Երևան {i}"}, headers=H1).status_code for i in range(5)]
assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429], codes
auth.geocode_limiter.limit = 1000
# Leaflet-ը սերվերից է (ոչ արտաքին CDN)
assert c.get("/static/leaflet/leaflet.js").status_code == 200 and "unpkg" not in c.get("/panel").text
print("Քարտեզի և երթուղու թեստերն անցան ✓")

# =====================================================================
# Հաճախ հարցվող հարցեր (chat-ի chip-երը՝ ըստ ամենաշատ հարցված ծառայությունների)
# =====================================================================
with db.connect() as cn:
    cn.execute("DELETE FROM chat_queries")
apimod.POPULAR_CACHE.clear()
r = c.post("/chat", json={"messages": [{"role": "user", "content": "  արգելակելիս   ճռռոց է լսվում "}]}); assert r.status_code == 200
assert queries.query_stats()["total"] == 1
assert queries.popular_questions(min_total=1) == [{"service_id": 2, "text": "Արգելակելիս ճռռոց է լսվում", "count": 1}]   # ծառայության օրինակ հարցը, ոչ թե վարորդի ձևակերպումը
c.post("/chat", json={"messages": [{"role": "user", "content": "արգելակ"}, {"role": "assistant", "content": "..."}, {"role": "user", "content": "օդորակիչը չի սառեցնում"}]})
assert queries.query_stats()["total"] == 1                                              # խոսակցության հաջորդ հարցերը չեն հաշվվում
c.post("/chat", json={"messages": [{"role": "user", "content": "ո՞ր գարաժն է հիմա բաց"}]})
st = queries.query_stats(); assert st["total"] == 2 and st["unmatched"] == [{"text": "ո՞ր գարաժն է հիմա բաց", "n": 1}]   # ծառայություն չգտնվեց -> «չհամընկած»
apimod.POPULAR_CACHE.clear()
assert [x["text"] for x in c.get("/popular-questions").json()] == ["Արգելակելիս ճռռոց է լսվում", "Օդորակիչը չի սառեցնում", "Ո՞ր գարաժն է հիմա բաց"]   # քիչ տվյալ -> լռելյայնները
for _ in range(25): queries.log_query("կոնդիցիոները չի աշխատում", 6, "ai")
for _ in range(21): queries.log_query("յուղ փոխել", 1, "simple")
apimod.POPULAR_CACHE.clear()
pop = c.get("/popular-questions").json()
assert [x["text"] for x in pop] == ["Օդորակիչը չի սառեցնում", "Յուղը փոխելու ժամանակն է", "Ո՞ր գարաժն է հիմա բաց"], pop   # ըստ քանակի. 25 > 21 > 1
assert pop[0]["service_id"] == 6 and pop[2]["service_id"] is None
assert c.get("/popular-questions").json() == pop                                        # քեշը նույնն է տալիս
# ադմինը փոխում է օրինակ հարցը -> chip-ը փոխվում է
svc6 = next(s for s in c.get("/admin/data", headers=H).json()["services"] if s["id"] == 6)
assert svc6["sample_question"] == "Օդորակիչը չի սառեցնում"
assert c.put("/admin/services/6", headers=H, json={**{k: svc6[k] for k in ("name", "category", "keywords")}, "sample_question": " Կոնդիցիոները չի սառեցնում "}).status_code == 200
apimod.POPULAR_CACHE.clear()
assert c.get("/popular-questions").json()[0]["text"] == "Կոնդիցիոները չի սառեցնում"
# օրինակ հարց չկա -> վարորդների ամենահաճախ ձևակերպումը
assert c.put("/admin/services/6", headers=H, json={**{k: svc6[k] for k in ("name", "category", "keywords")}, "sample_question": ""}).status_code == 200
for _ in range(3): queries.log_query("Օդորակիչը տաք է փչում", 6, "ai")
apimod.POPULAR_CACHE.clear()
assert c.get("/popular-questions").json()[0]["text"] == "կոնդիցիոները չի աշխատում"      # 25 անգամ > 3 անգամ
queries.log_query("x" * 500, 2, "simple")
with db.connect() as cn:
    assert cn.execute("SELECT MAX(LENGTH(text)) AS m FROM chat_queries").fetchone()["m"] == 200
assert c.post("/admin/services", headers=H, json={"name": "Փայլ", "sample_question": "x" * 151}).status_code == 422
print("Հաճախ հարցվող հարցերի թեստերն անցան ✓")

# =====================================================================
# Հին SQLite բազայից տվյալների ներմուծում (python db.py import-sqlite)
# =====================================================================
import sqlite3
old_path = os.path.join(tempfile.mkdtemp(), "old.db")
oc = sqlite3.connect(old_path)
oc.executescript("""CREATE TABLE services (id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, keywords TEXT NOT NULL DEFAULT '');
CREATE TABLE garages (id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL, phone TEXT NOT NULL, login TEXT, password_hash TEXT);
INSERT INTO services VALUES (1,'Յուղ','Սպասարկում','յուղ'); INSERT INTO garages VALUES (7,'Հին գարաժ','Ա 1','+374 1','old',NULL);
CREATE TABLE garage_services (garage_id INTEGER, service_id INTEGER, price INTEGER, duration_min INTEGER, PRIMARY KEY (garage_id, service_id));
INSERT INTO garage_services VALUES (7,1,9000,30);
CREATE TABLE requests (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, name TEXT NOT NULL, phone TEXT NOT NULL,
  garage_id INTEGER REFERENCES garages(id) ON DELETE SET NULL, service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
  message TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','done')));
INSERT INTO requests(id,created_at,name,phone,garage_id,status) VALUES (1,'2025-01-02 03:04:05','Հին մշակված','+374 1',7,'done'),(2,'2025-01-03 00:00:00','Հին նոր','+374 2',7,'new');""")
oc.commit(); oc.close()
import_url = testdb.create()                                   # առանձին դատարկ բազա ներմուծման համար
db.close(); db.DATABASE_URL = os.environ["DATABASE_URL"] = import_url
counts = db.import_sqlite(old_path)
assert counts == {"services": 1, "garages": 1, "garage_services": 1, "requests": 2}, counts
assert queries.get_garage(7).name == "Հին գարաժ" and queries.get_garage(7).services[1].price == 9000   # հին տվյալները տեղափոխվել են
assert queries.set_garage_login(7, "old", auth.hash_password("old-password")) == "ok"
assert queries.find_garage_login("old")[0] == 7
assert queries.create_garage("Նոր", "Բ 2", "+374 3") == 8                                   # id-ների հաջորդականությունը շարունակվում է
print("SQLite-ից ներմուծման թեստը անցավ ✓")
old_reqs = {r["id"]: r["status"] for r in queries.list_requests()}
assert old_reqs == {1: "called", 2: "new"}, old_reqs                                    # «done» -> «called», տվյալները մնացել են
assert queries.request_row(1)["created_at"] == "2025-01-02 03:04:05"                   # ժամանակը նույն ձևաչափով է
assert queries.set_request_status(2, "booked") and queries.set_request_status(1, "declined", "price")   # նոր փուլերը թույլատրված են
assert queries.request_row(2)["first_response_at"] is not None
assert queries.create_request("Ն", "+374 91 111111", 7, 1, "") == 3
try:
    db.import_sqlite(old_path); raise AssertionError("դատարկ չէ՝ պետք է մերժվեր")
except SystemExit:
    pass
print("Հին հայտերի ներմուծման թեստը անցավ ✓")
