"""Մուտք (գլխավոր ադմին + գարաժների սեփականատերեր) և հարցումների սահմանափակում։"""
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Identity:
    role: str                  # "admin" | "garage"
    garage_id: int | None = None


# ---- Գաղտնաբառեր ----
_ITER = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITER).hex()
        return hmac.compare_digest(calc, h)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = hash_password("dummy-password")  # անհայտ մուտքանունի դեպքում նույն ժամանակը ծախսելու համար


def check_password(password: str) -> bool:  # գլխավոր ադմին
    return hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode())


# ---- Token ----
def _sign(msg: str) -> str:
    return hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()


def make_token(role: str, garage_id: int | None = None) -> str:
    payload = f"{'a' if role == 'admin' else 'g'}:{garage_id or 0}:{int(time.time()) + TOKEN_TTL}"
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str) -> Identity | None:
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        kind, gid, exp = payload.split(":")
        if int(exp) <= time.time():
            return None
        return Identity("admin") if kind == "a" else Identity("garage", int(gid))
    except ValueError:
        return None


def require_user(authorization: str = Header(default="")) -> Identity:
    user = verify_token(authorization[7:]) if authorization.startswith("Bearer ") else None
    if user is None:
        raise HTTPException(401, "Անհրաժեշտ է մուտք գործել")
    if user.role == "garage":
        import queries  # ուշացված import՝ ցիկլից խուսափելու համար
        if not queries.garage_login_active(user.garage_id):  # մուտքը հանված է կամ գարաժը ջնջված է
            raise HTTPException(401, "Մուտքն այլևս վավեր չէ")
    return user


# ---- Rate limit ----
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
