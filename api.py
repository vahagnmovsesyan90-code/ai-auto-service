"""Փուլ 2. FastAPI. գործարկում՝ uvicorn api:app --reload
Փաստաթղթավորում՝ http://127.0.0.1:8000/docs"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from data import DAY_NAMES, Garage
import admin
import chat as chat_engine
import queries
from auth import chat_limiter, rate_limit, request_limiter
from queries import (all_garages, all_services, find_services, garages_for_service, get_garage,
                     get_service, is_open, open_garages)

app = FastAPI(title="AI Auto Service API", version="1.0")
app.include_router(admin.router)
TZ = ZoneInfo("Asia/Yerevan")


# ---- Պատասխանի մոդելներ ---------------------------------------------------
class ServiceOut(BaseModel):
    id: int
    name: str
    category: str


class DayHours(BaseModel):
    day: str
    open: time
    close: time


class GarageOut(BaseModel):
    id: int
    name: str
    address: str
    phone: str
    hours: list[DayHours]


class OfferOut(BaseModel):
    garage: GarageOut
    price: int
    duration_min: int


def garage_out(g: Garage) -> GarageOut:
    return GarageOut(
        id=g.id, name=g.name, address=g.address, phone=g.phone,
        hours=[DayHours(day=DAY_NAMES[d], open=o, close=c)
               for d, (o, c) in sorted(g.hours.items())],
    )


# ---- Endpoint-ներ ----------------------------------------------------------
@app.get("/")
def root():
    return {"name": "AI Auto Service API", "docs": "/docs", "chat": "/app", "panel": "/panel"}


@app.get("/services", response_model=list[ServiceOut])
def list_services(q: str | None = None):
    """Կատալոգի ծառայությունները. ?q=արգելակ՝ որոնման համար։"""
    return find_services(q) if q else all_services()


@app.get("/services/{service_id}", response_model=ServiceOut)
def read_service(service_id: int):
    service = get_service(service_id)
    if service is None:
        raise HTTPException(404, "Ծառայությունը չի գտնվել")
    return service


@app.get("/services/{service_id}/garages", response_model=list[OfferOut])
def garages_by_service(service_id: int, open_now: bool = False):
    """Գարաժներ՝ գնի աճման կարգով. ?open_now=true՝ միայն հիմա բաց գարաժները։"""
    if get_service(service_id) is None:
        raise HTTPException(404, "Ծառայությունը չի գտնվել")
    now = datetime.now(TZ)
    offers = []
    for g, price in garages_for_service(service_id):
        if open_now and not is_open(g, now):
            continue
        offers.append(OfferOut(garage=garage_out(g), price=price,
                               duration_min=g.services[service_id].duration_min))
    return offers


@app.get("/garages", response_model=list[GarageOut])
def list_garages():
    return [garage_out(g) for g in all_garages()]


@app.get("/garages/open", response_model=list[GarageOut])
def garages_open_now():
    """Գարաժները, որոնք բաց են հիմա (Երևանի ժամանակով)։"""
    return [garage_out(g) for g in open_garages(datetime.now(TZ))]


@app.get("/garages/{garage_id}", response_model=GarageOut)
def read_garage(garage_id: int):
    garage = get_garage(garage_id)
    if garage is None:
        raise HTTPException(404, "Գարաժը չի գտնվել")
    return garage_out(garage)


# ---- Chat (Փուլ 3 + 4) ------------------------------------------------------
class Message(BaseModel):
    role: str  # "user" կամ "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


class ChatResponse(BaseModel):
    reply: str
    mode: str  # "ai" կամ "simple"


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    rate_limit(chat_limiter, request)
    msgs = [m.model_dump() for m in req.messages[-20:]]  # վերջին 20 հաղորդագրությունը
    if not msgs or msgs[-1]["role"] != "user" or not msgs[-1]["content"].strip():
        raise HTTPException(400, "Վերջին հաղորդագրությունը պետք է լինի օգտատիրոջից")
    text, mode = chat_engine.reply(msgs)
    return ChatResponse(reply=text, mode=mode)


@app.get("/app", include_in_schema=False)
def chat_page():
    return FileResponse(Path(__file__).parent / "chat.html")


# ---- Վարորդի հայտ (Փուլ 7) ---------------------------------------------------
class RequestIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=6, max_length=25, pattern=r"^[0-9+\-() ]+$")
    garage_id: int | None = None
    service_id: int | None = None
    message: str = Field(default="", max_length=500)


@app.post("/requests", status_code=201)
def create_request(body: RequestIn, request: Request):
    """Վարորդը թողնում է հայտ. ադմինը տեսնում է այն պանելում։"""
    rate_limit(request_limiter, request)
    rid = queries.create_request(body.name.strip(), body.phone.strip(),
                                 body.garage_id, body.service_id, body.message.strip())
    if rid is None:
        raise HTTPException(400, "Գարաժը կամ ծառայությունը գոյություն չունի")
    return {"id": rid}


@app.get("/panel", include_in_schema=False)
def admin_page():
    return FileResponse(Path(__file__).parent / "admin.html")
