"""Հարցումներ տվյալների բազայի վրա (Փուլ 5). Ֆունկցիաների անունները նույնն են, ինչ Փուլ 1-ում։"""
from datetime import datetime, time

from data import Garage, GarageService, Service
from db import connect


def all_services() -> list[Service]:
    with connect() as c:
        rows = c.execute("SELECT * FROM services ORDER BY id").fetchall()
    return [Service(r["id"], r["name"], r["category"],
                    tuple(k for k in r["keywords"].split(",") if k), r["sample_question"] or "") for r in rows]


def all_garages() -> list[Garage]:
    with connect() as c:
        garages = c.execute("SELECT * FROM garages ORDER BY id").fetchall()
        hours = c.execute("SELECT * FROM working_hours").fetchall()
        offers = c.execute("SELECT * FROM garage_services").fetchall()
    result = []
    for r in garages:
        g = Garage(r["id"], r["name"], r["address"], r["phone"], r["lat"], r["lng"])
        for h in hours:
            if h["garage_id"] == g.id:
                g.hours[h["weekday"]] = (time.fromisoformat(h["open_time"]),
                                         time.fromisoformat(h["close_time"]))
        for o in offers:
            if o["garage_id"] == g.id:
                g.services[o["service_id"]] = GarageService(o["service_id"], o["price"], o["duration_min"])
        result.append(g)
    return result


def catalog_page(q: str, service_ids: list[int], offset: int, limit: int) -> tuple[list[dict], int]:
    """Գարաժների էջ՝ էջավորումը սերվերում (հազարավոր գարաժների համար)։ Գարաժը համընկնում է, եթե անունը կամ հասցեն
    պարունակում է տեքստը, կամ առաջարկում է service_ids-ից որևէ ծառայություն (դրանք AI-ն է որոշել տեքստից)։"""
    like = f"%{q.strip()}%"
    where, args = "", ()
    if q.strip():
        where = """WHERE g.name ILIKE %s OR g.address ILIKE %s
                   OR EXISTS (SELECT 1 FROM garage_services gs WHERE gs.garage_id = g.id AND gs.service_id = ANY(%s))"""
        args = (like, like, list(service_ids))
    with connect() as c:
        total = c.execute(f"SELECT COUNT(*) AS n FROM garages g {where}", args).fetchone()["n"]
        rows = c.execute(f"""SELECT g.id, g.name, g.address, g.phone,
                                    (SELECT COUNT(*) FROM garage_services gs WHERE gs.garage_id = g.id) AS services_count
                             FROM garages g {where} ORDER BY g.name, g.id LIMIT %s OFFSET %s""",
                         args + (limit, offset)).fetchall()
        ids = [r["id"] for r in rows]
        hours = c.execute("SELECT garage_id, weekday, open_time, close_time FROM working_hours WHERE garage_id = ANY(%s)",
                          (ids,)).fetchall() if ids else []
    out = []
    for r in rows:
        g = Garage(r["id"], r["name"], r["address"], r["phone"])
        for h in hours:
            if h["garage_id"] == g.id:
                g.hours[h["weekday"]] = (time.fromisoformat(h["open_time"]), time.fromisoformat(h["close_time"]))
        out.append({"garage": g, "services_count": r["services_count"]})
    return out, total


def garage_services(garage_id: int) -> list[dict]:
    """Գարաժի ծառայությունները գներով՝ կատեգորիայով և անունով դասավորված (գարաժի էջ)։"""
    with connect() as c:
        rows = c.execute("""SELECT s.id AS service_id, s.name, s.category, gs.price, gs.duration_min
                            FROM garage_services gs JOIN services s ON s.id = gs.service_id
                            WHERE gs.garage_id = %s ORDER BY s.category, s.name""", (garage_id,)).fetchall()
    return [dict(r) for r in rows]


def get_service(service_id: int) -> Service | None:
    return next((s for s in all_services() if s.id == service_id), None)


def get_garage(garage_id: int) -> Garage | None:
    return next((g for g in all_garages() if g.id == garage_id), None)


def find_services(text: str) -> list[Service]:
    text = text.strip().lower()
    return [s for s in all_services() if text in s.name.lower()]


def garages_for_service(service_id: int) -> list[tuple[Garage, int]]:
    """Գարաժները, որոնք առաջարկում են ծառայությունը՝ գնի աճման կարգով."""
    result = [(g, g.services[service_id].price) for g in all_garages() if service_id in g.services]
    return sorted(result, key=lambda pair: pair[1])


def is_open(garage: Garage, when: datetime) -> bool:
    hours = garage.hours.get(when.weekday())
    if hours is None:
        return False
    opens, closes = hours
    return opens <= when.time() < closes


def open_garages(when: datetime) -> list[Garage]:
    return [g for g in all_garages() if is_open(g, when)]


def set_price(garage_id: int, service_id: int, price: int) -> bool:
    """Փոխում է գինը։ False, եթե այդ գարաժը այդ ծառայությունը չի առաջարկում։"""
    if price < 0:
        return False
    with connect() as c:
        cur = c.execute("UPDATE garage_services SET price=%s WHERE garage_id=%s AND service_id=%s",
                        (price, garage_id, service_id))
        return cur.rowcount == 1


# ================= Ադմինի գործողություններ (Փուլ 6) =================
import secrets

import psycopg


def _kw(keywords: list[str]) -> str:
    return ",".join(k.strip() for k in keywords if k.strip())


def create_garage(name: str, address: str, phone: str) -> int:
    """Նոր գարաժ՝ լռելյայն Երկ–Ուրբ 09:00–18:00։"""
    with connect() as c:
        gid = c.execute("INSERT INTO garages(name,address,phone) VALUES (%s,%s,%s) RETURNING id",
                        (name, address, phone)).fetchone()["id"]
        for d in range(5):
            c.execute("INSERT INTO working_hours VALUES (%s,%s,%s,%s)", (gid, d, "09:00", "18:00"))
    return gid


def update_garage(garage_id: int, name: str, address: str, phone: str) -> bool:
    """Եթե հասցեն փոխվել է, հին կետը հանվում է. վարորդներին սխալ տեղ չենք ուղարկում,
    մինչև սեփականատերը նոր կետը չհաստատի։"""
    with connect() as c:
        old = c.execute("SELECT address FROM garages WHERE id=%s", (garage_id,)).fetchone()
        if old is None:
            return False
        changed = (old["address"] or "").strip() != address.strip()
        c.execute("UPDATE garages SET name=%s, address=%s, phone=%s, lat=CASE WHEN %s THEN NULL ELSE lat END, "
                  "lng=CASE WHEN %s THEN NULL ELSE lng END WHERE id=%s",
                  (name, address, phone, changed, changed, garage_id))
        return True


def set_garage_location(garage_id: int, lat: float | None, lng: float | None) -> bool:
    with connect() as c:
        return c.execute("UPDATE garages SET lat=%s, lng=%s WHERE id=%s", (lat, lng, garage_id)).rowcount == 1


def delete_garage(garage_id: int) -> bool:
    with connect() as c:
        return c.execute("DELETE FROM garages WHERE id=%s", (garage_id,)).rowcount == 1


def upsert_garage_service(garage_id: int, service_id: int, price: int, duration_min: int) -> bool:
    try:
        with connect() as c:
            c.execute("""INSERT INTO garage_services VALUES (%s,%s,%s,%s)
                         ON CONFLICT(garage_id, service_id)
                         DO UPDATE SET price=excluded.price, duration_min=excluded.duration_min""",
                      (garage_id, service_id, price, duration_min))
        return True
    except psycopg.IntegrityError:  # գարաժը կամ ծառայությունը գոյություն չունի
        return False


def delete_garage_service(garage_id: int, service_id: int) -> bool:
    with connect() as c:
        return c.execute("DELETE FROM garage_services WHERE garage_id=%s AND service_id=%s",
                         (garage_id, service_id)).rowcount == 1


def set_hours(garage_id: int, days: list[tuple[int, str, str]]) -> bool:
    """Փոխարինում է աշխատանքային ժամերը. days = [(օր, "HH:MM", "HH:MM"), ...]՝ միայն բաց օրերը։"""
    with connect() as c:
        if c.execute("SELECT 1 FROM garages WHERE id=%s", (garage_id,)).fetchone() is None:
            return False
        c.execute("DELETE FROM working_hours WHERE garage_id=%s", (garage_id,))
        for d, o, cl in days:
            c.execute("INSERT INTO working_hours VALUES (%s,%s,%s,%s)", (garage_id, d, o, cl))
    return True


def create_service(name: str, category: str, keywords: list[str], sample_question: str = "") -> int:
    with connect() as c:
        return c.execute("INSERT INTO services(name,category,keywords,sample_question) VALUES (%s,%s,%s,%s) RETURNING id",
                         (name, category, _kw(keywords), sample_question.strip())).fetchone()["id"]


def update_service(service_id: int, name: str, category: str, keywords: list[str], sample_question: str = "") -> bool:
    with connect() as c:
        return c.execute("UPDATE services SET name=%s, category=%s, keywords=%s, sample_question=%s WHERE id=%s",
                         (name, category, _kw(keywords), sample_question.strip(), service_id)).rowcount == 1


# ================= Հաճախ հարցվող հարցեր =================
QUERY_MAX_LEN = 200
QUERY_KEEP_DAYS = 90


def log_query(text: str, service_id: int | None, mode: str) -> None:
    """Պահում է վարորդի առաջին հարցը և ծառայությունը, որին chat-ը այն հասցրեց։
    Նույն իմաստով տարբեր ձևակերպումները խմբավորվում են հենց ծառայությունով։ Հինը (90 օր) ջնջվում է։"""
    text = " ".join(text.split())[:QUERY_MAX_LEN]
    if not text:
        return
    with connect() as c:
        c.execute("DELETE FROM chat_queries WHERE created_at < now() - make_interval(days => %s)", (QUERY_KEEP_DAYS,))
        c.execute("INSERT INTO chat_queries(text, service_id, mode) VALUES (%s,%s,%s)", (text, service_id, mode))


def popular_questions(days: int = 30, limit: int = 3, min_total: int = 20) -> list[dict]:
    """Ամենաշատ հարցված ծառայությունները վերջին `days` օրում՝ [{service_id, text, count}]։
    Տեքստը ծառայության «օրինակ հարցն» է, եթե չկա՝ այդ ծառայության ամենահաճախ բառացի հարցը։
    Եթե ընդհանուր հարցերը `min_total`-ից քիչ են, վերադարձնում է դատարկ ցուցակ (վիճակագրությունը դեռ վստահելի չէ)։"""
    with connect() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM chat_queries WHERE created_at >= now() - make_interval(days => %s)",
                          (days,)).fetchone()["n"]
        if total < min_total:
            return []
        rows = c.execute("""SELECT q.service_id, s.sample_question, COUNT(*)::int AS n
                            FROM chat_queries q JOIN services s ON s.id = q.service_id
                            WHERE q.created_at >= now() - make_interval(days => %s)
                            GROUP BY q.service_id, s.sample_question ORDER BY n DESC, q.service_id LIMIT %s""",
                         (days, limit)).fetchall()
        out = []
        for r in rows:
            text = (r["sample_question"] or "").strip()
            if not text:   # օրինակ հարց չկա. վերցնում ենք վարորդների ամենահաճախ ձևակերպումը
                t = c.execute("""SELECT lower(text) AS t, COUNT(*) AS n FROM chat_queries
                                 WHERE service_id=%s AND created_at >= now() - make_interval(days => %s)
                                 GROUP BY lower(text) ORDER BY n DESC LIMIT 1""", (r["service_id"], days)).fetchone()
                text = t["t"] if t else ""
            if text:
                out.append({"service_id": r["service_id"], "text": text, "count": r["n"]})
    return out


def query_stats(days: int = 30) -> dict:
    """Ադմինի համար. հարցերի քանակը և ծառայություն չգտած հարցերը (ինչ են հարցնում, ինչը կատալոգում չկա)։"""
    with connect() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM chat_queries WHERE created_at >= now() - make_interval(days => %s)",
                          (days,)).fetchone()["n"]
        unmatched = c.execute("""SELECT text, COUNT(*)::int AS n FROM chat_queries
                                 WHERE service_id IS NULL AND created_at >= now() - make_interval(days => %s)
                                 GROUP BY text ORDER BY n DESC LIMIT 20""", (days,)).fetchall()
    return {"days": days, "total": total, "unmatched": [dict(r) for r in unmatched]}


def delete_service(service_id: int) -> bool:
    with connect() as c:
        return c.execute("DELETE FROM services WHERE id=%s", (service_id,)).rowcount == 1


# ================= Վարորդների հայտեր (Փուլ 7) =================
def create_request(name: str, phone: str, garage_id: int | None,
                   service_id: int | None, message: str) -> int | None:
    try:
        with connect() as c:
            return c.execute("INSERT INTO requests(name,phone,garage_id,service_id,message,review_token) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                             (name, phone, garage_id, service_id, message, secrets.token_urlsafe(16))).fetchone()["id"]
    except psycopg.IntegrityError:
        return None


STATUSES = ("new", "called", "no_answer", "booked", "visited", "declined")
DECLINE_REASONS = ("price", "far", "other_garage", "no_time", "changed_mind", "other")


def list_requests(garage_id: int | None = None) -> list[dict]:
    """Բոլոր հայտերը, կամ միայն տվյալ գարաժինը (գարաժի սեփականատիրոջ համար)։"""
    where, args = ("WHERE r.garage_id = %s", (garage_id,)) if garage_id is not None else ("", ())
    with connect() as c:
        rows = c.execute(f"""SELECT r.id, r.created_at, r.name, r.phone, r.message, r.status,
                                   r.decline_reason, r.status_changed_at, r.first_response_at,
                                   r.garage_id, g.name AS garage, r.service_id, s.name AS service
                            FROM requests r LEFT JOIN garages g ON g.id = r.garage_id
                            LEFT JOIN services s ON s.id = r.service_id {where}
                            ORDER BY (r.status = 'new') DESC, r.id DESC""", args).fetchall()
    return [dict(r) for r in rows]


def request_row(request_id: int) -> dict | None:
    with connect() as c:
        r = c.execute("""SELECT r.*, g.name AS garage, g.telegram_chat_id AS garage_chat_id, s.name AS service
                         FROM requests r LEFT JOIN garages g ON g.id = r.garage_id
                         LEFT JOIN services s ON s.id = r.service_id WHERE r.id = %s""",
                      (request_id,)).fetchone()
    return dict(r) if r else None


def set_request_garage(request_id: int, garage_id: int | None) -> str:
    """Նշանակում է հայտը գարաժին (կամ հանում՝ None)։ Վերադարձնում է "ok" | "notfound" | "badgarage"։"""
    try:
        with connect() as c:
            n = c.execute("UPDATE requests SET garage_id=%s WHERE id=%s", (garage_id, request_id)).rowcount
        return "ok" if n == 1 else "notfound"
    except psycopg.IntegrityError:
        return "badgarage"


def set_request_status(request_id: int, status: str, decline_reason: str | None = None) -> bool:
    """Փոխում է հայտի փուլը։ Առաջին անգամ «նոր»-ից դուրս գալիս գրանցվում է արձագանքման պահը
    (այն չի փոխվում, եթե հետո նորից բացեն)։ Հրաժարման պատճառը պահվում է միայն «declined»-ի դեպքում։"""
    if status not in STATUSES or (decline_reason is not None and decline_reason not in DECLINE_REASONS):
        return False
    with connect() as c:
        row = c.execute("SELECT status, first_response_at FROM requests WHERE id=%s", (request_id,)).fetchone()
        if row is None:
            return False
        first = row["first_response_at"] is None and row["status"] == "new" and status != "new"
        c.execute("""UPDATE requests SET status=%s, decline_reason=%s, status_changed_at=CURRENT_TIMESTAMP,
                     first_response_at=CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE first_response_at END
                     WHERE id=%s""",
                  (status, decline_reason if status == "declined" else None, first, request_id))
    return True


def _metrics(rows: list) -> dict:
    from collections import Counter
    from datetime import datetime as dt
    from statistics import median
    fmt = "%Y-%m-%d %H:%M:%S"
    by = Counter(r["status"] for r in rows)
    waits = [(dt.strptime(r["first_response_at"], fmt) - dt.strptime(r["created_at"], fmt)).total_seconds() / 60
             for r in rows if r["first_response_at"]]
    return {
        "total": len(rows), **{s: by.get(s, 0) for s in STATUSES},
        "responded": len(rows) - by.get("new", 0),             # «նոր»-ից դուրս եկածները
        "booked_plus": by.get("booked", 0) + by.get("visited", 0),
        "median_response_min": round(median(waits)) if waits else None,
        "decline_reasons": dict(Counter(r["decline_reason"] or "other" for r in rows if r["status"] == "declined")),
        # վարորդի անկախ հաստատումը (գնահատման հղումով)
        "confirmed_visits": sum(1 for r in rows if r["went"] == 1),
        "driver_no_visit": sum(1 for r in rows if r["went"] == 0),
        "mismatch": sum(1 for r in rows if r["status"] == "visited" and r["went"] == 0),  # գարաժը՝ «այցելեց», վարորդը՝ «չգնացի»
    }


def request_report(start_utc: str, end_utc: str, garage_id: int | None = None) -> dict:
    """Հայտերի հաշվետվություն ըստ ստեղծման ժամանակի [start, end) (UTC տողեր)։
    Վիճակները ընթացիկն են (պատմություն չենք պահում)։"""
    where, args = "WHERE r.created_at >= %s AND r.created_at < %s", [start_utc, end_utc]
    if garage_id is not None:
        where, args = where + " AND r.garage_id = %s", args + [garage_id]
    with connect() as c:
        rows = c.execute(f"""SELECT r.garage_id, r.status, r.decline_reason, r.created_at, r.first_response_at, rv.went
                             FROM requests r LEFT JOIN reviews rv ON rv.request_id = r.id {where}""", args).fetchall()
        garages = c.execute("SELECT id, name FROM garages" + (" WHERE id = %s" if garage_id is not None else "") +
                            " ORDER BY id", (garage_id,) if garage_id is not None else ()).fetchall()
    out = [{"garage_id": g["id"], "name": g["name"], **_metrics([r for r in rows if r["garage_id"] == g["id"]])}
           for g in garages]
    if garage_id is None:
        unassigned = [r for r in rows if r["garage_id"] is None]
        if unassigned:
            out.append({"garage_id": None, "name": "Նշանակված չէ", **_metrics(unassigned)})
    return {"total": _metrics(list(rows)), "garages": out}


# ================= Գարաժների մուտք և Telegram =================
import secrets


def set_garage_login(garage_id: int, login: str, password_hash: str) -> str:
    """"ok" | "taken" (մուտքանունը զբաղված է) | "notfound"։"""
    try:
        with connect() as c:
            n = c.execute("UPDATE garages SET login=%s, password_hash=%s WHERE id=%s",
                          (login.lower(), password_hash, garage_id)).rowcount
        return "ok" if n == 1 else "notfound"
    except psycopg.IntegrityError:
        return "taken"


def clear_garage_login(garage_id: int) -> bool:
    with connect() as c:
        return c.execute("UPDATE garages SET login=NULL, password_hash=NULL WHERE id=%s",
                         (garage_id,)).rowcount == 1


def find_garage_login(login: str) -> tuple[int, str] | None:
    with connect() as c:
        r = c.execute("SELECT id, password_hash FROM garages WHERE login=%s AND password_hash IS NOT NULL",
                      (login.lower(),)).fetchone()
    return (r["id"], r["password_hash"]) if r else None


def garage_login_active(garage_id: int) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM garages WHERE id=%s AND password_hash IS NOT NULL",
                         (garage_id,)).fetchone() is not None


def garage_accounts() -> dict[int, dict]:
    with connect() as c:
        rows = c.execute("SELECT id, login, telegram_chat_id FROM garages").fetchall()
    return {r["id"]: {"login": r["login"], "telegram_linked": r["telegram_chat_id"] is not None} for r in rows}


def create_link_code(kind: str, garage_id: int | None = None) -> str:
    code = secrets.token_urlsafe(9)  # միայն A-Za-z0-9_- (Telegram-ի /start պարամետրի համար)
    with connect() as c:
        c.execute("DELETE FROM link_codes WHERE created_at < now() - interval '1 hour'")
        c.execute("DELETE FROM link_codes WHERE kind=%s AND garage_id IS NOT DISTINCT FROM %s", (kind, garage_id))
        c.execute("INSERT INTO link_codes(code, kind, garage_id) VALUES (%s,%s,%s)", (code, kind, garage_id))
    return code


def consume_link_code(code: str, chat_id: int) -> tuple[str, str | None] | None:
    """Մեկանգամյա կոդով կապում է Telegram chat-ը։ Վերադարձնում է ("garage", անուն) | ("admin", None) | None։"""
    with connect() as c:
        c.execute("DELETE FROM link_codes WHERE created_at < now() - interval '1 hour'")
        row = c.execute("SELECT * FROM link_codes WHERE code=%s", (code,)).fetchone()
        if row is None:
            return None
        c.execute("DELETE FROM link_codes WHERE code=%s", (code,))
        if row["kind"] == "admin":
            c.execute("""INSERT INTO settings VALUES ('admin_chat_id', %s)
                         ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (str(chat_id),))
            return ("admin", None)
        c.execute("UPDATE garages SET telegram_chat_id=%s WHERE id=%s", (chat_id, row["garage_id"]))
        g = c.execute("SELECT name FROM garages WHERE id=%s", (row["garage_id"],)).fetchone()
        return ("garage", g["name"] if g else None)


def unlink_garage_telegram(garage_id: int) -> bool:
    with connect() as c:
        return c.execute("UPDATE garages SET telegram_chat_id=NULL WHERE id=%s", (garage_id,)).rowcount == 1


def get_admin_chat_id() -> int | None:
    import os
    with connect() as c:
        r = c.execute("SELECT value FROM settings WHERE key='admin_chat_id'").fetchone()
    value = r["value"] if r else os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def unlink_admin_telegram() -> None:
    with connect() as c:
        c.execute("DELETE FROM settings WHERE key='admin_chat_id'")


# ================= Գնահատականներ =================
PRIOR_WEIGHT = 5      # Bayes-ի «նախնական» կշիռ. քիչ կարծիքով գարաժի գնահատականը մոտեցվում է ընդհանուր միջինին
MIN_REVIEWS_BADGE = 5  # այս թվից քիչ կարծիքի դեպքում UI-ը նշում է «քիչ կարծիք»


def phone_key(phone: str) -> str:
    """+374 91 123456 և 091123456 -> նույն բանալին (վերջին 8 թվանշանը)։"""
    return "".join(ch for ch in phone if ch.isdigit())[-8:]


def garage_ratings(garage_id: int | None = None) -> dict[int, dict]:
    """garage_id -> {avg, count, score}. Հաշվվում են միայն թաքցված չեղած, «գնացի» կարծիքները։
    score-ը Bayes-ի միջինն է՝ դասավորելու համար (1 կարծիքով 5.0-ը չի հաղթում 50 կարծիքով 4.7-ին)։"""
    with connect() as c:
        rows = c.execute("""SELECT garage_id, COUNT(*)::int AS n, AVG(rating)::float AS a FROM reviews
                            WHERE went = 1 AND hidden = 0 GROUP BY garage_id""").fetchall()
    total_n = sum(r["n"] for r in rows)
    # նախնական միջինը. քիչ տվյալի դեպքում մոտ է 4.0-ին, որպեսզի մեկ կարծիքը ինքն իրեն չդարձնի «նորմա»
    global_avg = (sum(r["a"] * r["n"] for r in rows) + 20 * 4.0) / (total_n + 20)
    out = {}
    for r in rows:
        out[r["garage_id"]] = {"avg": round(r["a"], 1), "count": r["n"],
                               "score": round((r["n"] * r["a"] + PRIOR_WEIGHT * global_avg) / (r["n"] + PRIOR_WEIGHT), 3)}
    return out if garage_id is None else {garage_id: out[garage_id]} if garage_id in out else {}


def rating_of(ratings: dict, garage_id: int) -> dict:
    return ratings.get(garage_id, {"avg": None, "count": 0, "score": None})


def review_context(token: str) -> dict | None:
    with connect() as c:
        r = c.execute("""SELECT r.id AS request_id, r.garage_id, r.phone, g.name AS garage, s.name AS service,
                                rv.id AS review_id
                         FROM requests r LEFT JOIN garages g ON g.id = r.garage_id
                         LEFT JOIN services s ON s.id = r.service_id
                         LEFT JOIN reviews rv ON rv.request_id = r.id
                         WHERE r.review_token = %s""", (token,)).fetchone()
    return dict(r) if r else None


def create_review(token: str, went: bool, rating: int | None, comment: str, reason: str | None,
                  display_name: str) -> str:
    """"ok" | "notfound" | "nogarage" (հայտը գարաժի չի նշանակված) | "already" (այս հայտը արդեն գնահատված է)
    | "updated" (նույն համարից նույն գարաժին 30 օրում արդեն կար «գնացի» կարծիք. այն թարմացվեց՝ նոր աստղեր, կարծիք, անուն.
      գարաժը կրկնակի կարծիք չի ստանում, իսկ վարորդի գրածը չի կորչում)։"""
    ctx = review_context(token)
    if ctx is None:
        return "notfound"
    if ctx["garage_id"] is None:
        return "nogarage"
    if ctx["review_id"] is not None:
        return "already"
    key = phone_key(ctx["phone"])
    try:
        with connect() as c:
            if went:
                dup = c.execute("""SELECT id FROM reviews WHERE garage_id=%s AND phone_key=%s AND went=1
                                   AND created_at >= now() - interval '30 days' ORDER BY created_at DESC LIMIT 1""",
                                (ctx["garage_id"], key)).fetchone()
                if dup:
                    c.execute("UPDATE reviews SET rating=%s, comment=%s, display_name=%s WHERE id=%s",
                              (rating, comment, display_name, dup["id"]))
                    return "updated"
            c.execute("""INSERT INTO reviews(request_id, garage_id, service_id, phone_key, went, rating, comment, reason, display_name)
                         VALUES (%s,%s,(SELECT service_id FROM requests WHERE id=%s),%s,%s,%s,%s,%s,%s)""",
                      (ctx["request_id"], ctx["garage_id"], ctx["request_id"], key, 1 if went else 0,
                       rating if went else None, comment, None if went else reason, display_name))
    except psycopg.IntegrityError:
        return "already"
    return "ok"


def public_reviews(garage_id: int, limit: int = 20, offset: int = 0) -> list[dict]:
    with connect() as c:
        rows = c.execute("""SELECT rv.rating, rv.comment, rv.display_name, rv.created_at, s.name AS service
                            FROM reviews rv LEFT JOIN services s ON s.id = rv.service_id
                            WHERE rv.garage_id=%s AND rv.went=1 AND rv.hidden=0
                            ORDER BY rv.id DESC LIMIT %s OFFSET %s""", (garage_id, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def admin_reviews(garage_id: int | None = None, is_admin: bool = False) -> list[dict]:
    """Ադմինը տեսնում է ամեն ինչ (թաքցվածները և «չգնացի»-ները), գարաժը՝ միայն իր հրապարակային կարծիքները։"""
    where, args = [], []
    if garage_id is not None:
        where.append("rv.garage_id = %s"); args.append(garage_id)
    if not is_admin:
        where.append("rv.went = 1 AND rv.hidden = 0")
    sql = "WHERE " + " AND ".join(where) if where else ""
    with connect() as c:
        rows = c.execute(f"""SELECT rv.id, rv.garage_id, g.name AS garage, s.name AS service, rv.went, rv.rating, rv.comment,
                                    rv.reason, rv.display_name, rv.hidden, rv.hidden_reason, rv.created_at
                             FROM reviews rv LEFT JOIN garages g ON g.id = rv.garage_id
                             LEFT JOIN services s ON s.id = rv.service_id {sql} ORDER BY rv.id DESC LIMIT 200""", args).fetchall()
    return [dict(r) for r in rows]


def set_review_hidden(review_id: int, hidden: bool, reason: str | None) -> bool:
    with connect() as c:
        return c.execute("UPDATE reviews SET hidden=%s, hidden_reason=%s WHERE id=%s",
                         (1 if hidden else 0, reason if hidden else None, review_id)).rowcount == 1


def existing_review_tokens(tokens: list[str]) -> list[dict]:
    """«Իմ հայտերը» ցուցակի ստուգում. վերադարձնում է միայն այն հղումները, որոնք սերվերում դեռ կան
    (օր.՝ անվճար հոսթինգի վերագործարկումից հետո հին հղումները դադարում են գոյություն ունենալ)։"""
    tokens = [t for t in dict.fromkeys(tokens) if t][:200]
    if not tokens:
        return []
    marks = ",".join(["%s"] * len(tokens))
    with connect() as c:
        # dup. նույն համարից նույն գարաժին 30 օրում արդեն տրված «գնացի» կարծիքը (create_review-ի «duplicate» կանոնը).
        # այդ դեպքում հայտը համարվում է գնահատված և ցույց է տալիս նույն աստղերը, ոչ թե առանց աստղի «գնահատված»
        rows = c.execute(f"""SELECT r.review_token AS token, g.name AS garage, g.address AS address, s.name AS service, r.garage_id,
                                    r.id AS request_id, r.created_at,
                                    COALESCE(rv.id, dup.id) AS review_id, COALESCE(rv.went, dup.went) AS went,
                                    COALESCE(rv.rating, dup.rating) AS rating,
                                    COALESCE(rv.comment, dup.comment) AS comment, COALESCE(rv.display_name, dup.display_name) AS display_name
                             FROM requests r LEFT JOIN garages g ON g.id = r.garage_id
                             LEFT JOIN services s ON s.id = r.service_id
                             LEFT JOIN reviews rv ON rv.request_id = r.id
                             LEFT JOIN LATERAL (SELECT x.id, x.went, x.rating, x.comment, x.display_name FROM reviews x
                                                WHERE rv.id IS NULL AND x.garage_id = r.garage_id AND x.went = 1
                                                  AND x.phone_key = RIGHT(regexp_replace(r.phone, '\\D', '', 'g'), 8)
                                                  AND x.created_at >= now() - interval '30 days'
                                                ORDER BY x.created_at DESC LIMIT 1) dup ON TRUE
                             WHERE r.review_token IN ({marks})""", tokens).fetchall()
    return [{"token": r["token"], "garage": r["garage"], "garage_id": r["garage_id"], "address": r["address"] or "", "service": r["service"],
             "request_id": r["request_id"], "created_at": r["created_at"],
             "already_reviewed": r["review_id"] is not None, "has_garage": r["garage_id"] is not None,
             "went": None if r["review_id"] is None else bool(r["went"]),   # ցուցակը ցույց է տալիս տրված աստղերը
             "rating": r["rating"], "comment": r["comment"] or "", "display_name": r["display_name"] or ""} for r in rows]
