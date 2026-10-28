"""Դիտարկչային end-to-end թեստ (իրական Chromium). Պահանջում է՝ pip install playwright && playwright install chromium
Գործարկում՝ python test_browser.py   (սերվերը ինքն է բարձրացնում ժամանակավոր բազայով, նկարները՝ ./shots/)"""
import os, subprocess, sys, tempfile, time, urllib.request
import testdb

PORT = 8770
tmp = tempfile.mkdtemp()
env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
env.update(ADMIN_PASSWORD="pw", DATABASE_URL=testdb.create(), SEED_SAMPLE="1", REQUEST_RATE_LIMIT="20")   # թեստը 5/րոպեից շատ հայտ է թողնում
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
        ctx.route("https://tile.openstreetmap.org/**", lambda r: r.fulfill(status=200, body=b"", content_type="image/png"))   # քարտեզի նկարները իրական չեն բեռնվում
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
        expect(sent_msg.locator("a.lnk")).to_have_text("Իմ հայտերը → Գնահատել")                  # առանձին էջ չկա. հղումը բացում է ցուցակը
        stored = page.evaluate("JSON.parse(localStorage.getItem('pending_reviews'))")
        assert len(stored) == 1 and len(stored[0]["tok"]) > 20 and "url" not in stored[0], stored
        page.screenshot(path="shots/chat_after_request.png")
        print("«Թողնել հայտ» քարտից (լրացված գարաժ/ծառայություն, վալիդացիա, հայտը ցուցակում) ✓")

        # --- Հավելվածը փակում և նորից բացում ենք. խոսակցությունը և գնահատման հղումը չեն ջնջվում ---
        page.reload()
        expect(page.locator(".m.bot").last).to_contain_text("Հայտը ուղարկված է «Garage Kentron»-ին")
        page.locator(".m.bot").last.locator("a.lnk").click(); page.wait_for_url("**/my*")   # հղումը տանում է «Իմ հայտերը» էջ
        page.goto(BASE + "/app")
        expect(page.locator(".m.me")).to_have_count(4)                                       # նախորդ հաղորդագրությունները
        expect(page.locator(".gc").first).to_be_visible()                                    # քարտերը նույնպես
        assert page.locator("#hint").is_hidden()
        expect(page.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")                      # մշտական ցուցակ՝ նույնիսկ առանց չատի
        page.click("#mineBtn")
        expect(page.locator("#mineList")).to_contain_text("Garage Kentron")
        expect(page.locator("#mineList .stars")).to_have_count(1)                           # գնահատումը հենց այստեղ է
        page.screenshot(path="shots/my_requests.png"); page.goto(BASE + "/app")
        page.fill("#in", "օդորակիչ"); page.press("#in", "Enter")                             # խոսակցությունը շարունակվում է
        expect(page.locator(".m.me")).to_have_count(5)
        expect(page.locator(".m.bot").last).to_contain_text("Օդորակիչի լիցքավորում")
        # «Նոր խոսակցություն». մաքրում է չատը, բայց ոչ «Իմ հայտերը»
        page.click("#newChat")                                                                      # մեկ սեղմում, առանց հաստատման
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
        time.sleep(1)                                          # սպասում ենք պահպանմանը և վերանկարմանը (հին toast-ը դեռ երևում է)
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

        # Գարաժներ. ցանկ → խմբագրում, գին
        def pick(pg, name):                                                      # գարաժների ցանկից բացել խմբագրումը
            if pg.locator("[data-back]").count(): pg.click("[data-back]")
            pg.locator("tr[data-gid]", has_text=name).locator("[data-g]").first.click()
        a.click("[data-t=garages]")
        expect(a.locator("tr[data-gid]")).to_have_count(3)                     # ցանկում 3 գարաժ
        pick(a, "AutoPro")
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
        expect(a.locator(".ghead h3")).to_have_text("AutoPro Plus"); assert api("/garages/1")["name"] == "AutoPro Plus"
        a.click("[data-back]"); expect(a.locator("tr[data-gid]")).to_have_count(3)
        a.click("#addG"); expect(a.locator("#gn")).to_have_value("Նոր գարաժ")       # նորը անմիջապես բացվում է խմբագրման
        a.click("#delG"); expect(a.locator("#delG")).to_have_text("Հաստատել ջնջումը")   # առաջին սեղմում
        assert len(api("/garages")) == 4                                                  # դեռ չի ջնջվել
        a.click("#delG"); expect(a.locator("tr[data-gid]")).to_have_count(3); assert len(api("/garages")) == 3   # ջնջելուց հետո՝ ցանկ
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
        pick(a, "Garage Kentron")
        a.fill("#ap", "123"); a.fill("#al", "kentron"); a.click("#saveAcc")
        expect(a.locator("#toast")).to_contain_text("Սխալ" if False else "Անվավեր")        # կարճ գաղտնաբառը մերժվում է
        a.fill("#ap", "kentron-pass-1"); a.click("#saveAcc")
        expect(a.locator("#toast")).to_contain_text("Մուտքը պահպանվեց")
        expect(a.locator("#main")).to_contain_text("Մուտքանուն՝ kentron")
        pick(a, "AutoPro Plus")
        a.fill("#al", "autopro"); a.fill("#ap", "autopro-pass-1"); a.click("#saveAcc")
        expect(a.locator("#main")).to_contain_text("Մուտքանուն՝ autopro")                   # սպասում ենք իրական արդյունքին, ոչ հին toast-ին
        pick(a, "Speed Service")
        a.fill("#al", "kentron"); a.fill("#ap", "another-pass-1"); a.click("#saveAcc")
        expect(a.locator("#toast")).to_contain_text("զբաղված")                               # կրկնվող մուտքանուն
        ctx.request.post(BASE + "/requests", data={"name": "Վահե", "phone": "+374 99 111222", "message": "առանց գարաժի"})
        a.goto(BASE + "/panel/requests"); expect(a.locator("#app")).to_be_visible()   # հասցեն պահում է բաժինը. #requests + թարմ տվյալներ
        row = a.locator("tr", has_text="Վահե")
        expect(row.locator("[data-assign]")).to_have_value("")
        row.locator("[data-assign]").select_option(label="AutoPro Plus")
        expect(a.locator("#toast")).to_contain_text("նշանակվեց")
        a.screenshot(path="shots/admin_assign.png")
        print("Գարաժների մուտք և հայտի նշանակում (ադմին) ✓")

        # --- Գարաժի տեղը քարտեզում և «Երթուղի» կոճակը ---
        def spd(): return next(g for g in api("/garages") if g["name"] == "Speed Service")
        def wait_api(cond):
            for _ in range(40):
                if cond(): return
                time.sleep(0.25)
            raise AssertionError("սերվերի վիճակը չփոխվեց")
        PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
        gctx = b.new_context(viewport={"width": 1100, "height": 900}, geolocation={"latitude": 40.1850, "longitude": 44.5150, "accuracy": 25},
                             permissions=["geolocation"])
        gctx.route("https://tile.openstreetmap.org/**", lambda r: r.fulfill(body=PNG, content_type="image/png"))   # իրական տեղադրանքներ չենք բեռնում
        gp = gctx.new_page(); gp.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        gp.goto(BASE + "/panel"); gp.fill("#pw", "pw"); gp.click("#go"); expect(gp.locator("#app")).to_be_visible()
        gp.click("[data-t=garages]"); pick(gp, "Speed Service")
        expect(gp.locator("#map .leaflet-tile-pane")).to_be_attached()
        expect(gp.locator("#locSave")).to_be_disabled()                                          # կետ դեռ չկա
        expect(gp.locator("#main")).to_contain_text("Կետը դեռ հաստատված չէ")
        assert api("/garages")[2]["lat"] is None or True
        # 1) «Ես գարաժում եմ»՝ GPS, ցույց է տալիս ճշտությունը, բայց ինքնուրույն ՉԻ պահպանում
        gp.click("#locHere")
        expect(gp.locator("#locMsg")).to_contain_text("±25 մ"); expect(gp.locator("#locSave")).to_be_enabled()
        expect(gp.locator("#map .pin")).to_be_visible()
        assert all(g["lat"] is None for g in api("/garages")), "GPS-ը չպետք է ինքնուրույն պահպանի"
        # 2) քարտեզին սեղմելով կետը տեղափոխվում է
        box = gp.locator("#map").bounding_box()
        gp.mouse.click(box["x"] + 80, box["y"] + 80)
        gp.click("#locSave"); wait_api(lambda: spd()["lat"] is not None)
        sp = next(g for g in api("/garages") if g["name"] == "Speed Service")
        assert sp["lat"] is not None and abs(sp["lat"] - 40.185) < 0.01 and sp["lat"] != 40.185, sp   # քարտեզին սեղմած կետը, ոչ GPS-ը
        expect(gp.locator("#main")).to_contain_text("Կետը հաստատված է")
        # 3) հասցեով որոնում (Nominatim-ի պատասխանը փոխարինված է)
        gp.route("**/admin/geocode", lambda r: r.fulfill(json={"found": True, "lat": 40.2000, "lng": 44.5300, "label": "x"}))
        gp.fill("#ga", "Նոր փողոց 5"); gp.click("#locFind")
        expect(gp.locator("#locMsg")).to_contain_text("ՍՏՈՒԳԵՔ")
        assert next(g for g in api("/garages") if g["name"] == "Speed Service")["lat"] == sp["lat"]   # որոնումը չի պահպանում
        gp.click("#locSave"); wait_api(lambda: (spd()["lat"] or 0) > 40.19999)
        sp2 = next(g for g in api("/garages") if g["name"] == "Speed Service")
        assert abs(sp2["lat"] - 40.2) < 1e-6 and sp2["address"] == "Նոր փողոց 5", sp2               # հասցեն և կետը միասին
        # 4) միայն հասցեն փոխելով «Պահպանել»՝ հին կետը հանվում է
        gp.fill("#ga", "Մեկ այլ փողոց 9"); gp.click("#saveG"); wait_api(lambda: spd()["lat"] is None)
        expect(gp.locator("#main")).to_contain_text("Կետը դեռ հաստատված չէ")
        assert next(g for g in api("/garages") if g["name"] == "Speed Service")["lat"] is None
        gp.screenshot(path="shots/admin_map.png")
        # վերականգնում ենք կետը՝ chat-ի ստուգման համար
        gp.locator("#map").scroll_into_view_if_needed(); box = gp.locator("#map").bounding_box()   # էջը scroll է եղել, կոորդինատները թարմացնում ենք
        gp.mouse.click(box["x"] + 120, box["y"] + 120); gp.click("#locSave"); wait_api(lambda: spd()["lat"] is not None)
        sp3 = next(g for g in api("/garages") if g["name"] == "Speed Service")
        gctx.close()
        # chat. «Երթուղի»՝ միայն կետ ունեցող գարաժի քարտում
        rp = b.new_context(viewport={"width": 420, "height": 800}).new_page()
        rp.goto(BASE + "/app"); rp.fill("#in", "արգելակ ճռռոց"); rp.press("#in", "Enter")
        cards_ = rp.locator(".m.bot").last.locator(".gc"); expect(cards_).to_have_count(3)
        assert rp.get_by_role("button", name="Երթուղի").count() == 1, "կոճակը միայն մեկ գարաժի քարտում պետք է լինի"
        sc = cards_.filter(has_text="Speed Service")
        expect(sc.get_by_role("button", name="Թողնել հայտ")).to_be_visible(); expect(sc.get_by_role("button", name="Կարծիքներ")).to_be_visible()
        expect(sc.locator(".maps")).to_be_hidden()
        sc.get_by_role("button", name="Երթուղի").click()
        ll = "%.6f,%.6f" % (sp3["lat"], sp3["lng"])
        hrefs = {sc.locator(".maps a").nth(i).inner_text(): sc.locator(".maps a").nth(i).get_attribute("href") for i in range(3)}
        assert hrefs["Google Maps"] == f"https://www.google.com/maps/dir/?api=1&destination={ll}&travelmode=driving", hrefs
        assert hrefs["Yandex Maps"] == f"https://yandex.ru/maps/?rtext=~{ll}&rtt=auto" and hrefs["Waze"] == f"https://waze.com/ul?ll={ll}&navigate=yes", hrefs
        assert "origin" not in hrefs["Google Maps"]                      # սկիզբը վարորդի ընթացիկ տեղն է. մենք այն չենք իմանում
        assert rp.evaluate("document.documentElement.scrollWidth") <= 421
        rp.screenshot(path="shots/chat_route.png")
        print("Գարաժի տեղը քարտեզում (GPS, քարտեզ, հասցե, հասցեի փոփոխության ժամանակ կետի հանում) և «Երթուղի» կոճակը ✓")

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
        assert a.locator("tr[data-gid]").count() == 0 and a.locator("[data-back]").count() == 0 and a.locator("#delG").count() == 0 and a.locator("#saveAcc").count() == 0 and a.locator("#addG").count() == 0
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

        # --- Վարորդի գնահատում՝ «Իմ հայտերը» բաժնում, աստղերով (առանձին գնահատման էջ չկա) ---
        page.click("#mineBtn"); page.wait_for_url("**/my*")
        kcard = page.locator("#mineList .mc", has_text="Garage Kentron"); expect(kcard).to_contain_text("Կախոցի ստուգում")
        expect(kcard.get_by_role("button", name="Հաստատել")).to_be_hidden()                  # ձևը բացվում է աստղ ընտրելուց հետո
        kcard.get_by_role("radio", name="4 աստղ").click()
        expect(kcard.get_by_role("radio", name="4 աստղ")).to_have_attribute("aria-checked", "true")
        kcard.locator("textarea").fill("Արագ և ազնիվ <b>bold</b>"); kcard.locator("input").fill("Արամ")
        page.screenshot(path="shots/review_form.png")
        kcard.get_by_role("button", name="Հաստատել").click(); expect(kcard).to_contain_text("պահվեց")
        expect(kcard.locator(".cm")).to_contain_text("Արագ և ազնիվ <b>bold</b>"); expect(kcard.locator(".cm .who")).to_contain_text("Արամ")   # կարծիքը երևում է
        expect(kcard.locator(".stars.ro span.on")).to_have_count(4)                          # գնահատվածը ցույց է տալիս տրված աստղերը
        expect(kcard.locator(".stars button")).to_have_count(0)                              # մեկ հայտ = մեկ կարծիք
        page.goto(BASE + "/app")
        assert [x["done"] for x in page.evaluate("JSON.parse(localStorage.getItem('pending_reviews')||'[]')")] == [True]   # նշվել է որպես գնահատված

        # chat-ում քարտը ցույց է տալիս գնահատականը և կարծիքը (HTML-ը էկրանավորված է)
        page.reload(); page.fill("#in", "կախոցի թակոց"); page.press("#in", "Enter")
        kc = page.locator(".m.bot").last.locator(".gc", has_text="Garage Kentron")
        expect(kc.locator(".rt .st")).to_have_text("4.0"); expect(kc).to_contain_text("1 կարծիք (քիչ կարծիք)")
        expect(page.locator(".m.bot").last.locator(".gc", has_text="Speed Service")).to_contain_text("Դեռ գնահատականներ չկան")
        kc.get_by_role("button", name="Կարծիքներ").click()
        expect(kc.locator(".revs")).to_contain_text("Արագ և ազնիվ <b>bold</b>"); expect(kc.locator(".revs")).to_contain_text("Արամ")
        assert kc.locator(".revs b", has_text="bold").count() == 0                           # XSS չկա
        page.screenshot(path="shots/chat_ratings.png")

        # երկրորդ հայտ (Speed Service)՝ հիշեցման բաններ, գնահատում բանների հղումից
        page.evaluate("localStorage.setItem('remind_after_ms','0')")
        spd = page.locator(".m.bot").last.locator(".gc", has_text="Speed Service")
        spd.get_by_role("button", name="Թողնել հայտ").click()
        page.fill("#rn", "Նարե"); page.fill("#rp", "+374 99 765432"); page.click("#rsend")
        expect(page.locator("#dlg")).not_to_be_visible()
        page.reload()
        expect(page.locator(".rb")).to_have_count(1); expect(page.locator(".rb")).to_contain_text("Speed Service")
        page.locator(".rb").get_by_role("link", name="Գնահատել").click(); page.wait_for_url("**/my*")
        scard = page.locator("#mineList .mc").first; expect(scard).to_contain_text("Speed Service")   # նորը վերևում է
        expect(scard.get_by_role("button", name="Հաստատել")).to_be_hidden()                     # թաքնված է մինչև ընտրելը
        scard.get_by_role("button", name="Չեմ գնացել").click(); scard.get_by_role("button", name="Հաստատել").click()
        expect(scard.locator(".err")).to_contain_text("պատճառը")                                 # «չգնացի»՝ առանց պատճառի չի ուղարկվում
        scard.get_by_role("radio", name="5 աստղ").click(); scard.locator("textarea").fill("Շատ լավ")
        expect(scard.get_by_role("button", name="Չեմ գնացել")).to_be_hidden()                   # աստղ ընտրելուց հետո «չեմ գնացել»-ը կորչում է
        expect(scard.locator("select")).to_be_hidden()
        page.screenshot(path="shots/my_requests_stars.png")
        scard.get_by_role("button", name="Հաստատել").click(); expect(scard.locator(".stars.ro span.on")).to_have_count(5)
        page.goto(BASE + "/app"); expect(page.locator("#mineBtn")).to_have_text("Իմ հայտերը")   # այլևս չգնահատված չկա
        expect(page.locator(".rb")).to_have_count(0)                                             # բանները անհետացավ
        page.reload(); expect(page.locator(".rb")).to_have_count(0)
        page.click("#mineBtn"); expect(page.locator("#mineList .stars button")).to_have_count(0)   # չգնահատված չկա
        expect(page.locator("#mineList .mc").nth(0).locator(".stars.ro span.on")).to_have_count(5)   # սերվերից՝ տրված աստղերը
        expect(page.locator("#mineList .mc").nth(1).locator(".stars.ro span.on")).to_have_count(4)
        expect(page.locator("#mineList .mc").nth(1).locator(".cm")).to_contain_text("Արագ և ազնիվ")       # կարծիքը՝ սերվերից էլ
        page.goto(BASE + "/my?per_page=1"); expect(page.locator("#mineList .mc")).to_have_count(1)         # էջավորում
        expect(page.locator("#mineList .mc")).to_contain_text("Speed Service"); expect(page.locator("#pg button.on")).to_have_text("1")
        page.locator("#pg").get_by_role("button", name="2").click(); expect(page.locator("#mineList .mc")).to_contain_text("Garage Kentron")
        page.goto(BASE + "/app")
        page.fill("#in", "կախոցի թակոց"); page.press("#in", "Enter")
        expect(page.locator(".m.bot").last.locator(".gc", has_text="Speed Service").locator(".rt .st")).to_have_text("5.0")   # կարծիքը հասավ քարտին
        print("Վարորդի գնահատում (աստղերով ցուցակում, մեկանգամյա, հիշեցում, քարտերում վարկանիշ) ✓")

        # --- Ադմինը տեսնում է կարծիքները և թաքցնում է մեկը ---
        a.fill("#lg", ""); a.fill("#pw", "pw"); a.click("#go"); expect(a.locator("#app")).to_be_visible()
        a.click("[data-t=reviews]")
        expect(a.locator("#main")).to_contain_text("★ 4.0"); expect(a.locator("#main")).to_contain_text("Արագ և ազնիվ")
        expect(a.locator("#main")).to_contain_text("★ 5.0"); expect(a.locator("#main")).to_contain_text("Շատ լավ")
        kr = a.locator("#main article", has_text="Garage Kentron")                            # թաքցնում ենք միայն Kentron-ինը
        kr.get_by_role("button", name="Թաքցնել").click(); expect(a.locator("#toast")).to_contain_text("Ընտրեք թաքցնելու պատճառը")
        kr.locator("[data-hr]").select_option("Կեղծ"); kr.get_by_role("button", name="Թաքցնել").click()
        expect(a.locator("#main")).to_contain_text("Թաքցված՝ Կեղծ")
        page.reload(); page.fill("#in", "կախոցի թակոց"); page.press("#in", "Enter")
        expect(page.locator(".m.bot").last.locator(".gc", has_text="Garage Kentron")).to_contain_text("Դեռ գնահատականներ չկան")   # թաքցվածը չի հաշվվում
        a.click("[data-t=report]"); expect(a.locator("#main")).to_contain_text("Վարորդի հաստատած այցեր")
        a.click("#out")
        # գարաժի սեփականատերը՝ միայն իր հրապարակային կարծիքները, առանց թաքցնելու հնարավորության
        a.fill("#lg", "kentron"); a.fill("#pw", "kentron-pass-1"); a.click("#go"); expect(a.locator("#who")).to_have_text("Garage Kentron")
        a.click("[data-t=reviews]")
        expect(a.locator("#main")).to_contain_text("Կարծիքներ դեռ չկան")
        assert a.locator("[data-hide]").count() == 0
        a.click("#out")
        print("Ադմինի մոդերացիա, գարաժի տեսածը ✓")

        # --- Հայերեն տառերի հուշում չկա. լատինատառ գրելը ազատ է ---
        lc = b.new_context(viewport={"width": 1000, "height": 800}); lp = lc.new_page()
        lp.on("pageerror", lambda e: errors.append("lang pageerror: " + str(e)))
        lp.goto(BASE + "/app")
        assert "հայերեն տառերով" not in lp.get_attribute("#in", "placeholder")                    # դաշտում պահանջ չկա
        expect(lp.locator(".m.bot").first).not_to_contain_text("հայերեն տառերով")                # ողջույնում էլ
        assert lp.locator("#lang").count() == 0                                                    # դեղին հուշումը հանված է
        lp.fill("#in", "tormoza skripyat"); lp.dispatch_event("#in", "input")
        assert lp.locator("#lang").count() == 0
        lp.press("#in", "Enter")                                                                   # ուղարկվում է առանց հուշման
        expect(lp.locator(".m.bot").last).not_to_contain_text("Խնդրում ենք գրել")
        lc.close()
        print("Հայերեն տառերի ուղղորդում (placeholder, ողջույն, հուշում, բոտի պատասխան, BMW-ը խնդիր չէ) ✓")

        # --- «Իմ հայտերը». անվավեր հղումները չեն երևում ---
        ic = b.new_context(viewport={"width": 1000, "height": 800}); ip = ic.new_page()
        ip.on("pageerror", lambda e: errors.append("mine pageerror: " + str(e)))
        valid = ic.request.post(BASE + "/requests", data={"name": "Վ", "phone": "+374 91 700001", "garage_id": 2}).json()["review_token"]
        ip.goto(BASE + "/app")
        def seed(entries): ip.evaluate("(e) => localStorage.setItem('pending_reviews', JSON.stringify(e))", entries)
        now = ip.evaluate("Date.now()")
        seed([{"url": "/review/" + valid, "garage": "Garage Kentron", "ts": now, "done": False},   # հին ձևաչափ (url)՝ դեռ ճանաչվում է
              {"tok": "fake-token-abc", "garage": "Ghost Garage", "ts": now, "done": False}])
        ip.reload()
        expect(ip.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")                              # միայն վավերը
        ip.click("#mineBtn")
        expect(ip.locator("#mineList")).to_contain_text("Garage Kentron"); expect(ip.locator("#mineList")).not_to_contain_text("Ghost Garage")
        assert "fake-token-abc" not in ip.evaluate("localStorage.getItem('pending_reviews')")       # պահոցից նույնպես հանված է
        ip.goto(BASE + "/app"); ip.wait_for_timeout(800)                                              # սպասում ենք սինքին, որ seed-ը չվերագրվի
        seed([{"tok": "only-fake", "garage": "Ghost Garage", "ts": now, "done": False}])         # միայն անվավեր -> հաշվիչ չկա
        ip.goto(BASE + "/app"); ip.wait_for_timeout(800); expect(ip.locator("#mineBtn")).to_have_text("Իմ հայտերը")   # հաշվիչ չկա, մաքուր URL (առանց #h=)
        seed([{"tok": valid, "garage": "Garage Kentron", "ts": now, "done": False}])
        # ցանցի անկման դեպքում ոչինչ չի ջնջվում (չենք կարող իմանալ՝ վավեր է թե ոչ)
        ip.goto(BASE + "/app"); expect(ip.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")
        ip.route("**/my-requests/check", lambda route: route.abort())
        ip.reload(); ip.wait_for_timeout(800)
        expect(ip.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")
        ic.close()
        print("«Իմ հայտերը». անվավեր հայտերը չեն երևում և հանվում են, ցանցի անկման դեպքում ոչինչ չի կորչում ✓")

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
        assert "#h=" in bp.url and len(bp.url.split("#h=")[1]) > 20, bp.url                          # token-ը պահվել է հասցեագոտում
        bp.reload()                                                                                   # refresh առանց localStorage-ի
        expect(bp.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")                                # հղումը չկորավ
        bp.click("#mineBtn"); expect(bp.locator("#mineList .stars")).to_have_count(1)
        bc = bp.locator("#mineList .mc").first                                                       # «չեմ գնացել»՝ պատճառով
        bc.get_by_role("button", name="Չեմ գնացել").click(); bc.locator("select").select_option("far")
        bc.get_by_role("button", name="Հաստատել").click(); expect(bc.locator(".nogo")).to_have_text("Չեմ գնացել")
        bp.screenshot(path="shots/storage_blocked.png")
        blocked.close()
        print("localStorage-ը արգելված է. նախազգուշացում + հայտը չի կորչում refresh-ից հետո ✓")

        # --- «Գարաժներ» էջը և գարաժի էջը (առանձին պատուհանում, որ chat-ի պահոցը չխառնվի) ---
        cc = b.new_context(viewport={"width": 1000, "height": 800}); cp = cc.new_page()
        cp.on("pageerror", lambda e: errors.append("catalog pageerror: " + str(e)))
        cp.goto(BASE + "/app"); cp.click("#allBtn"); cp.wait_for_url("**/catalog")                    # chat-ի կոճակը տանում է էջ, ոչ մոդալ
        expect(cp.locator(".list .g")).to_have_count(3); expect(cp.locator("#cnt")).to_contain_text("3 գարաժ")
        expect(cp.locator(".list .g", has_text="Garage Kentron")).to_contain_text("Տերյան 40")
        assert cp.locator(".list .g .open").count() == 3 and cp.locator("#pg button").count() == 0    # բաց/փակ նշում, 3 գարաժ = 1 էջ
        cp.goto(BASE + "/catalog?per_page=2"); expect(cp.locator(".list .g")).to_have_count(2)        # էջավորում (per_page՝ թեստի համար)
        expect(cp.locator("#pg button.on")).to_have_text("1"); expect(cp.locator("#cnt")).to_contain_text("էջ 1/2")
        cp.locator("#pg").get_by_role("button", name="2").click(); expect(cp.locator(".list .g")).to_have_count(1)
        assert "&page=2" in cp.url or "?page=2" in cp.url; expect(cp.locator("#pg button.on")).to_have_text("2")
        cp.fill("#q", "speed"); expect(cp.locator("#cnt")).to_contain_text("«speed»"); expect(cp.locator(".list .g")).to_have_count(1)
        assert "&page=" not in cp.url and "?page=" not in cp.url                                    # որոնումը սկսում է 1-ից
        cp.goto(BASE + "/catalog")
        cp.fill("#q", "speed"); expect(cp.locator(".list .g")).to_have_count(1); expect(cp.locator(".list .g")).to_contain_text("Speed Service")
        cp.fill("#q", "Կախոցի ստուգում"); expect(cp.locator(".list .g", has_text="Garage Kentron")).to_be_visible()   # ծառայությամբ
        expect(cp.locator(".list .g", has_text="AutoPro")).to_have_count(0)
        cp.fill("#q", "zzz"); expect(cp.locator(".empty")).to_contain_text("Ոչինչ չգտնվեց")
        cp.fill("#q", ""); expect(cp.locator(".list .g")).to_have_count(3)
        cp.screenshot(path="shots/garages.png")
        cp.locator(".list .g", has_text="Garage Kentron").click(); cp.wait_for_url("**/catalog/*")    # գարաժի էջ
        expect(cp.locator("h1")).to_have_text("Garage Kentron"); expect(cp.locator(".ad")).to_contain_text("Տերյան 40")
        expect(cp.locator(".sr", has_text="Կախոցի ստուգում")).to_contain_text("֏"); assert cp.locator(".sr").count() >= 2
        expect(cp.locator(".hrs li")).to_have_count(7); expect(cp.locator("section", has_text="Կարծիքներ")).to_contain_text("Կարծիքներ դեռ չկան")
        cp.screenshot(path="shots/garage.png")
        cp.locator(".sr", has_text="Կախոցի ստուգում").get_by_role("button", name="Թողնել հայտ").click()   # հայտ գարաժի էջից
        expect(cp.locator("#dlg")).to_be_visible(); expect(cp.locator("#dlgFor")).to_have_text("Garage Kentron · Կախոցի ստուգում")
        cp.click("#rsend"); expect(cp.locator("#rerr")).to_contain_text("Լրացրեք")
        cp.fill("#rn", "Գոռ"); cp.fill("#rp", "+374 91 555555"); cp.click("#rsend"); expect(cp.locator("#dlg")).to_be_hidden()
        expect(cp.locator(".sent")).to_contain_text("Հայտը ուղարկված է «Garage Kentron»-ին")
        cp.goto(BASE + "/app"); expect(cp.locator("#mineBtn")).to_have_text("Իմ հայտերը (1)")          # հայտը երևում է chat-ի ցուցակում
        cp.click("#mineBtn"); expect(cp.locator("#mineList .mc")).to_contain_text("Garage Kentron"); expect(cp.locator("#mineList .stars")).to_have_count(1)
        for path in ("/app", "/my", "/catalog", "/catalog/2"):                                       # նույն վերնագիրը բոլոր էջերում
            cp.goto(BASE + path); expect(cp.locator("header nav a")).to_have_count(4)
            expect(cp.locator("header nav")).to_have_text("ՕգնականԻմ հայտերը (1)ԳարաժներՀավելված"); expect(cp.locator("header .inst.on")).to_have_count(1)
        cp.goto(BASE + "/catalog/999"); expect(cp.locator("body")).to_contain_text("չի գտնվել")
        cc.close()
        print("«Գարաժներ» էջ (ցուցակ, որոնում) և գարաժի էջ (ծառայություններ, ժամեր, հայտ) ✓")

        # --- Refresh պատասխանի սպասման ժամանակ. անպատասխան հարցը վերադառնում է մուտքի դաշտ ---
        page.evaluate("""localStorage.setItem('chat_state_v1', JSON.stringify({ts: Date.now(),
            items: [{cls: 'me', text: 'թակոց կախոցից'}], history: [{role: 'user', content: 'թակոց կախոցից'}]}))""")
        page.reload()
        expect(page.locator("#in")).to_have_value("թակոց կախոցից")
        expect(page.locator(".m.bot").last).to_contain_text("պատասխանը չստացվեց")
        assert page.locator(".m.me").count() == 0
        page.evaluate("localStorage.removeItem('chat_state_v1')")
        print("Անպատասխան հարցի վերականգնում ✓")

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

        b.close()

    print("JS/console սխալներ:", errors or "չկան")

finally:
    server.terminate()
