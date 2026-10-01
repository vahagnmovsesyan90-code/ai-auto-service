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
            return c.execute("INSERT INTO requests(name,phone,garage_id,service_id,message) VALUES (?,?,?,?,?)",
                             (name, phone, garage_id, service_id, message)).lastrowid
    except sqlite3.IntegrityError:
        return None


def list_requests(garage_id: int | None = None) -> list[dict]:
    """Բոլոր հայտերը, կամ միայն տվյալ գարաժինը (գարաժի սեփականատիրոջ համար)։"""
    where, args = ("WHERE r.garage_id = ?", (garage_id,)) if garage_id is not None else ("", ())
    with connect() as c:
        rows = c.execute(f"""SELECT r.id, r.created_at, r.name, r.phone, r.message, r.status,
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


def set_request_status(request_id: int, status: str) -> bool:
    with connect() as c:
        return c.execute("UPDATE requests SET status=? WHERE id=?", (status, request_id)).rowcount == 1


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
