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

REQUESTS_DDL = """
CREATE TABLE IF NOT EXISTS requests (           -- վարորդների հայտերը
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- UTC
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    garage_id INTEGER REFERENCES garages(id) ON DELETE SET NULL,
    service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
    message TEXT NOT NULL DEFAULT '',
    -- փուլեր՝ new նոր, called զանգահարվել է, no_answer չպատասխանեց, booked ժամ պայմանավորվեց,
    -- visited այցելեց, declined հրաժարվեց
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new','called','no_answer','booked','visited','declined')),
    decline_reason TEXT
        CHECK (decline_reason IS NULL OR decline_reason IN ('price','far','other_garage','no_time','changed_mind','other')),
    status_changed_at TEXT,                      -- UTC
    first_response_at TEXT,                      -- UTC. առաջին անգամ «նոր»-ից դուրս գալու պահը
    review_token TEXT                            -- վարորդի գաղտնի հղում՝ գնահատելու համար (գարաժը չի տեսնում)
);
"""

REVIEWS_DDL = """
CREATE TABLE IF NOT EXISTS reviews (             -- վարորդի հաստատումը և գնահատականը (մեկ հայտ = մեկ կարծիք)
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL UNIQUE REFERENCES requests(id) ON DELETE CASCADE,
    garage_id INTEGER NOT NULL REFERENCES garages(id) ON DELETE CASCADE,
    service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
    phone_key TEXT NOT NULL,                     -- հեռախոսի վերջին 8 թվանշանը՝ կրկնակի կարծիքներից պաշտպանվելու համար
    went INTEGER NOT NULL CHECK (went IN (0, 1)),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    comment TEXT NOT NULL DEFAULT '',
    reason TEXT CHECK (reason IS NULL OR reason IN ('price','far','other_garage','no_time','changed_mind','other')),
    display_name TEXT NOT NULL DEFAULT '',
    hidden INTEGER NOT NULL DEFAULT 0,
    hidden_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((went = 1 AND rating IS NOT NULL) OR (went = 0 AND rating IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_reviews_garage ON reviews(garage_id);
"""

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
    phone TEXT NOT NULL,
    login TEXT,                                 -- գարաժի սեփականատիրոջ մուտքանունը (փոքրատառ)
    password_hash TEXT,
    telegram_chat_id INTEGER
);
CREATE TABLE IF NOT EXISTS link_codes (          -- Telegram կապի մեկանգամյա կոդեր (վավեր 1 ժամ)
    code TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('garage','admin')),
    garage_id INTEGER REFERENCES garages(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS garage_services (
    garage_id INTEGER NOT NULL REFERENCES garages(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    price INTEGER NOT NULL CHECK (price >= 0),  -- դրամ
    duration_min INTEGER NOT NULL CHECK (duration_min > 0),
    PRIMARY KEY (garage_id, service_id)
);
{REQUESTS_DDL}
CREATE TABLE IF NOT EXISTS working_hours (      -- միայն բաց օրերը
    garage_id INTEGER NOT NULL REFERENCES garages(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),  -- 0 = Երկուշաբթի
    open_time TEXT NOT NULL,                     -- "HH:MM"
    close_time TEXT NOT NULL,
    PRIMARY KEY (garage_id, weekday)
);
"""

_ready: set[str] = set()


def _migrate(conn: sqlite3.Connection) -> None:
    """Հին բազաներին ավելացնում է նոր սյուները (Փուլ 5-ի բազան չի կորչում)։"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(garages)")}
    for name, decl in (("login", "TEXT"), ("password_hash", "TEXT"), ("telegram_chat_id", "INTEGER")):
        if name not in cols:
            conn.execute(f"ALTER TABLE garages ADD COLUMN {name} {decl}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_garages_login ON garages(login) WHERE login IS NOT NULL")
    # հին requests աղյուսակ (միայն new/done). վերակառուցում ենք, «done»-ը դառնում է «called»
    sql = (conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='requests'").fetchone() or [""])[0]
    if "'done'" in sql:
        conn.executescript("ALTER TABLE requests RENAME TO requests_old;" + REQUESTS_DDL + """
            INSERT INTO requests(id, created_at, name, phone, garage_id, service_id, message, status)
            SELECT id, created_at, name, phone, garage_id, service_id, message,
                   CASE status WHEN 'done' THEN 'called' ELSE status END FROM requests_old;
            DROP TABLE requests_old;""")
    rcols = {r[1] for r in conn.execute("PRAGMA table_info(requests)")}
    if "review_token" not in rcols:
        conn.execute("ALTER TABLE requests ADD COLUMN review_token TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_requests_review_token ON requests(review_token) WHERE review_token IS NOT NULL")
    conn.commit()


def connect() -> sqlite3.Connection:
    """Բացում է կապը. առաջին անգամ ստեղծում է աղյուսակները և լցնում նմուշային տվյալները։"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(DB_PATH) not in _ready:
        conn.executescript(SCHEMA.replace("{REQUESTS_DDL}", REQUESTS_DDL))
        _migrate(conn)
        conn.executescript(REVIEWS_DDL)   # միայն requests-ի վերակառուցումից հետո, որպեսզի FK-ները չկոտրվեն
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
            conn.execute("INSERT INTO garages(id,name,address,phone) VALUES (?,?,?,?)", (g.id, g.name, g.address, g.phone))
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
