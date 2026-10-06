"""Հարցումներ տվյալների բազայի վրա (Փուլ 5). Ֆունկցիաների անունները նույնն են, ինչ Փուլ 1-ում։"""
from datetime import datetime, time

from data import Garage, GarageService, Service
from db import connect


def all_services() -> list[Service]:
    with connect() as c:
        rows = c.execute("SELECT * FROM services ORDER BY id").fetchall()
    return [Service(r["id"], r["name"], r["category"],
                    tuple(k for k in r["keywords"].split(",") if k)) for r in rows]


def all_garages() -> list[Garage]:
    with connect() as c:
        garages = c.execute("SELECT * FROM garages ORDER BY id").fetchall()
        hours = c.execute("SELECT * FROM working_hours").fetchall()
        offers = c.execute("SELECT * FROM garage_services").fetchall()
    result = []
    for r in garages:
        g = Garage(r["id"], r["name"], r["address"], r["phone"])
        for h in hours:
            if h["garage_id"] == g.id:
                g.hours[h["weekday"]] = (time.fromisoformat(h["open_time"]),
                                         time.fromisoformat(h["close_time"]))
        for o in offers:
            if o["garage_id"] == g.id:
                g.services[o["service_id"]] = GarageService(o["service_id"], o["price"], o["duration_min"])
        result.append(g)
    return result


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
        cur = c.execute("UPDATE garage_services SET price=? WHERE garage_id=? AND service_id=?",
                        (price, garage_id, service_id))
        return cur.rowcount == 1


# ================= Ադմինի գործողություններ (Փուլ 6) =================
import secrets
import sqlite3


def _kw(keywords: list[str]) -> str:
    return ",".join(k.strip() for k in keywords if k.strip())


def create_garage(name: str, address: str, phone: str) -> int:
    """Նոր գարաժ՝ լռելյայն Երկ–Ուրբ 09:00–18:00։"""
    with connect() as c:
        gid = c.execute("INSERT INTO garages(name,address,phone) VALUES (?,?,?)",
                        (name, address, phone)).lastrowid
        for d in range(5):
            c.execute("INSERT INTO working_hours VALUES (?,?,?,?)", (gid, d, "09:00", "18:00"))
    return gid


def update_garage(garage_id: int, name: str, address: str, phone: str) -> bool:
    with connect() as c:
        return c.execute("UPDATE garages SET name=?, address=?, phone=? WHERE id=?",
                         (name, address, phone, garage_id)).rowcount == 1


def delete_garage(garage_id: int) -> bool:
    with connect() as c:
        return c.execute("DELETE FROM garages WHERE id=?", (garage_id,)).rowcount == 1


def upsert_garage_service(garage_id: int, service_id: int, price: int, duration_min: int) -> bool:
    try:
        with connect() as c:
            c.execute("""INSERT INTO garage_services VALUES (?,?,?,?)
                         ON CONFLICT(garage_id, service_id)
                         DO UPDATE SET price=excluded.price, duration_min=excluded.duration_min""",
                      (garage_id, service_id, price, duration_min))
        return True
    except sqlite3.IntegrityError:  # գարաժը կամ ծառայությունը գոյություն չունի
        return False


def delete_garage_service(garage_id: int, service_id: int) -> bool:
    with connect() as c:
        return c.execute("DELETE FROM garage_services WHERE garage_id=? AND service_id=?",
                         (garage_id, service_id)).rowcount == 1


def set_hours(garage_id: int, days: list[tuple[int, str, str]]) -> bool:
    """Փոխարինում է աշխատանքային ժամերը. days = [(օր, "HH:MM", "HH:MM"), ...]՝ միայն բաց օրերը։"""
    with connect() as c:
        if c.execute("SELECT 1 FROM garages WHERE id=?", (garage_id,)).fetchone() is None:
            return False
        c.execute("DELETE FROM working_hours WHERE garage_id=?", (garage_id,))
        for d, o, cl in days:
            c.execute("INSERT INTO working_hours VALUES (?,?,?,?)", (garage_id, d, o, cl))
    return True


def create_service(name: str, category: str, keywords: list[str]) -> int:
    with connect() as c:
        return c.execute("INSERT INTO services(name,category,keywords) VALUES (?,?,?)",
                         (name, category, _kw(keywords))).lastrowid


def update_service(service_id: int, name: str, category: str, keywords: list[str]) -> bool:
    with connect() as c:
        return c.execute("UPDATE services SET name=?, category=?, keywords=? WHERE id=?",
                         (name, category, _kw(keywords), service_id)).rowcount == 1


def delete_service(service_id: int) -> bool:
    with connect() as c:
        return c.execute("DELETE FROM services WHERE id=?", (service_id,)).rowcount == 1


# ================= Վարորդների հայտեր (Փուլ 7) =================
def create_request(name: str, phone: str, garage_id: int | None,
                   service_id: int | None, message: str) -> int | None:
    try:
        with connect() as c:
            return c.execute("INSERT INTO requests(name,phone,garage_id,service_id,message,review_token) VALUES (?,?,?,?,?,?)",
                             (name, phone, garage_id, service_id, message, secrets.token_urlsafe(16))).lastrowid
    except sqlite3.IntegrityError:
        return None


STATUSES = ("new", "called", "no_answer", "booked", "visited", "declined")
DECLINE_REASONS = ("price", "far", "other_garage", "no_time", "changed_mind", "other")


def list_requests(garage_id: int | None = None) -> list[dict]:
    """Բոլոր հայտերը, կամ միայն տվյալ գարաժինը (գարաժի սեփականատիրոջ համար)։"""
    where, args = ("WHERE r.garage_id = ?", (garage_id,)) if garage_id is not None else ("", ())
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
                         LEFT JOIN services s ON s.id = r.service_id WHERE r.id = ?""",
                      (request_id,)).fetchone()
    return dict(r) if r else None


def set_request_garage(request_id: int, garage_id: int | None) -> str:
    """Նշանակում է հայտը գարաժին (կամ հանում՝ None)։ Վերադարձնում է "ok" | "notfound" | "badgarage"։"""
    try:
        with connect() as c:
            n = c.execute("UPDATE requests SET garage_id=? WHERE id=?", (garage_id, request_id)).rowcount
        return "ok" if n == 1 else "notfound"
    except sqlite3.IntegrityError:
        return "badgarage"


def set_request_status(request_id: int, status: str, decline_reason: str | None = None) -> bool:
    """Փոխում է հայտի փուլը։ Առաջին անգամ «նոր»-ից դուրս գալիս գրանցվում է արձագանքման պահը
    (այն չի փոխվում, եթե հետո նորից բացեն)։ Հրաժարման պատճառը պահվում է միայն «declined»-ի դեպքում։"""
    if status not in STATUSES or (decline_reason is not None and decline_reason not in DECLINE_REASONS):
        return False
    with connect() as c:
        row = c.execute("SELECT status, first_response_at FROM requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            return False
        first = row["first_response_at"] is None and row["status"] == "new" and status != "new"
        c.execute("""UPDATE requests SET status=?, decline_reason=?, status_changed_at=CURRENT_TIMESTAMP,
                     first_response_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE first_response_at END
                     WHERE id=?""",
                  (status, decline_reason if status == "declined" else None, 1 if first else 0, request_id))
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
    where, args = "WHERE r.created_at >= ? AND r.created_at < ?", [start_utc, end_utc]
    if garage_id is not None:
        where, args = where + " AND r.garage_id = ?", args + [garage_id]
    with connect() as c:
        rows = c.execute(f"""SELECT r.garage_id, r.status, r.decline_reason, r.created_at, r.first_response_at, rv.went
                             FROM requests r LEFT JOIN reviews rv ON rv.request_id = r.id {where}""", args).fetchall()
        garages = c.execute("SELECT id, name FROM garages" + (" WHERE id = ?" if garage_id is not None else "") +
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
            n = c.execute("UPDATE garages SET login=?, password_hash=? WHERE id=?",
                          (login.lower(), password_hash, garage_id)).rowcount
        return "ok" if n == 1 else "notfound"
    except sqlite3.IntegrityError:
        return "taken"


def clear_garage_login(garage_id: int) -> bool:
    with connect() as c:
        return c.execute("UPDATE garages SET login=NULL, password_hash=NULL WHERE id=?",
                         (garage_id,)).rowcount == 1


def find_garage_login(login: str) -> tuple[int, str] | None:
    with connect() as c:
        r = c.execute("SELECT id, password_hash FROM garages WHERE login=? AND password_hash IS NOT NULL",
                      (login.lower(),)).fetchone()
    return (r["id"], r["password_hash"]) if r else None


def garage_login_active(garage_id: int) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM garages WHERE id=? AND password_hash IS NOT NULL",
                         (garage_id,)).fetchone() is not None


def garage_accounts() -> dict[int, dict]:
    with connect() as c:
        rows = c.execute("SELECT id, login, telegram_chat_id FROM garages").fetchall()
    return {r["id"]: {"login": r["login"], "telegram_linked": r["telegram_chat_id"] is not None} for r in rows}


def create_link_code(kind: str, garage_id: int | None = None) -> str:
    code = secrets.token_urlsafe(9)  # միայն A-Za-z0-9_- (Telegram-ի /start պարամետրի համար)
    with connect() as c:
        c.execute("DELETE FROM link_codes WHERE created_at < datetime('now','-1 hour')")
        c.execute("DELETE FROM link_codes WHERE kind=? AND garage_id IS ?", (kind, garage_id))
        c.execute("INSERT INTO link_codes(code, kind, garage_id) VALUES (?,?,?)", (code, kind, garage_id))
    return code


def consume_link_code(code: str, chat_id: int) -> tuple[str, str | None] | None:
    """Մեկանգամյա կոդով կապում է Telegram chat-ը։ Վերադարձնում է ("garage", անուն) | ("admin", None) | None։"""
    with connect() as c:
        c.execute("DELETE FROM link_codes WHERE created_at < datetime('now','-1 hour')")
        row = c.execute("SELECT * FROM link_codes WHERE code=?", (code,)).fetchone()
        if row is None:
            return None
        c.execute("DELETE FROM link_codes WHERE code=?", (code,))
        if row["kind"] == "admin":
            c.execute("""INSERT INTO settings VALUES ('admin_chat_id', ?)
                         ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (str(chat_id),))
            return ("admin", None)
        c.execute("UPDATE garages SET telegram_chat_id=? WHERE id=?", (chat_id, row["garage_id"]))
        g = c.execute("SELECT name FROM garages WHERE id=?", (row["garage_id"],)).fetchone()
        return ("garage", g["name"] if g else None)


def unlink_garage_telegram(garage_id: int) -> bool:
    with connect() as c:
        return c.execute("UPDATE garages SET telegram_chat_id=NULL WHERE id=?", (garage_id,)).rowcount == 1


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
        rows = c.execute("""SELECT garage_id, COUNT(*) n, AVG(rating) a FROM reviews
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
                         WHERE r.review_token = ?""", (token,)).fetchone()
    return dict(r) if r else None


def create_review(token: str, went: bool, rating: int | None, comment: str, reason: str | None,
                  display_name: str) -> str:
    """"ok" | "notfound" | "nogarage" (հայտը գարաժի չի նշանակված) | "already" | "duplicate" (նույն համարից նույն գարաժին 30 օրում)։"""
    ctx = review_context(token)
    if ctx is None:
        return "notfound"
    if ctx["garage_id"] is None:
        return "nogarage"
    if ctx["review_id"] is not None:
        return "already"
    key = phone_key(ctx["phone"])
    with connect() as c:
        if went:
            dup = c.execute("""SELECT 1 FROM reviews WHERE garage_id=? AND phone_key=? AND went=1
                               AND created_at >= datetime('now','-30 days')""", (ctx["garage_id"], key)).fetchone()
            if dup:
                return "duplicate"
        try:
            c.execute("""INSERT INTO reviews(request_id, garage_id, service_id, phone_key, went, rating, comment, reason, display_name)
                         VALUES (?,?,(SELECT service_id FROM requests WHERE id=?),?,?,?,?,?,?)""",
                      (ctx["request_id"], ctx["garage_id"], ctx["request_id"], key, 1 if went else 0,
                       rating if went else None, comment, None if went else reason, display_name))
        except sqlite3.IntegrityError:
            return "already"
    return "ok"


def public_reviews(garage_id: int, limit: int = 20) -> list[dict]:
    with connect() as c:
        rows = c.execute("""SELECT rv.rating, rv.comment, rv.display_name, rv.created_at, s.name AS service
                            FROM reviews rv LEFT JOIN services s ON s.id = rv.service_id
                            WHERE rv.garage_id=? AND rv.went=1 AND rv.hidden=0
                            ORDER BY rv.id DESC LIMIT ?""", (garage_id, limit)).fetchall()
    return [dict(r) for r in rows]


def admin_reviews(garage_id: int | None = None, is_admin: bool = False) -> list[dict]:
    """Ադմինը տեսնում է ամեն ինչ (թաքցվածները և «չգնացի»-ները), գարաժը՝ միայն իր հրապարակային կարծիքները։"""
    where, args = [], []
    if garage_id is not None:
        where.append("rv.garage_id = ?"); args.append(garage_id)
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
        return c.execute("UPDATE reviews SET hidden=?, hidden_reason=? WHERE id=?",
                         (1 if hidden else 0, reason if hidden else None, review_id)).rowcount == 1
