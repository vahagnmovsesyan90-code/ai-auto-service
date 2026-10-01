"""Դիտարկչային end-to-end թեստ (իրական Chromium). Պահանջում է՝ pip install playwright && playwright install chromium
Գործարկում՝ python test_browser.py   (սերվերը ինքն է բարձրացնում ժամանակավոր բազայով, նկարները՝ ./shots/)"""
import os, subprocess, sys, tempfile, time, urllib.request

PORT = 8770
tmp = tempfile.mkdtemp()
env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
env.update(ADMIN_PASSWORD="pw", AUTOSERVICE_DB=os.path.join(tmp, "e2e.db"))
os.makedirs("shots", exist_ok=True)
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "api:app", "--port", str(PORT)], env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=os.path.dirname(os.path.abspath(__file__)))
for _ in range(40):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1); break
    except Exception:
        time.sleep(0.5)
try:
    import json, urllib.request
    from playwright.sync_api import sync_playwright, expect

    BASE = "http://127.0.0.1:8770"
    errors = []
    def api(path): return json.load(urllib.request.urlopen(BASE + path))

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1100, "height": 800})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)

        # ================= CHAT =================
        page.goto(BASE + "/app")
        expect(page.locator(".m.bot").first).to_contain_text("Բարև")
        page.get_by_role("button", name="Արգելակելիս ճռռոց է լսվում").click()
        expect(page.locator(".m.bot").nth(1)).to_contain_text("14,000")
        expect(page.locator("#mode")).to_contain_text("Պարզ ռեժիմ")
        assert page.locator("#hint").is_hidden()                              # հուշումները թաքնվում են
        page.fill("#in", "օդորակիչը չի սառեցնում"); page.press("#in", "Enter")
        expect(page.locator(".m.bot").nth(2)).to_contain_text("Օդորակիչի լիցքավորում")
        page.fill("#in", "բլա բլա"); page.click("#send")
        expect(page.locator(".m.bot").nth(3)).to_contain_text("Չհասկացա")
        assert page.locator(".m.me").count() == 3
        page.screenshot(path="shots/chat.png")
        print("Chat-ը (հարցում, Enter, հուշումներ, ռեժիմ) ✓")

        # հայտի ձևը
        page.click("#reqBtn"); expect(page.locator("#dlg")).to_be_visible()
        expect(page.locator("#rg option")).to_have_count(4)                   # «ընտրված չէ» + 3 գարաժ
        expect(page.locator("#rs option")).to_have_count(7)
        page.click("#rsend"); expect(page.locator("#rerr")).to_contain_text("Լրացրեք")
        page.fill("#rp", "abcdefgh"); page.fill("#rn", "Արամ")
        page.click("#rsend"); expect(page.locator("#rerr")).to_contain_text("Ստուգեք հեռախոսի")   # սերվերի 422
        page.fill("#rp", "+374 91 123456"); page.select_option("#rg", "2"); page.select_option("#rs", "5")
        page.fill("#rm", "Վաղը առավոտյան")
        page.screenshot(path="shots/dialog.png")
        page.click("#rsend")
        expect(page.locator("#dlg")).not_to_be_visible()
        expect(page.locator(".m.bot").last).to_contain_text("Հայտը ուղարկված է")
        print("Հայտի ձևը (վալիդացիա, ուղարկում) ✓")

        # ================= ԱԴՄԻՆ =================
        a = ctx.new_page()
        a.on("pageerror", lambda e: errors.append("admin pageerror: " + str(e)))
        a.on("console", lambda m: errors.append("admin console: " + m.text) if m.type == "error" and "401" not in m.text else None)
        a.goto(BASE + "/panel")
        expect(a.locator("#login")).to_be_visible(); assert a.locator("#app").is_hidden()
        a.fill("#pw", "wrong"); a.click("#go")
        expect(a.locator("#toast")).to_contain_text("Սխալ մուտքանուն կամ գաղտնաբառ"); expect(a.locator("#login")).to_be_visible()
        a.fill("#pw", "pw"); a.press("#pw", "Enter")
        expect(a.locator("#app")).to_be_visible()
        print("Մուտք (սխալ/ճիշտ գաղտնաբառ) ✓")

        # Հայտեր
        expect(a.locator("#main")).to_contain_text("Արամ"); expect(a.locator("#main")).to_contain_text("+374 91 123456")
        expect(a.locator("#main")).to_contain_text("Garage Kentron"); expect(a.locator("#main")).to_contain_text("Վաղը առավոտյան")
        a.screenshot(path="shots/admin_requests.png")
        a.get_by_role("button", name="Մշակված է").click()
        expect(a.get_by_role("button", name="Վերաբացել")).to_be_visible()
        print("Հայտերի բաժին ✓")

        # Գարաժներ. գին
        a.click("[data-t=garages]")
        expect(a.locator(".chip")).to_have_count(4)                            # 3 գարաժ + «Նոր»
        a.locator("[data-price='2']").fill("16000"); a.locator("[data-price='2']").press("Tab")
        expect(a.locator("#toast")).to_contain_text("Գինը պահպանվեց")
        offers = api("/services/2/garages"); assert [o["price"] for o in offers][:2] == [14000, 16000] or 16000 in [o["price"] for o in offers], offers
        assert next(o for o in offers if o["garage"]["id"] == 1)["price"] == 16000
        # ծառայությունը հանել
        a.locator("[data-on='3']").uncheck()
        expect(a.locator("#toast")).to_contain_text("հանվեց")
        assert all(o["garage"]["id"] != 1 for o in api("/services/3/garages"))
        a.locator("[data-on='3']").check(); a.locator("[data-price='3']").fill("6500"); a.locator("[data-price='3']").press("Tab")
        expect(a.locator("#toast")).to_contain_text("Գինը պահպանվեց")
        assert next(o for o in api("/services/3/garages") if o["garage"]["id"] == 1)["price"] == 6500
        print("Գներ (փոփոխել, հանել, վերադարձնել) ✓")

        # Ժամեր
        a.locator("[data-ho='5']").uncheck()                                    # շաբաթ՝ փակ
        a.locator("[data-hf='0']").fill("07:30")
        a.click("#saveH"); expect(a.locator("#toast")).to_contain_text("Ժամերը պահպանվեցին")
        h = api("/garages/1")["hours"]
        assert "Շբթ" not in [x["day"] for x in h] and h[0]["open"].startswith("07:30"), h
        a.locator("[data-hf='1']").fill("20:00"); a.locator("[data-ht='1']").fill("10:00")   # անվավեր
        a.click("#saveH"); expect(a.locator("#toast")).to_contain_text("շուտ")
        print("Ժամեր (պահպանում, վալիդացիա) ✓")

        # Խմբագրել գարաժ + ավելացնել + ջնջել
        a.fill("#gn", "AutoPro Plus"); a.click("#saveG")
        expect(a.locator(".chip.on")).to_have_text("AutoPro Plus"); assert api("/garages/1")["name"] == "AutoPro Plus"
        a.click("#addG"); expect(a.locator(".chip")).to_have_count(5); expect(a.locator("#gn")).to_have_value("Նոր գարաժ")
        a.click("#delG"); expect(a.locator("#delG")).to_have_text("Հաստատել ջնջումը")   # առաջին սեղմում
        assert len(api("/garages")) == 4                                                  # դեռ չի ջնջվել
        a.click("#delG"); expect(a.locator(".chip")).to_have_count(4); assert len(api("/garages")) == 3
        a.screenshot(path="shots/admin_garages.png", full_page=True)
        print("Գարաժ (խմբագրել, ավելացնել, երկքայլ ջնջում) ✓")

        # Կատալոգ
        a.click("[data-t=catalog]")
        a.fill("#cn", "Լուսարձակների փայլեցում"); a.fill("#cc", "Դետեյլինգ"); a.fill("#ck", "լուսարձակ, փայլ"); a.click("#addC")
        expect(a.locator("tr[data-sid]")).to_have_count(7)
        row = a.locator("tr[data-sid='7']"); expect(row.locator("[data-f=n]")).to_have_value("Լուսարձակների փայլեցում"); row.locator("[data-f=k]").fill("լուսարձակ, փայլ, մթագնել"); row.locator("[data-savs]").click()
        expect(a.locator("#toast")).to_contain_text("Պահպանվեց")
        row.locator("[data-dels]").click(); expect(row.locator("[data-dels]")).to_have_text("Հաստատել ջնջումը")
        row.locator("[data-dels]").click(); expect(a.locator("tr[data-sid='7']")).to_have_count(0)
        print("Կատալոգ (ավելացնել, խմբագրել, ջնջել) ✓")

        # --- Գարաժների մուտք. ադմինը ստեղծում է երկու գարաժի մուտք և նշանակում հայտ ---
        a.click("[data-t=garages]")
        a.get_by_role("button", name="Garage Kentron").click()
        a.fill("#ap", "123"); a.fill("#al", "kentron"); a.click("#saveAcc")
        expect(a.locator("#toast")).to_contain_text("Սխալ" if False else "Անվավեր")        # կարճ գաղտնաբառը մերժվում է
        a.fill("#ap", "kentron-pass-1"); a.click("#saveAcc")
        expect(a.locator("#toast")).to_contain_text("Մուտքը պահպանվեց")
        expect(a.locator("#main")).to_contain_text("Մուտքանուն՝ kentron")
        a.get_by_role("button", name="AutoPro Plus").click()
        a.fill("#al", "autopro"); a.fill("#ap", "autopro-pass-1"); a.click("#saveAcc")
        expect(a.locator("#main")).to_contain_text("Մուտքանուն՝ autopro")                   # սպասում ենք իրական արդյունքին, ոչ հին toast-ին
        a.get_by_role("button", name="Speed Service").click()
        a.fill("#al", "kentron"); a.fill("#ap", "another-pass-1"); a.click("#saveAcc")
        expect(a.locator("#toast")).to_contain_text("զբաղված")                               # կրկնվող մուտքանուն
        ctx.request.post(BASE + "/requests", data={"name": "Վահե", "phone": "+374 99 111222", "message": "առանց գարաժի"})
        a.reload(); expect(a.locator("#app")).to_be_visible()
        row = a.locator("tr", has_text="Վահե")
        expect(row.locator("select")).to_have_value("")
        row.locator("select").select_option(label="AutoPro Plus")
        expect(a.locator("#toast")).to_contain_text("նշանակվեց")
        a.screenshot(path="shots/admin_assign.png")
        print("Գարաժների մուտք և հայտի նշանակում (ադմին) ✓")

        # Session և logout
        a.reload(); expect(a.locator("#app")).to_be_visible()                  # sessionStorage-ը պահում է մուտքը
        a.click("#out"); expect(a.locator("#login")).to_be_visible()
        a.reload(); expect(a.locator("#login")).to_be_visible()
        print("Session, դուրս գալ ✓")

        # --- Գարաժի սեփականատերը տեսնում է միայն իրենը ---
        a.fill("#lg", "autopro"); a.fill("#pw", "wrong-pass"); a.click("#go")
        expect(a.locator("#toast")).to_contain_text("Սխալ մուտքանուն կամ գաղտնաբառ"); expect(a.locator("#login")).to_be_visible()
        a.fill("#pw", "autopro-pass-1"); a.press("#pw", "Enter")
        expect(a.locator("#app")).to_be_visible()
        expect(a.locator("#who")).to_have_text("AutoPro Plus")
        expect(a.locator("#tabC")).to_be_hidden(); expect(a.locator("#tabG")).to_have_text("Իմ գարաժը")
        expect(a.locator("#main")).to_contain_text("Վահե"); expect(a.locator("#main")).not_to_contain_text("Արամ")
        assert a.locator("[data-assign]").count() == 0 and a.locator("[data-tglink='admin']").count() == 0
        a.screenshot(path="shots/garage_requests.png")
        a.click("[data-t=garages]")
        assert a.locator(".chip").count() == 0 and a.locator("#delG").count() == 0 and a.locator("#saveAcc").count() == 0 and a.locator("#addG").count() == 0
        expect(a.locator("#gn")).to_have_value("AutoPro Plus")
        expect(a.locator("#main")).to_contain_text("Telegram-ը դեռ կարգավորված չէ")
        a.locator("[data-price='1']").fill("8800"); a.locator("[data-price='1']").press("Tab")
        expect(a.locator("#toast")).to_contain_text("Գինը պահպանվեց")
        assert next(o for o in api("/services/1/garages") if o["garage"]["name"] == "AutoPro Plus")["price"] == 8800
        a.screenshot(path="shots/garage_panel.png", full_page=True)
        a.click("#out")
        a.fill("#lg", "kentron"); a.fill("#pw", "kentron-pass-1"); a.click("#go")
        expect(a.locator("#who")).to_have_text("Garage Kentron")
        expect(a.locator("#main")).to_contain_text("Արամ"); expect(a.locator("#main")).not_to_contain_text("Վահե")
        a.reload(); expect(a.locator("#who")).to_have_text("Garage Kentron")             # session-ը պահում է դերը
        a.click("#out")
        print("Գարաժի սեփականատիրոջ պանել (միայն իրենը, առանց ադմինի գործիքների) ✓")

        # Մոբայլ
        m = b.new_context(viewport={"width": 375, "height": 720}).new_page()
        m.goto(BASE + "/app"); m.screenshot(path="shots/chat_mobile.png")
        assert m.evaluate("document.documentElement.scrollWidth") <= 376, "chat-ը հորիզոնական scroll ունի մոբայլում"
        m.goto(BASE + "/panel"); m.fill("#pw", "pw"); m.click("#go"); expect(m.locator("#app")).to_be_visible()
        m.click("[data-t=garages]"); m.screenshot(path="shots/admin_mobile.png")
        print("Մոբայլ տեսք ✓ (admin scrollWidth=%s)" % m.evaluate("document.documentElement.scrollWidth"))
        b.close()

    print("JS/console սխալներ:", errors or "չկան")

finally:
    server.terminate()
