"""Ադմինի API. երկու դեր՝ գլխավոր ադմին (ամեն ինչ) և գարաժի սեփականատեր (միայն իր գարաժը և հայտերը)։"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import queries as q
import telegram
from auth import (DUMMY_HASH, Identity, check_password, hash_password, login_limiter, make_token,
                  rate_limit, require_user, verify_password)

TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$"
LOGIN_RE = r"^[A-Za-z0-9._-]{3,40}$"

router = APIRouter(prefix="/admin")


# ---- Մոդելներ ----
class Login(BaseModel):
    login: str = Field(default="", max_length=40)   # դատարկ կամ «admin»՝ գլխավոր ադմին
    password: str = Field(max_length=200)


class GarageIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)


class AccountIn(BaseModel):
    login: str = Field(pattern=LOGIN_RE)
    password: str = Field(min_length=8, max_length=100)


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(default="Այլ", max_length=60)
    keywords: list[str] = Field(default_factory=list, max_length=30)


class OfferIn(BaseModel):
    price: int = Field(ge=0, le=10_000_000)
    duration_min: int = Field(gt=0, le=1440)


class DayIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    open: str = Field(pattern=TIME_RE)
    close: str = Field(pattern=TIME_RE)


class HoursIn(BaseModel):
    days: list[DayIn] = Field(max_length=7)


class StatusIn(BaseModel):
    status: Literal["new", "done"]


class AssignIn(BaseModel):
    garage_id: int | None = None


# ---- Իրավունքներ ----
def need_admin(user: Identity) -> None:
    if user.role != "admin":
        raise HTTPException(403, "Միայն գլխավոր ադմինի համար")


def need_garage(user: Identity, garage_id: int) -> None:
    """Գարաժի սեփականատերը կարող է գործել միայն իր գարաժի հետ։"""
    if user.role == "garage" and user.garage_id != garage_id:
        raise HTTPException(403, "Այս գարաժը ձեզ չի պատկանում")


def found(ok: bool, what: str = "Գրառումը") -> None:
    if not ok:
        raise HTTPException(404, f"{what} չի գտնվել")


# ---- Մուտք ----
@router.post("/login")
def login(body: Login, request: Request):
    rate_limit(login_limiter, request)
    name = body.login.strip().lower()
    bad = HTTPException(401, "Սխալ մուտքանուն կամ գաղտնաբառ")
    if name in ("", "admin"):
        if not check_password(body.password):
            raise bad
        return {"token": make_token("admin"), "role": "admin"}
    row = q.find_garage_login(name)
    ok = verify_password(body.password, row[1] if row else DUMMY_HASH)
    if row is None or not ok:
        raise bad
    return {"token": make_token("garage", row[0]), "role": "garage"}


# ---- Տվյալներ ----
@router.get("/data")
def data(user: Identity = Depends(require_user)):
    """Ադմինին՝ ամեն ինչ. գարաժին՝ միայն իր գարաժը և իր հայտերը։"""
    accounts = q.garage_accounts()
    garages = [g for g in q.all_garages() if user.role == "admin" or g.id == user.garage_id]
    return {
        "role": user.role,
        "services": [{"id": s.id, "name": s.name, "category": s.category,
                      "keywords": list(s.keywords)} for s in q.all_services()],
        "garages": [{
            "id": g.id, "name": g.name, "address": g.address, "phone": g.phone,
            "login": accounts[g.id]["login"], "telegram_linked": accounts[g.id]["telegram_linked"],
            "hours": [{"weekday": d, "open": f"{o:%H:%M}", "close": f"{c:%H:%M}"}
                      for d, (o, c) in sorted(g.hours.items())],
            "services": [{"service_id": gs.service_id, "price": gs.price,
                          "duration_min": gs.duration_min} for gs in g.services.values()],
        } for g in garages],
        "requests": q.list_requests(user.garage_id if user.role == "garage" else None),
        "telegram": {"enabled": telegram.enabled(), "bot_username": telegram.BOT_USERNAME,
                     "admin_linked": q.get_admin_chat_id() is not None if user.role == "admin" else None},
    }


# ---- Գարաժներ ----
@router.post("/garages", status_code=201)
def create_garage(body: GarageIn, user: Identity = Depends(require_user)):
    need_admin(user)
    return {"id": q.create_garage(body.name, body.address, body.phone)}


@router.put("/garages/{garage_id}")
def update_garage(garage_id: int, body: GarageIn, user: Identity = Depends(require_user)):
    need_garage(user, garage_id)
    found(q.update_garage(garage_id, body.name, body.address, body.phone), "Գարաժը")
    return {"ok": True}


@router.delete("/garages/{garage_id}")
def delete_garage(garage_id: int, user: Identity = Depends(require_user)):
    need_admin(user)
    found(q.delete_garage(garage_id), "Գարաժը")
    return {"ok": True}


@router.put("/garages/{garage_id}/services/{service_id}")
def put_offer(garage_id: int, service_id: int, body: OfferIn, user: Identity = Depends(require_user)):
    need_garage(user, garage_id)
    found(q.upsert_garage_service(garage_id, service_id, body.price, body.duration_min),
          "Գարաժը կամ ծառայությունը")
    return {"ok": True}


@router.delete("/garages/{garage_id}/services/{service_id}")
def delete_offer(garage_id: int, service_id: int, user: Identity = Depends(require_user)):
    need_garage(user, garage_id)
    found(q.delete_garage_service(garage_id, service_id))
    return {"ok": True}


@router.put("/garages/{garage_id}/hours")
def put_hours(garage_id: int, body: HoursIn, user: Identity = Depends(require_user)):
    need_garage(user, garage_id)
    seen = set()
    for d in body.days:
        if d.weekday in seen:
            raise HTTPException(422, "Նույն օրը կրկնվում է")
        seen.add(d.weekday)
        if d.open >= d.close:
            raise HTTPException(422, "Բացման ժամը պետք է լինի փակման ժամից շուտ")
    found(q.set_hours(garage_id, [(d.weekday, d.open, d.close) for d in body.days]), "Գարաժը")
    return {"ok": True}


# ---- Գարաժի մուտքի տվյալներ (միայն գլխավոր ադմին) ----
@router.put("/garages/{garage_id}/account")
def set_account(garage_id: int, body: AccountIn, user: Identity = Depends(require_user)):
    need_admin(user)
    if body.login.lower() == "admin":
        raise HTTPException(422, "«admin» մուտքանունը վերապահված է")
    res = q.set_garage_login(garage_id, body.login, hash_password(body.password))
    if res == "taken":
        raise HTTPException(409, "Այս մուտքանունը արդեն զբաղված է")
    found(res == "ok", "Գարաժը")
    return {"ok": True}


@router.delete("/garages/{garage_id}/account")
def delete_account(garage_id: int, user: Identity = Depends(require_user)):
    need_admin(user)
    found(q.clear_garage_login(garage_id), "Գարաժը")
    return {"ok": True}


# ---- Telegram ----
def _need_telegram() -> None:
    if not telegram.enabled():
        raise HTTPException(400, "Telegram-ը կարգավորված չէ (TELEGRAM_BOT_TOKEN)")


def _link_info(code: str) -> dict:
    username = telegram.ensure_username()
    return {"code": code, "bot_username": username, "command": f"/start {code}",
            "url": f"https://t.me/{username}?start={code}" if username else None}


@router.post("/garages/{garage_id}/telegram/link")
def garage_link(garage_id: int, user: Identity = Depends(require_user)):
    need_garage(user, garage_id)
    _need_telegram()
    found(q.get_garage(garage_id) is not None, "Գարաժը")
    return _link_info(q.create_link_code("garage", garage_id))


@router.delete("/garages/{garage_id}/telegram")
def garage_unlink(garage_id: int, user: Identity = Depends(require_user)):
    need_garage(user, garage_id)
    found(q.unlink_garage_telegram(garage_id), "Գարաժը")
    return {"ok": True}


@router.post("/telegram/link")
def admin_link(user: Identity = Depends(require_user)):
    need_admin(user)
    _need_telegram()
    return _link_info(q.create_link_code("admin"))


@router.delete("/telegram")
def admin_unlink(user: Identity = Depends(require_user)):
    need_admin(user)
    q.unlink_admin_telegram()
    return {"ok": True}


# ---- Կատալոգ (միայն գլխավոր ադմին) ----
@router.post("/services", status_code=201)
def create_service(body: ServiceIn, user: Identity = Depends(require_user)):
    need_admin(user)
    return {"id": q.create_service(body.name, body.category, body.keywords)}


@router.put("/services/{service_id}")
def update_service(service_id: int, body: ServiceIn, user: Identity = Depends(require_user)):
    need_admin(user)
    found(q.update_service(service_id, body.name, body.category, body.keywords), "Ծառայությունը")
    return {"ok": True}


@router.delete("/services/{service_id}")
def delete_service(service_id: int, user: Identity = Depends(require_user)):
    need_admin(user)
    found(q.delete_service(service_id), "Ծառայությունը")
    return {"ok": True}


# ---- Հայտեր ----
@router.patch("/requests/{request_id}")
def patch_request(request_id: int, body: StatusIn, user: Identity = Depends(require_user)):
    r = q.request_row(request_id)
    if r is None or (user.role == "garage" and r["garage_id"] != user.garage_id):
        raise HTTPException(404, "Հայտը չի գտնվել")  # այլ գարաժի հայտի գոյությունը չենք բացահայտում
    q.set_request_status(request_id, body.status)
    return {"ok": True}


@router.put("/requests/{request_id}/garage")
def assign_request(request_id: int, body: AssignIn, user: Identity = Depends(require_user)):
    """Գլխավոր ադմինը հայտը նշանակում է գարաժին. գարաժը ստանում է Telegram ծանուցում։"""
    need_admin(user)
    res = q.set_request_garage(request_id, body.garage_id)
    if res == "badgarage":
        raise HTTPException(400, "Գարաժը գոյություն չունի")
    found(res == "ok", "Հայտը")
    if body.garage_id is not None:
        telegram.notify_request(request_id, to_admin=False)
    return {"ok": True}
