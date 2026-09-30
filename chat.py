"""Chat-ի ուղեղը. AI (Claude) + գործիքներ, իսկ առանց բանալու՝ պարզ որոնում.
Բանալի՝ export ANTHROPIC_API_KEY=... (Windows՝ set ANTHROPIC_API_KEY=...)"""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from data import DAY_NAMES
from queries import all_garages, all_services, garages_for_service, get_garage, is_open

TZ = ZoneInfo("Asia/Yerevan")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "200"))  # AI-ի պատասխանների առավելագույնը օրական (ծախսի պաշտպանություն)
_ai_usage = {"day": None, "n": 0}


def ai_budget_ok() -> bool:
    """Հաշվում է AI-ի կանչերը օրական. սահմանը անցնելիս chat-ը անցնում է պարզ ռեժիմի։"""
    today = datetime.now(TZ).date()
    if _ai_usage["day"] != today:
        _ai_usage.update(day=today, n=0)
    if _ai_usage["n"] >= AI_DAILY_LIMIT:
        return False
    _ai_usage["n"] += 1
    return True


# ---- Գործիքներ (AI-ը կանչում է սրանք, թվերը գալիս են տվյալներից) ----------
def tool_list_services() -> list:
    return [{"id": s.id, "name": s.name, "category": s.category} for s in all_services()]


def tool_garages_for_service(service_id: int, open_now: bool = False) -> list:
    now = datetime.now(TZ)
    out = []
    for g, price in garages_for_service(service_id):
        if open_now and not is_open(g, now):
            continue
        out.append({"garage_id": g.id, "name": g.name, "address": g.address,
                    "phone": g.phone, "price_amd": price,
                    "duration_min": g.services[service_id].duration_min,
                    "open_now": is_open(g, now)})
    return out


def tool_garage_info(garage_id: int) -> dict:
    g = get_garage(garage_id)
    if g is None:
        return {"error": "Գարաժը չի գտնվել"}
    return {"id": g.id, "name": g.name, "address": g.address, "phone": g.phone,
            "hours": {DAY_NAMES[d]: f"{o:%H:%M}-{c:%H:%M}" for d, (o, c) in sorted(g.hours.items())},
            "closed_days": [DAY_NAMES[d] for d in range(7) if d not in g.hours],
            "services": [{"service_id": sid, "price_amd": gs.price} for sid, gs in g.services.items()]}


def run_tool(name: str, args: dict) -> str:
    try:
        if name == "list_services":
            result = tool_list_services()
        elif name == "garages_for_service":
            result = tool_garages_for_service(int(args["service_id"]), bool(args.get("open_now", False)))
        elif name == "garage_info":
            result = tool_garage_info(int(args["garage_id"]))
        else:
            result = {"error": f"Անհայտ գործիք՝ {name}"}
    except (KeyError, ValueError, TypeError) as e:
        result = {"error": f"Սխալ արգումենտներ՝ {e}"}
    return json.dumps(result, ensure_ascii=False)


TOOLS = [
    {"name": "list_services", "description": "Ծառայությունների ամբողջ կատալոգը (id, անուն, կատեգորիա)։",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "garages_for_service",
     "description": "Գարաժները, որոնք առաջարկում են ծառայությունը՝ գնի աճման կարգով (գին դրամով, տևողություն, հիմա բաց է թե ոչ)։",
     "input_schema": {"type": "object", "properties": {
         "service_id": {"type": "integer"},
         "open_now": {"type": "boolean", "description": "true՝ միայն հիմա բաց գարաժները"}},
         "required": ["service_id"]}},
    {"name": "garage_info", "description": "Գարաժի հասցեն, հեռախոսը, աշխատանքային ժամերը և գները։",
     "input_schema": {"type": "object", "properties": {"garage_id": {"type": "integer"}},
                      "required": ["garage_id"]}},
]


def system_prompt() -> str:
    now = datetime.now(TZ)
    return (
        "Դու ավտոսերվիսների հարթակի օգնականն ես։ Վարորդը նկարագրում է մեքենայի խնդիրը, "
        "դու օգնում ես գտնել համապատասխան ծառայությունը և գարաժը։\n"
        f"Հիմա Երևանում՝ {DAY_NAMES[now.weekday()]}, {now:%Y-%m-%d %H:%M}։\n"
        "Կանոններ.\n"
        "- Գները, ժամերը, հասցեներն ու հեռախոսները վերցրու ՄԻԱՅՆ գործիքներից։ Երբեք մի հորինիր։\n"
        "- Խնդրի նկարագրությունից որոշիր կատալոգի ամենահարմար ծառայությունը։ Եթե մի քանի տարբերակ կա, նշիր։\n"
        "- Դու չես ախտորոշում վերջնականապես. ասա «հավանաբար» և խորհուրդ տուր գարաժում ստուգել։\n"
        "- Եթե խնդիրը վտանգավոր է (արգելակները չեն աշխատում, ծուխ, յուղի ճնշման լամպ), խորհուրդ տուր չվարել։\n"
        "- Եթե ծառայությունը կատալոգում չկա, ազնվորեն ասա։\n"
        "- Պատասխանիր հայերեն, կարճ և պարզ, գները՝ դրամով (֏)։ Գրանցում դեռ չես կարող անել։"
    )


# ---- AI ռեժիմ -----------------------------------------------------------------
def ai_reply(messages: list[dict]) -> str:
    import anthropic
    client = anthropic.Anthropic()
    msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
    for _ in range(6):  # գործիքների կանչերի սահման
        resp = client.messages.create(model=MODEL, max_tokens=1024, system=system_prompt(),
                                      tools=TOOLS, messages=msgs)
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        msgs.append({"role": "assistant", "content": resp.content})
        results = [{"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input)}
                   for b in resp.content if b.type == "tool_use"]
        msgs.append({"role": "user", "content": results})
    return "Չհաջողվեց պատասխանը պատրաստել։ Փորձեք նորից։"


# ---- Պարզ ռեժիմ (առանց AI) ----------------------------------------------------
def simple_reply(text: str) -> str:
    low = text.lower()
    if "բաց" in low and "գարաժ" in low:
        now = datetime.now(TZ)
        names = [g.name for g in all_garages() if is_open(g, now)]
        return ("Հիմա բաց են՝ " + ", ".join(names) + "։") if names else "Հիմա բոլոր գարաժները փակ են։"
    scored = sorted(((sum(k in low for k in s.keywords), s) for s in all_services()),
                    key=lambda p: -p[0])
    if not scored or scored[0][0] == 0:
        return ("Չհասկացա խնդիրը։ Նկարագրեք այլ կերպ, օրինակ՝ «արգելակելիս ճռռոց է լսվում»։ "
                "Առկա ծառայությունները՝ " + "; ".join(s.name for s in all_services()) + "։")
    service = scored[0][1]
    lines = [f"Հավանական ծառայություն՝ {service.name}։", "Գարաժները՝ ամենաէժանից."]
    for o in tool_garages_for_service(service.id):
        state = "բաց է հիմա" if o["open_now"] else "հիմա փակ է"
        lines.append(f"• {o['name']} — {o['price_amd']:,} ֏, {o['duration_min']} ր, {o['address']} ({state})")
    return "\n".join(lines)


def reply(messages: list[dict]) -> tuple[str, str]:
    """Վերադարձնում է (տեքստ, ռեժիմ)."""
    last = messages[-1]["content"] if messages else ""
    if os.getenv("ANTHROPIC_API_KEY") and ai_budget_ok():
        try:
            return ai_reply(messages), "ai"
        except Exception as e:  # ցանց, բանալի, սահմանաչափ...
            print("AI սխալ:", repr(e))
            return simple_reply(last) + "\n\n(AI-ն հիմա անհասանելի է, պատասխանը պարզ որոնումից է։)", "simple"
    return simple_reply(last), "simple"
