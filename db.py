"""Փուլ 5. SQLite տվյալների բազա.
Հրամաններ՝
  python db.py reset                      # ջնջել բազան և նորից լցնել նմուշային տվյալներով
  python db.py set-price ԳԱՐԱԺ ԾԱՌԱՅՈՒԹՅՈՒՆ ԳԻՆ   # օր.՝ python db.py set-price 3 2 13000
  python db.py show                       # ցույց տալ գները
"""
import os
import sqlite3
import sys
from pathlib import Path

from data import GARAGES, SERVICES

DB_PATH = Path(os.getenv("AUTOSERVICE_DB", Path(__file__).parent / "autoservice.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT ''          -- ստորակետով բաժանված
);
CREATE TABLE IF NOT EXISTS garages (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    phone TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS garage_services (
    garage_id INTEGER NOT NULL REFERENCES garages(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    price INTEGER NOT NULL CHECK (price >= 0),  -- դրամ
    duration_min INTEGER NOT NULL CHECK (duration_min > 0),
    PRIMARY KEY (garage_id, service_id)
);
CREATE TABLE IF NOT EXISTS requests (           -- վարորդների հայտերը
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- UTC
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    garage_id INTEGER REFERENCES garages(id) ON DELETE SET NULL,
    service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','done'))
);
CREATE TABLE IF NOT EXISTS working_hours (      -- միայն բաց օրերը
    garage_id INTEGER NOT NULL REFERENCES garages(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),  -- 0 = Երկուշաբթի
    open_time TEXT NOT NULL,                     -- "HH:MM"
    close_time TEXT NOT NULL,
    PRIMARY KEY (garage_id, weekday)
);
"""

_ready: set[str] = set()


def connect() -> sqlite3.Connection:
    """Բացում է կապը. առաջին անգամ ստեղծում է աղյուսակները և լցնում նմուշային տվյալները։"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(DB_PATH) not in _ready:
        conn.executescript(SCHEMA)
        if (os.getenv("SEED_SAMPLE", "1") == "1"
                and conn.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0):
            seed(conn)
        _ready.add(str(DB_PATH))
    return conn


def seed(conn: sqlite3.Connection) -> None:
    with conn:
        for s in SERVICES:
            conn.execute("INSERT INTO services VALUES (?,?,?,?)",
                         (s.id, s.name, s.category, ",".join(s.keywords)))
        for g in GARAGES:
            conn.execute("INSERT INTO garages VALUES (?,?,?,?)", (g.id, g.name, g.address, g.phone))
            for day, (o, c) in g.hours.items():
                conn.execute("INSERT INTO working_hours VALUES (?,?,?,?)",
                             (g.id, day, f"{o:%H:%M}", f"{c:%H:%M}"))
            for gs in g.services.values():
                conn.execute("INSERT INTO garage_services VALUES (?,?,?,?)",
                             (g.id, gs.service_id, gs.price, gs.duration_min))


def reset() -> None:
    DB_PATH.unlink(missing_ok=True)
    _ready.discard(str(DB_PATH))
    connect().close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "reset":
        reset()
        print("Բազան վերականգնված է՝", DB_PATH)
    elif cmd == "set-price" and len(sys.argv) == 5:
        from queries import set_price
        ok = set_price(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
        print("Գինը թարմացվեց ✓" if ok else "Այդպիսի գարաժ/ծառայություն չկա")
    elif cmd == "show":
        with connect() as c:
            for r in c.execute("""SELECT g.id gid, g.name g, s.id sid, s.name s, gs.price
                                  FROM garage_services gs JOIN garages g ON g.id = gs.garage_id
                                  JOIN services s ON s.id = gs.service_id ORDER BY g.id, s.id"""):
                print(f"[{r['gid']}] {r['g']:16} [{r['sid']}] {r['s']:42} {r['price']:>7,} ֏")
    else:
        print(__doc__)
