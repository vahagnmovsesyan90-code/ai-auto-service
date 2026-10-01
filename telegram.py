"""Telegram ծանուցումներ (առանց արտաքին գրադարանների).
Միացնելու համար՝ @BotFather-ով ստեղծեք բոտ և Render-ում ավելացրեք TELEGRAM_BOT_TOKEN։"""
import hashlib
import hmac
import json
import os
import threading
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import queries
from auth import SECRET_KEY

SYNC = False            # թեստերում True՝ առանց thread-ի
BOT_USERNAME: str | None = None


def token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def enabled() -> bool:
    return bool(token())


def webhook_secret() -> str:
    """Telegram-ի webhook-ի գաղտնի վերնագիր (թույլատրվում են A-Za-z0-9_-)։"""
    return os.getenv("TELEGRAM_WEBHOOK_SECRET") or hmac.new(
        SECRET_KEY.encode(), b"telegram-webhook", hashlib.sha256).hexdigest()[:48]


def _call(method: str, payload: dict) -> dict:
    req = urllib.request.Request(f"https://api.telegram.org/bot{token()}/{method}",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def send_message(chat_id: int, text: str) -> None:
    def run():
        try:
            _call("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        except Exception as e:  # ցանց, արգելափակված բոտ... հայտը արդեն պահված է, ուստի չենք ընկնում
            print("Telegram սխալ:", type(e).__name__, e)
    if SYNC:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()


def ensure_username() -> str | None:
    global BOT_USERNAME
    if BOT_USERNAME is None and enabled():
        try:
            BOT_USERNAME = _call("getMe", {})["result"]["username"]
        except Exception as e:
            print("Telegram getMe սխալ:", type(e).__name__, e)
    return BOT_USERNAME


def setup(public_url: str | None) -> None:
    """Գործարկման ժամանակ՝ բոտի անունը և webhook-ը գրանցելը։"""
    ensure_username()
    if public_url:
        try:
            _call("setWebhook", {"url": public_url.rstrip("/") + "/telegram/webhook",
                                 "secret_token": webhook_secret(), "allowed_updates": ["message"]})
            print("Telegram webhook-ը գրանցված է")
        except Exception as e:
            print("Telegram setWebhook սխալ:", type(e).__name__, e)
    else:
        print("⚠ PUBLIC_URL/RENDER_EXTERNAL_URL նշված չէ. Telegram webhook-ը չի գրանցվել")


def format_request(r: dict) -> str:
    when = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    when = when.astimezone(ZoneInfo("Asia/Yerevan"))
    lines = ["🔔 Նոր հայտ", f"Անուն՝ {r['name']}", f"Հեռախոս՝ {r['phone']}",
             f"Ծառայություն՝ {r['service'] or '—'}",
             f"Գարաժ՝ {r['garage'] or 'նշանակված չէ (նշանակեք պանելում)'}"]
    if r["message"]:
        lines.append(f"Նշում՝ {r['message']}")
    lines.append(f"Ժամանակ՝ {when:%d.%m.%Y %H:%M}")
    return "\n".join(lines)


def notify_request(request_id: int, to_admin: bool = True) -> None:
    """Ծանուցում նոր/նշանակված հայտի մասին՝ գարաժին (եթե կապված է) և ադմինին։"""
    if not enabled():
        return
    r = queries.request_row(request_id)
    if r is None:
        return
    text, sent = format_request(r), set()
    if r["garage_chat_id"]:
        send_message(r["garage_chat_id"], text)
        sent.add(r["garage_chat_id"])
    if to_admin:
        admin = queries.get_admin_chat_id()
        if admin and admin not in sent:
            send_message(admin, text)


HELP = ("Բարև։ Ես AI Auto Service-ի ծանուցումների բոտն եմ։\n"
        "Կապվելու համար պանելում սեղմեք «Միացնել Telegram» և օգտագործեք ստացված հղումը կամ կոդը։")


def handle_update(update: dict) -> None:
    """Մշակում է Telegram-ի webhook-ի հաղորդագրությունը (/start ԿՈԴ)։"""
    msg = update.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if chat_id is None:
        return
    parts = text.split(maxsplit=1)
    if parts and parts[0].split("@")[0] == "/start" and len(parts) == 2:
        result = queries.consume_link_code(parts[1].strip(), chat_id)
        if result is None:
            send_message(chat_id, "Կոդը սխալ է կամ ժամկետանց է (վավեր է 1 ժամ)։ Պանելում ստացեք նորը։")
        elif result[0] == "admin":
            send_message(chat_id, "✓ Միացված է. գլխավոր ադմինի ծանուցումները կգան այս chat-ով։")
        else:
            send_message(chat_id, f"✓ Միացված է «{result[1]}» գարաժին. նոր հայտերը կգան այս chat-ով։")
    else:
        send_message(chat_id, HELP)
