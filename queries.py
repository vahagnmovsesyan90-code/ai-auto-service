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


def list_requests() -> list[dict]:
    with connect() as c:
        rows = c.execute("""SELECT r.id, r.created_at, r.name, r.phone, r.message, r.status,
                                   r.garage_id, g.name AS garage, r.service_id, s.name AS service
                            FROM requests r LEFT JOIN garages g ON g.id = r.garage_id
                            LEFT JOIN services s ON s.id = r.service_id
                            ORDER BY (r.status = 'new') DESC, r.id DESC""").fetchall()
    return [dict(r) for r in rows]


def set_request_status(request_id: int, status: str) -> bool:
    with connect() as c:
        return c.execute("UPDATE requests SET status=? WHERE id=?", (status, request_id)).rowcount == 1
