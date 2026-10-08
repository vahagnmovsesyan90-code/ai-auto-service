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
        first = page.locator(".m.bot").nth(1)
        expect(first).to_contain_text("14,000"); expect(first.locator(".gc")).to_have_count(3)
        expect(first.locator(".gc").first).to_contain_text("Speed Service")                 # ամենաէժանը առաջինն է
        expect(first.locator(".gc").first).to_contain_text("Դեռ գնահատականներ չկան")
        expect(first.locator(".gc").first.get_by_role("button", name="Թողնել հայտ")).to_be_visible()
        assert page.locator("#reqBtn").count() == 0                                          # վերևի ընդհանուր կոճակը վերացել է
        expect(page.locator("#mode")).to_contain_text("Պարզ ռեժիմ")
        assert page.locator("#hint").is_hidden()                              # հուշումները թաքնվում են
        first.locator(".gc").first.get_by_role("button", name="Կարծիքներ").click()
        expect(first.locator(".revs").first).to_contain_text("Կարծիքներ դեռ չկան")
        page.fill("#in", "օդորակիչը չի սառեցնում"); page.press("#in", "Enter")
        expect(page.locator(".m.bot").nth(2)).to_contain_text("Օդորակիչի լիցքավորում")
        expect(page.locator(".m.bot").nth(2).locator(".gc")).to_have_count(1)
        page.fill("#in", "բլա բլա"); page.click("#send")
        expect(page.locator(".m.bot").nth(3)).to_contain_text("Չհասկացա"); expect(page.locator(".m.bot").nth(3).locator(".gc")).to_have_count(0)
        assert page.locator(".m.me").count() == 3
        page.screenshot(path="shots/chat.png")
        print("Chat-ը (հարցում, քարտեր, Enter, հուշումներ, ռեժիմ) ✓")

        # «Թողնել հայտ»՝ հենց Garage Kentron-ի քարտից (գարաժը և ծառայությունը արդեն լրացված են)
        page.fill("#in", "կախոցի թակոց"); page.press("#in", "Enter")
        susp = page.locator(".m.bot").nth(4)
        expect(susp.locator(".gc")).to_have_count(2)
        susp.get_by_role("button", name="Գնահատականով").click()                              # դասավորման փոխարկիչ
        expect(susp.locator(".sort button.on")).to_have_text("Գնահատականով")
        susp.locator(".gc", has_text="Garage Kentron").get_by_role("button", name="Թողնել հայտ").click()
        expect(page.locator("#dlg")).to_be_visible(); expect(page.locator("#dlgFor")).to_have_text("Garage Kentron · Կախոցի ստուգում")
        assert page.locator("#rg").count() == 0                                              # գարաժ ընտրելու դաշտ այլևս չկա
        page.click("#rsend"); expect(page.locator("#rerr")).to_contain_text("Լրացրեք")
        page.fill("#rp", "abcdefgh"); page.fill("#rn", "Արամ")
        page.click("#rsend"); expect(page.locator("#rerr")).to_contain_text("Ստուգեք հեռախոսի")   # սերվերի 422
        page.fill("#rp", "+374 91 123456"); page.fill("#rm", "Վաղը առավոտյան")
        page.screenshot(path="shots/dialog.png")
        page.click("#rsend")
        expect(page.locator("#dlg")).not_to_be_visible()
        sent_msg = page.locator(".m.bot").last
        expect(sent_msg).to_contain_text("Հայտը ուղարկված է «Garage Kentron»-ին")
        review_url = sent_msg.locator("a.lnk").get_attribute("href")
        assert review_url.startswith("/review/") and len(review_url) > 20, review_url
        assert len(page.evaluate("JSON.parse(localStorage.getItem('pending_reviews'))")) == 1
        page.screenshot(path="shots/chat_after_request.png")
        print("«Թողնել հայտ» քարտից (լրացված գարաժ/ծառայություն, վալիդացիա, գնահատման հղում) ✓")

        # --- Հավելվածը փակում և նորից բացում ենք. խոսակցությունը և գնահատման հղումը չեն ջնջվում ---
        page.reload()
        expect(page.locator(".m.bot").last).to_contain_text("Հայտը ուղարկված է «Garage Kentron»-ին")
        expect(page.locator(".m.bot").last.locator("a.lnk")).to_have_attribute("href", review_url)   # նույն հղումը
        expect(page.locator(".m.me")).to_have_count(4)                                       # նախորդ հաղորդագրությունները
        expect(page.locator(".gc").first).to_be_visible()                                    # քարտերը նույնպես
        assert page.locator("#hint").is_hidden()
        expect(page.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")                      # մշտական ցուցակ՝ նույնիսկ առանց չատի
        page.click("#mineBtn")
        expect(page.locator("#mineList")).to_contain_text("Garage Kentron")
        expect(page.locator("#mineList a")).to_have_attribute("href", review_url)
        page.screenshot(path="shots/my_requests.png"); page.click("#mineClose")
        page.fill("#in", "օդորակիչ"); page.press("#in", "Enter")                             # խոսակցությունը շարունակվում է
        expect(page.locator(".m.me")).to_have_count(5)
        expect(page.locator(".m.bot").last).to_contain_text("Օդորակիչի լիցքավորում")
        # «Նոր խոսակցություն». մաքրում է չատը, բայց ոչ «Իմ հայտերը»
        page.click("#newChat"); expect(page.locator("#newChat")).to_have_text("Հաստատե՞լ")
        page.click("#newChat")
        expect(page.locator(".m.bot").first).to_contain_text("Բարև"); expect(page.locator(".m.me")).to_have_count(0)
        expect(page.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")
        print("Փակել/նորից բացել. խոսակցությունը, քարտերը և «Իմ հայտերը» մնում են ✓")

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
        stage = a.locator("[data-stage]").first
        expect(stage).to_have_value("new")
        stage.select_option("called")
        expect(a.locator("#toast")).to_contain_text("Փուլը պահպանվեց"); expect(a.locator("[data-stage]").first).to_have_value("called")
        # «Հրաժարվեց»-ը պահանջում է պատճառ. մինչև ընտրելը չի պահվում
        a.locator("[data-stage]").first.select_option("declined")
        expect(a.locator("[data-reason]").first).to_be_visible(); expect(a.locator("#toast")).to_contain_text("Ընտրեք հրաժարման պատճառը")
        a.reload(); expect(a.locator("[data-stage]").first).to_have_value("called")           # դեռ չի պահվել
        a.locator("[data-stage]").first.select_option("declined")
        a.locator("[data-reason]").first.select_option("price")
        expect(a.locator("#toast")).to_contain_text("Փուլը պահպանվեց")
        expect(a.locator("[data-stage]").first).to_have_value("declined"); expect(a.locator("[data-reason]").first).to_have_value("price")
        a.locator("[data-stage]").first.select_option("booked")                               # պատճառը թաքնվում է
        expect(a.locator("[data-reason]").first).to_be_hidden()
        a.locator("[data-stage]").first.select_option("declined"); a.locator("[data-reason]").first.select_option("price")
        expect(a.locator("[data-stage]").first).to_have_value("declined")
        # հաշվետվություն
        a.click("[data-t=report]")
        expect(a.locator(".card b").first).to_have_text("1")                                  # 1 հայտ այս ամսում
        expect(a.locator("#main")).to_contain_text("Ինչու են հրաժարվում"); expect(a.locator("#main")).to_contain_text("Թանկ է")
        expect(a.locator("#main")).to_contain_text("Արձագանքման ժամանակ")
        a.screenshot(path="shots/admin_report.png", full_page=True)
        a.locator("#rm").fill("2020-01")
        expect(a.locator(".card b").first).to_have_text("0"); expect(a.locator("#main")).to_contain_text("հրաժարումներ չկան")
        a.click("[data-t=requests]")
        print("Հայտերի փուլեր, հրաժարման պատճառ, հաշվետվություն ✓")

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
        expect(row.locator("[data-assign]")).to_have_value("")
        row.locator("[data-assign]").select_option(label="AutoPro Plus")
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
        a.click("[data-t=report]")                                                           # գարաժը տեսնում է միայն իր հաշվետվությունը
        expect(a.locator(".card b").first).to_have_text("1"); expect(a.locator("#main table").first.locator("tr")).to_have_count(2)
        expect(a.locator("#main")).to_contain_text("AutoPro Plus"); expect(a.locator("#main")).not_to_contain_text("Garage Kentron")
        a.click("[data-t=requests]")
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

        # --- Վարորդի գնահատում ---
        v = ctx.new_page()
        v.on("pageerror", lambda e: errors.append("review pageerror: " + str(e)))
        v.goto(BASE + review_url)
        expect(v.locator("#box h1")).to_have_text("Garage Kentron"); expect(v.locator("#box")).to_contain_text("Կախոցի ստուգում")
        v.get_by_role("button", name="Այո, գնացի").click()
        v.click("#send"); expect(v.locator("#err")).to_contain_text("աստղերի")               # առանց աստղերի չի ուղարկվում
        v.get_by_role("radio", name="4 աստղ").click()
        expect(v.get_by_role("radio", name="4 աստղ")).to_have_attribute("aria-checked", "true")
        v.fill("#comment", "Արագ և ազնիվ <b>bold</b>"); v.fill("#dname", "Արամ")
        v.screenshot(path="shots/review_form.png")
        v.click("#send"); expect(v.locator("#box")).to_contain_text("Շնորհակալություն")
        v.reload(); expect(v.locator("#box")).to_contain_text("արդեն թողնված")                # մեկ հայտ = մեկ կարծիք
        v.goto(BASE + "/review/not-a-real-token"); expect(v.locator("#box")).to_contain_text("անվավեր")
        assert [x["done"] for x in page.evaluate("JSON.parse(localStorage.getItem('pending_reviews')||'[]')")] == [True]   # նշվել է որպես գնահատված

        # chat-ում քարտը ցույց է տալիս գնահատականը և կարծիքը (HTML-ը էկրանավորված է)
        page.reload(); page.fill("#in", "կախոցի թակոց"); page.press("#in", "Enter")
        kc = page.locator(".m.bot").last.locator(".gc", has_text="Garage Kentron")
        expect(kc).to_contain_text("★ 4.0"); expect(kc).to_contain_text("1 կարծիք (քիչ կարծիք)")
        expect(page.locator(".m.bot").last.locator(".gc", has_text="Speed Service")).to_contain_text("Դեռ գնահատականներ չկան")
        kc.get_by_role("button", name="Կարծիքներ").click()
        expect(kc.locator(".revs")).to_contain_text("Արագ և ազնիվ <b>bold</b>"); expect(kc.locator(".revs")).to_contain_text("Արամ")
        assert kc.locator(".revs b", has_text="bold").count() == 0                           # XSS չկա
        page.screenshot(path="shots/chat_ratings.png")

        # երկրորդ հայտ (Speed Service)՝ հիշեցման բաններ և «չգնացի»
        page.evaluate("localStorage.setItem('remind_after_ms','0')")
        spd = page.locator(".m.bot").last.locator(".gc", has_text="Speed Service")
        spd.get_by_role("button", name="Թողնել հայտ").click()
        page.fill("#rn", "Նարե"); page.fill("#rp", "+374 99 765432"); page.click("#rsend")
        expect(page.locator("#dlg")).not_to_be_visible()
        url2 = page.locator(".m.bot").last.locator("a.lnk").get_attribute("href")
        page.reload()
        expect(page.locator(".rb")).to_have_count(1); expect(page.locator(".rb")).to_contain_text("Speed Service")
        expect(page.locator(".rb a")).to_have_attribute("href", url2)
        page.locator(".rb").get_by_role("button", name="Փակել").click(); expect(page.locator(".rb")).to_have_count(0)
        v.goto(BASE + url2); v.get_by_role("button", name="Ոչ, չգնացի").click()
        v.click("#send"); expect(v.locator("#err")).to_contain_text("պատճառը")
        v.select_option("#reason", "price"); v.click("#send"); expect(v.locator("#box")).to_contain_text("Շնորհակալություն")
        page.reload(); expect(page.locator("#mineBtn")).to_have_text("Իմ հայտերը")                 # այլևս չգնահատված չկա
        page.click("#mineBtn"); expect(page.locator("#mineList .done")).to_have_count(2); expect(page.locator("#mineList a")).to_have_count(0)
        page.click("#mineClose")
        print("Վարորդի գնահատում (այո/ոչ, մեկանգամյա, հիշեցում, քարտերում վարկանիշ) ✓")

        # --- Ադմինը տեսնում է կարծիքները և թաքցնում է մեկը ---
        a.fill("#lg", ""); a.fill("#pw", "pw"); a.click("#go"); expect(a.locator("#app")).to_be_visible()
        a.click("[data-t=reviews]")
        expect(a.locator("#main")).to_contain_text("★ 4.0"); expect(a.locator("#main")).to_contain_text("Արագ և ազնիվ")
        expect(a.locator("#main")).to_contain_text("Չգնաց՝ Թանկ է")                          # ադմինը տեսնում է նաև «չգնացի»-ները
        a.get_by_role("button", name="Թաքցնել").click(); expect(a.locator("#toast")).to_contain_text("Ընտրեք թաքցնելու պատճառը")
        a.locator("[data-hr]").select_option("Կեղծ"); a.get_by_role("button", name="Թաքցնել").click()
        expect(a.locator("#main")).to_contain_text("Թաքցված՝ Կեղծ")
        page.reload(); page.fill("#in", "կախոցի թակոց"); page.press("#in", "Enter")
        expect(page.locator(".m.bot").last.locator(".gc", has_text="Garage Kentron")).to_contain_text("Դեռ գնահատականներ չկան")   # թաքցվածը չի հաշվվում
        a.click("[data-t=report]"); expect(a.locator("#main")).to_contain_text("Վարորդի հաստատած այցեր")
        a.click("#out")
        # գարաժի սեփականատերը՝ միայն իր հրապարակային կարծիքները, առանց թաքցնելու հնարավորության
        a.fill("#lg", "kentron"); a.fill("#pw", "kentron-pass-1"); a.click("#go"); expect(a.locator("#who")).to_have_text("Garage Kentron")
        a.click("[data-t=reviews]")
        expect(a.locator("#main")).to_contain_text("Կարծիքներ դեռ չկան"); expect(a.locator("#main")).not_to_contain_text("Չգնաց")
        assert a.locator("[data-hide]").count() == 0
        a.click("#out")
        print("Ադմինի մոդերացիա, գարաժի տեսածը ✓")

        # --- Եթե դիտարկիչը արգելում է localStorage-ը (private ռեժիմ և այլն) ---
        blocked = b.new_context(viewport={"width": 1000, "height": 800})
        blocked.add_init_script("Object.defineProperty(window, 'localStorage', {get() { throw new DOMException('denied', 'SecurityError'); }})")
        bp = blocked.new_page()
        bp.on("pageerror", lambda e: errors.append("blocked pageerror: " + str(e)))
        bp.goto(BASE + "/app"); bp.fill("#in", "արգելակ ճռռոց"); bp.press("#in", "Enter")
        expect(bp.locator(".gc").first).to_be_visible()
        bp.locator(".gc").first.get_by_role("button", name="Թողնել հայտ").click()
        bp.fill("#rn", "Կարեն"); bp.fill("#rp", "+374 91 987654"); bp.click("#rsend")
        expect(bp.locator("#dlg")).not_to_be_visible()
        expect(bp.locator(".stwarn")).to_contain_text("չի թույլատրում պահել տվյալներ")           # վարորդին ազնվորեն ասում ենք
        link_blocked = bp.locator(".m.bot").last.locator("a.lnk").get_attribute("href")
        assert "#h=" in bp.url and link_blocked.split("/")[-1] in bp.url, bp.url                     # հղումը պահվել է հասցեագոտում
        bp.reload()                                                                                   # refresh առանց localStorage-ի
        expect(bp.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")                                # հղումը չկորավ
        bp.click("#mineBtn"); expect(bp.locator("#mineList a")).to_have_attribute("href", link_blocked)
        bp.screenshot(path="shots/storage_blocked.png")
        bp.click("#mineClose"); blocked.close()
        print("localStorage-ը արգելված է. նախազգուշացում + հղումը չի կորչում refresh-ից հետո ✓")

        # --- Refresh պատասխանի սպասման ժամանակ. անպատասխան հարցը վերադառնում է մուտքի դաշտ ---
        page.evaluate("""localStorage.setItem('chat_state_v1', JSON.stringify({ts: Date.now(),
            items: [{cls: 'me', text: 'թակոց կախոցից'}], history: [{role: 'user', content: 'թակոց կախոցից'}]}))""")
        page.reload()
        expect(page.locator("#in")).to_have_value("թակոց կախոցից")
        expect(page.locator(".m.bot").last).to_contain_text("պատասխանը չստացվեց")
        assert page.locator(".m.me").count() == 0
        page.evaluate("localStorage.removeItem('chat_state_v1')")
        print("Անպատասխան հարցի վերականգնում ✓")

        # --- Տեղադրվող հավելված (PWA) ---
        pw = ctx.new_page()
        pw.on("pageerror", lambda e: errors.append("pwa pageerror: " + str(e)))
        pw.goto(BASE + "/app"); pw.evaluate("localStorage.removeItem('chat_state_v1')")                    # մաքուր չատ՝ ողջույնով
        pw.goto(BASE + "/app")
        pw.wait_for_function("navigator.serviceWorker.ready.then(r => !!r.active)")                       # service worker-ը գրանցվել է
        assert pw.evaluate("document.querySelector('link[rel=manifest]').getAttribute('href')") == "/manifest-app.webmanifest"
        assert pw.evaluate("document.querySelector('meta[name=theme-color]').content") == "#1d2529"
        pw.reload(); pw.wait_for_function("!!navigator.serviceWorker.controller")                         # հիմա էջը վերահսկվում է SW-ով
        pw.goto(BASE + "/panel"); pw.wait_for_function("!!navigator.serviceWorker.controller")
        # «Տեղադրել հավելվածը» կոճակ. սկզբում թաքնված է, beforeinstallprompt-ից հետո երևում է
        pw.goto(BASE + "/app"); expect(pw.locator("#install")).to_be_hidden()
        pw.evaluate("""() => { const e = new Event('beforeinstallprompt'); e.prompt = () => { window.__prompted = true; };
                           e.userChoice = Promise.resolve({outcome: 'accepted'}); window.dispatchEvent(e); }""")
        expect(pw.locator("#install")).to_be_visible(); pw.click("#install")
        assert pw.evaluate("window.__prompted") is True; expect(pw.locator("#install")).to_be_hidden()
        # քեշում միայն էջերի «կեղևը» է, երբեք՝ API/անձնական տվյալները
        pw.goto(BASE + "/review/probe-token"); pw.wait_for_timeout(300)                                   # գաղտնի հղումով էջը չպետք է քեշավորվի
        pw.goto(BASE + "/panel"); pw.wait_for_timeout(300)
        pw.evaluate("fetch('/garages').then(r => r.json())")
        pw.evaluate("fetch('/admin/data', {headers: {Authorization: 'Bearer x'}})")
        cached = pw.evaluate("""async () => { const out = []; for (const k of await caches.keys()) { const c = await caches.open(k);
                              for (const r of await c.keys()) out.push(new URL(r.url).pathname); } return out.sort(); }""")
        assert cached == ["/app", "/panel"], cached
        print("PWA (service worker, տեղադրման կոճակ, քեշում միայն կեղևը) ✓")

        # Մոբայլ
        m = b.new_context(viewport={"width": 375, "height": 720}).new_page()
        m.goto(BASE + "/app"); m.fill("#in", "արգելակ ճռռոց"); m.press("#in", "Enter")
        expect(m.locator(".gc").first).to_be_visible(); m.screenshot(path="shots/chat_mobile.png")
        assert m.evaluate("document.documentElement.scrollWidth") <= 376, "chat-ը հորիզոնական scroll ունի մոբայլում"
        m.locator(".gc").first.get_by_role("button", name="Թողնել հայտ").click(); expect(m.locator("#dlg")).to_be_visible()
        assert m.evaluate("document.documentElement.scrollWidth") <= 376; m.click("#rcancel")
        m.goto(BASE + "/panel"); m.fill("#pw", "pw"); m.click("#go"); expect(m.locator("#app")).to_be_visible()
        m.click("[data-t=garages]"); m.screenshot(path="shots/admin_mobile.png")
        print("Մոբայլ տեսք ✓ (admin scrollWidth=%s)" % m.evaluate("document.documentElement.scrollWidth"))

        # --- Offline. իրոք անջատում ենք սերվերը (Playwright-ի set_offline-ը service worker-ի հարցումների վրա չի ազդում) ---
        server.terminate(); server.wait(timeout=15)
        pw.goto(BASE + "/app"); expect(pw.locator(".m.bot").first).to_contain_text("Բարև")                # քեշից
        pw.fill("#in", "արգելակ"); pw.press("#in", "Enter")
        expect(pw.locator(".m.bot").last).to_contain_text("սերվերը չպատասխանեց")                        # API-ն ազնվորեն ձախողվում է
        pw.goto(BASE + "/panel"); expect(pw.locator("#login")).to_be_visible()                           # գարաժի պանելի կեղևը քեշից
        pw.goto(BASE + "/review/some-token"); expect(pw.locator("body")).to_contain_text("Ինտերնետ կապ չկա")   # չայցելած էջ՝ «Կապ չկա»
        pw.screenshot(path="shots/offline.png")
        print("Offline (քեշավորված էջերը բացվում են, մնացածը՝ «Կապ չկա») ✓")
        b.close()

    print("JS/console սխալներ:", errors or "չկան")

finally:
    server.terminate()
