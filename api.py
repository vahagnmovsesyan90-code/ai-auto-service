"""Փուլ 2. FastAPI. գործարկում՝ uvicorn api:app --reload
Փաստաթղթավորում՝ http://127.0.0.1:8000/docs"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

import hmac
import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
from pydantic import BaseModel, Field

from data import DAY_NAMES, Garage
import admin
import chat as chat_engine
import queries
import telegram
from typing import Literal

from auth import RateLimiter, chat_limiter, rate_limit, request_limiter
from queries import (all_garages, all_services, find_services, garages_for_service, get_garage,
                     get_service, is_open, open_garages)

APP_VERSION = "2.7"


def html_page(name: str) -> HTMLResponse:
    """HTML էջը՝ տարբերակի համարով և Cache-Control: no-cache-ով. բրաուզերը ամեն անգամ ստուգում է նոր տարբերակը,
    որպեսզի թարմացումից հետո հին էջը չմնա քեշում։"""
    text = (Path(__file__).parent / name).read_text(encoding="utf-8").replace("__APP_VERSION__", APP_VERSION)
    return HTMLResponse(text, headers={"Cache-Control": "no-cache"})


@asynccontextmanager
async def lifespan(_app):
    """Գործարկման ժամանակ՝ Telegram բոտի webhook-ի գրանցում (եթե TELEGRAM_BOT_TOKEN-ը նշված է)։"""
    if telegram.enabled():
        url = os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL")
        threading.Thread(target=telegram.setup, args=(url,), daemon=True).start()
    yield


app = FastAPI(title="AI Auto Service API", version=APP_VERSION, lifespan=lifespan)
app.include_router(admin.router)
_static = Path(__file__).parent / "static"
if _static.is_dir():   # եթե թղթապանակը չվերբեռնվեց, սերվերը չի ընկնում (միայն քարտեզը չի երևա)
    app.mount("/static", StaticFiles(directory=_static), name="static")
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


class RatingOut(BaseModel):
    avg: float | None = None     # միջին (1-5), None՝ եթե կարծիք չկա
    count: int = 0
    score: float | None = None   # Bayes-ի միջին՝ դասավորելու համար


class GarageOut(BaseModel):
    id: int
    name: str
    address: str
    phone: str
    hours: list[DayHours]
    rating: RatingOut = RatingOut()
    lat: float | None = None
    lng: float | None = None
    open_now: bool = False


class OfferOut(BaseModel):
    garage: GarageOut
    price: int
    duration_min: int


def garage_out(g: Garage, ratings: dict | None = None) -> GarageOut:
    ratings = queries.garage_ratings() if ratings is None else ratings
    return GarageOut(
        id=g.id, name=g.name, address=g.address, phone=g.phone, lat=g.lat, lng=g.lng,
        rating=RatingOut(**queries.rating_of(ratings, g.id)), open_now=is_open(g, datetime.now(TZ)),
        hours=[DayHours(day=DAY_NAMES[d], open=o, close=c)
               for d, (o, c) in sorted(g.hours.items())],
    )


# ---- Endpoint-ներ ----------------------------------------------------------
@app.get("/")
def root():
    return {"name": "AI Auto Service API", "docs": "/docs", "chat": "/app", "panel": "/panel", "version": APP_VERSION}


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
    offers, ratings = [], queries.garage_ratings()
    for g, price in garages_for_service(service_id):
        if open_now and not is_open(g, now):
            continue
        offers.append(OfferOut(garage=garage_out(g, ratings), price=price,
                               duration_min=g.services[service_id].duration_min))
    return offers


@app.get("/garages", response_model=list[GarageOut])
def list_garages():
    ratings = queries.garage_ratings()
    return [garage_out(g, ratings) for g in all_garages()]


@app.get("/garages/open", response_model=list[GarageOut])
def garages_open_now():
    """Գարաժները, որոնք բաց են հիմա (Երևանի ժամանակով)։"""
    ratings = queries.garage_ratings()
    return [garage_out(g, ratings) for g in open_garages(datetime.now(TZ))]


class CatalogServiceOut(BaseModel):
    service_id: int
    name: str
    category: str
    price_amd: int
    duration_min: int


class CatalogItemOut(BaseModel):
    id: int
    name: str
    address: str
    phone: str
    open_now: bool
    rating: RatingOut
    services_count: int


class CatalogPageOut(BaseModel):
    items: list[CatalogItemOut]
    total: int
    page: int
    per_page: int
    matched_services: list[str] = []   # տեքստից հասկացված ծառայությունները (ցույց ենք տալիս վարորդին)
    mode: str = "none"                 # ai | simple | none


@app.get("/api/catalog", response_model=CatalogPageOut)
def catalog_api(q: str = "", page: int = 1, per_page: int = 20):
    """Գարաժների ցուցակը էջերով (մինչև 50 մեկ էջում)։ Որոնումը իմաստային է՝ տեքստը AI-ն (ինչպես օգնականում) վերածում է
    ծառայությունների, և վերադարձվում են այդ ծառայությունն առաջարկող գարաժները. անունով/հասցեով համընկնումը նույնպես հաշվվում է։"""
    page, per_page = max(1, page), max(1, min(per_page, 50))
    q = q[:100]
    ids, mode = chat_engine.resolve_services(q) if q.strip() else ([], "none")
    rows, total = queries.catalog_page(q, ids, (page - 1) * per_page, per_page)
    now, ratings = datetime.now(TZ), queries.garage_ratings()
    items = [CatalogItemOut(id=r["garage"].id, name=r["garage"].name, address=r["garage"].address, phone=r["garage"].phone,
                            open_now=is_open(r["garage"], now), rating=RatingOut(**queries.rating_of(ratings, r["garage"].id)),
                            services_count=r["services_count"]) for r in rows]
    names = {s.id: s.name for s in all_services()}
    return CatalogPageOut(items=items, total=total, page=page, per_page=per_page,
                          matched_services=[names[i] for i in ids if i in names], mode=mode)


@app.get("/garages/{garage_id}/services", response_model=list[CatalogServiceOut])
def garage_services_api(garage_id: int):
    """Գարաժի ծառայությունները գներով (գարաժի էջ)։"""
    if get_garage(garage_id) is None:
        raise HTTPException(404, "Գարաժը չի գտնվել")
    return [CatalogServiceOut(service_id=r["service_id"], name=r["name"], category=r["category"],
                              price_amd=r["price"], duration_min=r["duration_min"]) for r in queries.garage_services(garage_id)]


@app.get("/my", include_in_schema=False)
def my_requests_page():
    """Վարորդի «Իմ հայտերը» էջը՝ գնահատում աստղերով (տվյալները վարորդի սարքում են)։"""
    return html_page("my.html")


@app.get("/catalog", include_in_schema=False)
def catalog_page():
    """Գարաժների էջը (ցուցակ, որոնում, էջավորում)։"""
    return html_page("garages.html")


@app.get("/catalog/{garage_id}", include_in_schema=False)
def garage_page(garage_id: int):
    """Մեկ գարաժի էջը՝ ծառայություններով, ժամերով, կարծիքներով և հայտի ձևով։"""
    if get_garage(garage_id) is None:
        raise HTTPException(404, "Գարաժը չի գտնվել")
    return html_page("garage.html")


# ---- Հավելվածի ներբեռնում (/download էջ, փաթեթները՝ webview/bin/publish.sh-ից) ----------------
# Ֆայլի անունը խիստ է. aiauto-<տարբերակ>-<հարթակ>[-<ճարտարապետություն>].<ext> (օր.՝ aiauto-1.0-android.apk,
# aiauto-1.0.0-windows-x64.exe)։ Չհամապատասխանող անունով ֆայլերը էջին չեն երևում և չեն տրվում։
DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR") or Path(__file__).parent / "downloads")
DOWNLOAD_NAME = re.compile(r"^aiauto-(?P<version>\d[\w.]*)-(?P<platform>[a-z]+)(?:-(?P<arch>[a-z0-9_]+))?\.(?P<ext>[A-Za-z]+)$")
DOWNLOAD_PLATFORMS = {"android": ["apk"], "windows": ["exe", "msi"], "macos": ["dmg"], "linux": ["AppImage", "deb"]}
_ARCH_RANK = {None: 0, "x64": 1, "arm64": 2}


def _version_key(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))


def list_downloads() -> dict:
    """Պատրաստի փաթեթների ցանկը՝ ըստ հարթակի, նորը վերևում (x64-ը arm64-ից առաջ)։"""
    found = {k: [] for k in DOWNLOAD_PLATFORMS}
    if DOWNLOADS_DIR.is_dir():
        for f in DOWNLOADS_DIR.iterdir():
            m = DOWNLOAD_NAME.match(f.name)
            if not f.is_file() or not m or m["ext"] not in DOWNLOAD_PLATFORMS.get(m["platform"], []):
                continue
            st = f.stat()
            found[m["platform"]].append({"name": f.name, "version": m["version"], "arch": m["arch"], "ext": m["ext"], "size": st.st_size,
                                         "released_at": datetime.fromtimestamp(st.st_mtime, TZ).strftime("%Y-%m-%d"), "url": f"/downloads/{f.name}"})
    for builds in found.values():
        builds.sort(key=lambda b: (tuple(-x for x in _version_key(b["version"])), _ARCH_RANK.get(b["arch"], 3)))
    versions = sorted({b["version"] for bs in found.values() for b in bs}, key=_version_key)
    stores = {k: v for k, v in {"ios": os.getenv("APP_STORE_URL"), "android": os.getenv("PLAY_STORE_URL")}.items() if v}
    return {"version": versions[-1] if versions else None, "platforms": found, "stores": stores}


@app.get("/download", include_in_schema=False)
def download_page():
    """Հավելվածի ներբեռնման էջը (Android, iPhone/iPad, Windows, macOS, Linux)։"""
    return html_page("download.html")


@app.get("/api/downloads")
def downloads_api():
    """Փաթեթների ցանկը՝ տարբերակ, չափ, ամսաթիվ, հղում. ֆայլերն իրենք՝ /downloads/<անուն>։"""
    return list_downloads()


@app.api_route("/downloads/{name}", methods=["GET", "HEAD"], include_in_schema=False)
def download_file(name: str):
    m = DOWNLOAD_NAME.match(name)
    path = DOWNLOADS_DIR / name
    if not m or m["ext"] not in DOWNLOAD_PLATFORMS.get(m["platform"], []) or not path.is_file():
        raise HTTPException(404, "Ֆայլը չի գտնվել")
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def assetlinks():
    """Android App Links. կայքի հղումները բացվում են հավելվածում (release ստորագրության SHA-256-ը՝ assetlinks.json-ում)։"""
    f = Path(__file__).parent / "assetlinks.json"
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type="application/json")


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


class CardOut(BaseModel):
    """Գարաժի առաջարկ chat-ի քարտի համար."""
    garage_id: int
    name: str
    address: str
    phone: str
    service_id: int
    service_name: str
    price_amd: int
    duration_min: int
    open_now: bool
    rating: RatingOut
    lat: float | None = None
    lng: float | None = None


class ChatResponse(BaseModel):
    reply: str
    mode: str  # "ai" կամ "simple"
    cards: list[CardOut] = []


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    rate_limit(chat_limiter, request)
    msgs = [m.model_dump() for m in req.messages[-20:]]  # վերջին 20 հաղորդագրությունը
    if not msgs or msgs[-1]["role"] != "user" or not msgs[-1]["content"].strip():
        raise HTTPException(400, "Վերջին հաղորդագրությունը պետք է լինի օգտատիրոջից")
    text, mode, cards = chat_engine.reply(msgs)
    if sum(1 for m in msgs if m["role"] == "user") == 1:   # միայն խոսակցության առաջին հարցը. հաջորդները ճշտումներ են
        try:
            queries.log_query(msgs[-1]["content"], cards[0]["service_id"] if cards else None, mode)
        except Exception:   # վիճակագրությունը երբեք չպետք է տապալի պատասխանը
            pass
    return ChatResponse(reply=text, mode=mode, cards=cards)


# ---- Հաճախ հարցվող հարցեր (chat-ի chip-երը) ----
DEFAULT_QUESTIONS = ["Արգելակելիս ճռռոց է լսվում", "Օդորակիչը չի սառեցնում"]
OPEN_NOW_QUESTION = "Ո՞ր գարաժն է հիմա բաց"
POPULAR_CACHE: dict = {}
POPULAR_CACHE_SEC = int(os.getenv("POPULAR_CACHE_SEC", "600"))


class QuestionOut(BaseModel):
    text: str
    service_id: int | None = None


@app.get("/popular-questions", response_model=list[QuestionOut])
def popular():
    """Chat-ի «հաճախ հարցվող» chip-երը. վերջին 30 օրվա ամենաշատ հարցված 2 ծառայության օրինակ հարցը
    + «Ո՞ր գարաժն է հիմա բաց»։ Քիչ տվյալի դեպքում՝ լռելյայն հարցերը։ Քեշ՝ 10 րոպե։"""
    now = datetime.now().timestamp()
    if POPULAR_CACHE.get("until", 0) > now:
        return POPULAR_CACHE["data"]
    try:
        top = queries.popular_questions(days=30, limit=2, min_total=20)
    except Exception:
        top = []
    out = [{"text": t["text"], "service_id": t["service_id"]} for t in top]
    for d in DEFAULT_QUESTIONS:                       # լրացնում ենք մինչև 2-ը, կրկնություն չանելով
        if len(out) >= 2:
            break
        if all(o["text"] != d for o in out):
            out.append({"text": d, "service_id": None})
    out.append({"text": OPEN_NOW_QUESTION, "service_id": None})
    POPULAR_CACHE.update(until=now + POPULAR_CACHE_SEC, data=out)
    return out


@app.get("/app", include_in_schema=False)
def chat_page():
    return html_page("chat.html")


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
    telegram.notify_request(rid)  # գարաժին (եթե կապված է) և գլխավոր ադմինին
    row = queries.request_row(rid)
    # review_token-ը տրվում է միայն վարորդին (գարաժը այն չի տեսնում), որպեսզի կարծիքները չկեղծվեն.
    # վարորդը գնահատում է chat-ի «Իմ հայտերը» բաժնում՝ POST /reviews/{token}-ով
    return {"id": rid, "garage": row["garage"], "review_token": row["review_token"] if row["garage_id"] else None}


@app.get("/panel", include_in_schema=False)
def admin_page():
    return html_page("admin.html")


@app.get("/panel/{section:path}", include_in_schema=False)
def panel_section_page(section: str):
    """Ադմինի բաժինների ուղիները (/panel/requests, /panel/garages/3, …). նույն էջն է, բաժինը էջը ինքն է կարդում հասցեից։"""
    return html_page("admin.html")


@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request,
                           x_telegram_bot_api_secret_token: str = Header(default="")):
    """Telegram-ը այստեղ է ուղարկում բոտին գրված հաղորդագրությունները (/start ԿՈԴ)։"""
    if not telegram.enabled() or not hmac.compare_digest(x_telegram_bot_api_secret_token,
                                                         telegram.webhook_secret()):
        raise HTTPException(403, "Forbidden")
    try:
        telegram.handle_update(await request.json())
    except Exception as e:  # Telegram-ին միշտ 200, որպեսզի նույն update-ը անվերջ չկրկնի
        print("Webhook սխալ:", type(e).__name__, e)
    return {"ok": True}


# ---- Գնահատականներ (վարորդի կողմից) -------------------------------------------
review_limiter = RateLimiter(10)   # գնահատման ուղարկում
check_limiter = RateLimiter(60)    # «Իմ հայտերը»-ի ստուգում. առանձին, որպեսզի էջի թարմացումները չարգելափակեն գնահատումը


class ReviewIn(BaseModel):
    went: bool
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str = Field(default="", max_length=500)
    reason: Literal["price", "far", "other_garage", "no_time", "changed_mind", "other"] | None = None
    display_name: str = Field(default="", max_length=30)


class ReviewOut(BaseModel):
    rating: int
    comment: str
    display_name: str
    created_at: str
    service: str | None = None


@app.get("/garages/{garage_id}/reviews", response_model=list[ReviewOut])
def garage_reviews(garage_id: int, limit: int = Query(default=20, ge=1, le=50), offset: int = Query(default=0, ge=0)):
    """Գարաժի հրապարակային կարծիքները (նորը առաջինը, թաքցվածները՝ ոչ)։ limit/offset՝ գարաժի էջի «Ցույց տալ ավելին»-ի համար։"""
    if get_garage(garage_id) is None:
        raise HTTPException(404, "Գարաժը չի գտնվել")
    return queries.public_reviews(garage_id, limit, offset)


class MyRequestsIn(BaseModel):
    tokens: list[str] = Field(max_length=200)
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=50)
    status: str = Field(default="all", pattern="^(all|pending|rated)$")   # ֆիլտր՝ բոլորը | սպասում են գնահատման | գնահատված


@app.post("/my-requests/check")
def check_my_requests(body: MyRequestsIn, request: Request):
    """Վարորդի սարքում պահված հայտերի ստուգում մեկ հարցումով՝ էջավորումը սերվերում։ `requests`՝ պահանջված էջը (նորը վերևում),
    `valid`՝ բոլոր գոյություն ունեցող token-ները իրենց «գնահատված» նշանով (սարքի պահոցը մաքրելու և հաշվիչի համար)։"""
    rate_limit(check_limiter, request)
    tokens = [t for t in body.tokens if 0 < len(t) <= 64]
    rows = [r for r in queries.existing_review_tokens(tokens) if r["has_garage"]]
    rows.sort(key=lambda r: (r["created_at"], r["request_id"]), reverse=True)
    pending = [r for r in rows if not r["already_reviewed"]]
    shown = pending if body.status == "pending" else [r for r in rows if r["already_reviewed"]] if body.status == "rated" else rows
    start = (body.page - 1) * body.per_page
    return {"requests": shown[start:start + body.per_page], "total": len(shown), "page": body.page, "per_page": body.per_page,
            "all_total": len(rows), "pending_total": len(pending), "rated_total": len(rows) - len(pending),
            "valid": [{"token": r["token"], "done": r["already_reviewed"]} for r in rows]}


@app.post("/reviews/{token}", status_code=201)
def post_review(token: str, body: ReviewIn, request: Request):
    """Վարորդը հաստատում է՝ գնաց թե ոչ. եթե այո՝ գնահատում է (1-5), եթե ոչ՝ նշում է պատճառը։"""
    rate_limit(review_limiter, request)
    if body.went and body.rating is None:
        raise HTTPException(422, "Նշեք գնահատականը (1-5)")
    if not body.went and body.reason is None:
        raise HTTPException(422, "Նշեք, թե ինչու չգնացիք")
    res = queries.create_review(token, body.went, body.rating, body.comment.strip(), body.reason, body.display_name.strip())
    messages = {"notfound": (404, "Հղումը անվավեր է"), "nogarage": (400, "Այս հայտը գարաժի չի նշանակված"),
                "already": (409, "Այս հայտի համար արդեն թողնվել է կարծիք")}
    if res == "updated":   # նույն գարաժին 30 օրում երկրորդ «գնացի» գնահատականը թարմացնում է նախորդը (կրկնակի կարծիք չի ստեղծվում)
        return JSONResponse({"ok": True, "updated": True}, status_code=200)
    if res != "ok":
        raise HTTPException(*messages[res])
    return {"ok": True}
