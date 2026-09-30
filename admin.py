"""Փուլ 6. Ադմինի API (պաշտպանված է Bearer token-ով)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import queries as q
from auth import check_password, login_limiter, make_token, rate_limit, require_admin

TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$"

router = APIRouter(prefix="/admin")
secured = APIRouter(dependencies=[Depends(require_admin)])


class Login(BaseModel):
    password: str


class GarageIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)


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


def _found(ok: bool, what: str = "Գրառումը") -> None:
    if not ok:
        raise HTTPException(404, f"{what} չի գտնվել")


@router.post("/login")
def login(body: Login, request: Request):
    rate_limit(login_limiter, request)
    if not check_password(body.password):
        raise HTTPException(401, "Սխալ գաղտնաբառ")
    return {"token": make_token()}


@secured.get("/data")
def data():
    """Ամբողջ տվյալները ադմին պանելի համար՝ մեկ հարցումով։"""
    return {
        "services": [{"id": s.id, "name": s.name, "category": s.category,
                      "keywords": list(s.keywords)} for s in q.all_services()],
        "garages": [{
            "id": g.id, "name": g.name, "address": g.address, "phone": g.phone,
            "hours": [{"weekday": d, "open": f"{o:%H:%M}", "close": f"{c:%H:%M}"}
                      for d, (o, c) in sorted(g.hours.items())],
            "services": [{"service_id": gs.service_id, "price": gs.price,
                          "duration_min": gs.duration_min} for gs in g.services.values()],
        } for g in q.all_garages()],
        "requests": q.list_requests(),
    }


# ---- Գարաժներ ----
@secured.post("/garages", status_code=201)
def create_garage(body: GarageIn):
    return {"id": q.create_garage(body.name, body.address, body.phone)}


@secured.put("/garages/{garage_id}")
def update_garage(garage_id: int, body: GarageIn):
    _found(q.update_garage(garage_id, body.name, body.address, body.phone), "Գարաժը")
    return {"ok": True}


@secured.delete("/garages/{garage_id}")
def delete_garage(garage_id: int):
    _found(q.delete_garage(garage_id), "Գարաժը")
    return {"ok": True}


@secured.put("/garages/{garage_id}/services/{service_id}")
def put_offer(garage_id: int, service_id: int, body: OfferIn):
    _found(q.upsert_garage_service(garage_id, service_id, body.price, body.duration_min),
           "Գարաժը կամ ծառայությունը")
    return {"ok": True}


@secured.delete("/garages/{garage_id}/services/{service_id}")
def delete_offer(garage_id: int, service_id: int):
    _found(q.delete_garage_service(garage_id, service_id))
    return {"ok": True}


@secured.put("/garages/{garage_id}/hours")
def put_hours(garage_id: int, body: HoursIn):
    seen = set()
    for d in body.days:
        if d.weekday in seen:
            raise HTTPException(422, "Նույն օրը կրկնվում է")
        seen.add(d.weekday)
        if d.open >= d.close:
            raise HTTPException(422, "Բացման ժամը պետք է լինի փակման ժամից շուտ")
    _found(q.set_hours(garage_id, [(d.weekday, d.open, d.close) for d in body.days]), "Գարաժը")
    return {"ok": True}


# ---- Կատալոգ ----
@secured.post("/services", status_code=201)
def create_service(body: ServiceIn):
    return {"id": q.create_service(body.name, body.category, body.keywords)}


@secured.put("/services/{service_id}")
def update_service(service_id: int, body: ServiceIn):
    _found(q.update_service(service_id, body.name, body.category, body.keywords), "Ծառայությունը")
    return {"ok": True}


@secured.delete("/services/{service_id}")
def delete_service(service_id: int):
    _found(q.delete_service(service_id), "Ծառայությունը")
    return {"ok": True}


# ---- Հայտեր ----
@secured.patch("/requests/{request_id}")
def patch_request(request_id: int, body: StatusIn):
    _found(q.set_request_status(request_id, body.status), "Հայտը")
    return {"ok": True}


router.include_router(secured)
