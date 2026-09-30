"""Ադմինի մուտք և հարցումների սահմանափակում (առանց արտաքին գրադարանների)."""
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

APP_ENV = os.getenv("APP_ENV", "dev")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")
TOKEN_TTL = 12 * 3600  # 12 ժամ

if APP_ENV == "production" and (not ADMIN_PASSWORD or not SECRET_KEY):
    raise RuntimeError("Production-ում պարտադիր են ADMIN_PASSWORD և SECRET_KEY փոփոխականները")
if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = "admin"
    print("⚠ ADMIN_PASSWORD-ը նշված չէ. dev ռեժիմում գաղտնաբառը «admin» է")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)  # dev՝ սերվերի վերագործարկումից հետո նորից մուտք


def check_password(password: str) -> bool:
    return hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode())


def _sign(msg: str) -> str:
    return hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    exp = str(int(time.time()) + TOKEN_TTL)
    return f"{exp}.{_sign(exp)}"


def verify_token(token: str) -> bool:
    try:
        exp, sig = token.split(".")
        return hmac.compare_digest(sig, _sign(exp)) and int(exp) > time.time()
    except ValueError:
        return False


def require_admin(authorization: str = Header(default="")) -> None:
    if not authorization.startswith("Bearer ") or not verify_token(authorization[7:]):
        raise HTTPException(401, "Անհրաժեշտ է մուտք գործել")


class RateLimiter:
    """Առավելագույնը `limit` հարցում `window` վայրկյանում մեկ IP-ի համար։"""
    def __init__(self, limit: int, window: int = 60):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now, q = time.time(), self.hits[key]
        while q and q[0] < now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def rate_limit(limiter: RateLimiter, request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not limiter.check(ip):
        raise HTTPException(429, "Չափազանց շատ հարցումներ, փորձեք մի փոքր հետո")


chat_limiter = RateLimiter(20)    # chat՝ պաշտպանում է AI-ի ծախսերը
request_limiter = RateLimiter(5)  # հայտեր
login_limiter = RateLimiter(10)   # մուտք՝ գաղտնաբառի կռահման դեմ
