"""Telegram-ի կապի և ծանուցումների դիտարկչային թեստ (կեղծ Telegram API-ով, իրական բոտ պետք չէ).
Գործարկում՝ python test_telegram_browser.py"""
import os, re, tempfile, threading, time, urllib.request

PORT = 8771
BASE = f"http://127.0.0.1:{PORT}"
os.environ.update(ADMIN_PASSWORD="pw", AUTOSERVICE_DB=os.path.join(tempfile.mkdtemp(), "tg.db"),
                  TELEGRAM_BOT_TOKEN="123:fake")
os.environ.pop("ANTHROPIC_API_KEY", None)

import uvicorn
import telegram
from api import app

sent = []
def fake_call(method, payload):
    sent.append((method, payload))
    return {"ok": True, "result": {"username": "autoservice_test_bot"}}
telegram._call = fake_call
telegram.SYNC = True
texts = lambda: [(p["chat_id"], p["text"]) for m, p in sent if m == "sendMessage"]

server = uvicorn.Server(uvicorn.Config(app, port=PORT, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(40):
    try: urllib.request.urlopen(BASE + "/", timeout=1); break
    except Exception: time.sleep(0.25)

from playwright.sync_api import sync_playwright, expect

SEC = {"X-Telegram-Bot-Api-Secret-Token": telegram.webhook_secret()}
os.makedirs("shots", exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1100, "height": 800})
    a = ctx.new_page()
    errors = []
    a.on("pageerror", lambda e: errors.append(str(e)))
    def press_start(chat_id, code):
        r = ctx.request.post(BASE + "/telegram/webhook", headers=SEC,
                             data={"message": {"chat": {"id": chat_id}, "text": "/start " + code}})
        assert r.ok

    # --- ադմինը կապում է իր Telegram-ը ---
    a.goto(BASE + "/panel"); a.fill("#pw", "pw"); a.click("#go")
    expect(a.locator("#app")).to_be_visible()
    expect(a.locator("#main")).to_contain_text("Միացված չէ")
    a.click("[data-tglink=admin]")
    link = a.locator("#tgInfo-admin a")
    expect(link).to_be_visible()
    href = link.get_attribute("href")
    m = re.fullmatch(r"https://t\.me/autoservice_test_bot\?start=([A-Za-z0-9_-]+)", href)
    assert m, href
    a.screenshot(path="shots/tg_admin_link.png")
    press_start(777, m.group(1))                                     # «Telegram»-ում սեղմում են Start
    expect(a.locator("#main")).to_contain_text("✓ Միացված է", timeout=10000)   # էջը ինքն է թարմանում
    expect(a.locator("#toast")).to_contain_text("Telegram-ը միացավ")
    assert (777, ) == tuple(c for c, t in texts() if "ադմինի" in t)
    print("Ադմինի Telegram-ի կապ (հղում -> Start -> էջը թարմանում) ✓")

    # --- գարաժի մուտքը և նրա Telegram-ը ---
    a.click("[data-t=garages]"); a.get_by_role("button", name="Garage Kentron").click()
    a.fill("#al", "kentron"); a.fill("#ap", "kentron-pass-1"); a.click("#saveAcc")
    expect(a.locator("#main")).to_contain_text("Մուտքանուն՝ kentron")
    a.click("[data-tglink=garage]")
    code = re.search(r"start=([A-Za-z0-9_-]+)", a.locator("#tgInfo-garage a").get_attribute("href")).group(1)
    press_start(888, code)
    expect(a.locator("#main")).to_contain_text("✓ Միացված է", timeout=10000)
    assert any(c == 888 and "Garage Kentron" in t for c, t in texts())
    print("Գարաժի Telegram-ի կապ (ադմինի կողմից) ✓")

    # --- նոր հայտեր ---
    sent.clear()
    r = ctx.request.post(BASE + "/requests", data={"name": "Գոռ", "phone": "+374 91 555555", "garage_id": 2, "service_id": 2, "message": "շտապ է"})
    assert r.status == 201
    got = dict(texts())
    assert set(got) == {777, 888}, got
    assert all(s in got[888] for s in ("Գոռ", "+374 91 555555", "շտապ է", "Garage Kentron", "Արգելակային"))
    sent.clear()
    ctx.request.post(BASE + "/requests", data={"name": "Մարի", "phone": "+374 91 666666"})
    assert [c for c, _ in texts()] == [777] and "նշանակված չէ" in texts()[0][1]                  # առանց գարաժի՝ միայն ադմին
    print("Հայտերի ծանուցումներ (գարաժ + ադմին, առանց գարաժի՝ միայն ադմին) ✓")

    # նշանակում պանելից -> գարաժը ստանում է
    a.click("[data-t=requests]"); a.reload(); expect(a.locator("#app")).to_be_visible()
    sent.clear()
    a.locator("tr", has_text="Մարի").locator("[data-assign]").select_option(label="Garage Kentron")
    expect(a.locator("#toast")).to_contain_text("նշանակվեց")
    assert [c for c, _ in texts()] == [888] and "Մարի" in texts()[0][1]
    print("Նշանակման ծանուցում գարաժին ✓")

    # --- գարաժի սեփականատերը ինքն է կապում/անջատում ---
    a.click("#out")
    a.fill("#lg", "kentron"); a.fill("#pw", "kentron-pass-1"); a.click("#go")
    expect(a.locator("#who")).to_have_text("Garage Kentron")
    a.click("[data-t=garages]")
    expect(a.locator("#main")).to_contain_text("✓ Միացված է")
    a.locator("[data-tgunlink=garage]").click()
    expect(a.locator("#main")).to_contain_text("Միացված չէ"); expect(a.locator("#toast")).to_contain_text("անջատվեց")
    sent.clear(); ctx.request.post(BASE + "/requests", data={"name": "Տիգ", "phone": "+374 91 777777", "garage_id": 2})
    assert [c for c, _ in texts()] == [777]                                                   # անջատվածը այլևս չի ստանում
    a.click("[data-tglink=garage]")
    code = re.search(r"start=([A-Za-z0-9_-]+)", a.locator("#tgInfo-garage a").get_attribute("href")).group(1)
    press_start(999, code)
    expect(a.locator("#main")).to_contain_text("✓ Միացված է", timeout=10000)
    a.screenshot(path="shots/tg_garage_owner.png", full_page=True)
    sent.clear(); ctx.request.post(BASE + "/requests", data={"name": "Հայկ", "phone": "+374 91 888888", "garage_id": 2})
    assert {c for c, _ in texts()} == {777, 999}
    print("Սեփականատերը ինքն է միացնում և անջատում Telegram-ը ✓")
    b.close()

print("JS սխալներ:", errors or "չկան")
server.should_exit = True
