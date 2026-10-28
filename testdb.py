"""Թեստերի համար ժամանակավոր Postgres բազա։ Յուրաքանչյուր թեստ իր բազան է ստանում
(DATABASE_URL-ի սերվերի վրա), որը պրոցեսի ավարտին ջնջվում է։ Իրական բազային չի դիպչում։
Օգտագործում՝ թեստի ամենասկզբում, մինչև api/db-ի import-ը.
    os.environ["DATABASE_URL"] = testdb.create()
"""
import atexit
import os
import secrets

import psycopg

DEFAULT_URL = "postgresql://autoservice:autoservice@127.0.0.1:5433/autoservice"


def _split(url: str) -> tuple[str, str]:
    base, _, name = url.rpartition("/")
    name, _, query = name.partition("?")
    return base, query


def create(prefix: str = "autoservice_test") -> str:
    """Ստեղծում է դատարկ բազա և վերադարձնում նրա URL-ը։ Ավարտին բազան ջնջվում է։"""
    base_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_URL
    base, query = _split(base_url)
    name = f"{prefix}_{os.getpid()}_{secrets.token_hex(3)}"
    admin = f"{base}/postgres" + (f"?{query}" if query else "")
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{name}"')
    atexit.register(drop, admin, name)
    os.environ["SEED_SAMPLE"] = "1"       # թեստերը նմուշային գարաժների վրա են հենվում (image-ում SEED_SAMPLE=0 է)
    return f"{base}/{name}" + (f"?{query}" if query else "")


def drop(admin_url: str, name: str) -> None:
    try:
        import db
        db.close()
    except Exception:
        pass
    try:
        with psycopg.connect(admin_url, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    except Exception as e:  # ջնջման ձախողումը թեստը չի տապալում
        print("ժամանակավոր բազան չջնջվեց:", e)
