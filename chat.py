"""Chat-ի ուղեղը. AI (Claude) + գործիքներ, իսկ առանց բանալու՝ պարզ որոնում.
Բանալի՝ export ANTHROPIC_API_KEY=... (Windows՝ set ANTHROPIC_API_KEY=...)
Պատասխանը՝ (տեքստ, ռեժիմ, քարտեր). քարտերը գարաժների առաջարկներն են «Թողնել հայտ» կոճակով։"""
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from data import DAY_NAMES
from queries import (all_garages, all_services, garage_ratings, garages_for_service, get_garage,
                     get_service, is_open, rating_of)

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


_ARMENIAN = re.compile(r"[\u0531-\u0556\u0561-\u0587]")
_OTHER_LETTERS = re.compile(r"[A-Za-z\u0400-\u04FF]")
ARMENIAN_HINT = ("Խնդրում եմ նկարագրեք խնդիրը հայերեն տառերով, օրինակ՝ «արգելակելիս ճռռոց է լսվում»։ "
                 "Մակնիշները (BMW, Toyota) կարող եք գրել լատինատառ։")


def mostly_non_armenian(text: str) -> bool:
    """True, եթե տեքստի մեծ մասը լատինատառ կամ կիրիլիցա է (մակնիշի անունը՝ BMW, դեռ խնդիր չէ)։"""
    other = len(_OTHER_LETTERS.findall(text))
    return other >= 3 and other > len(_ARMENIAN.findall(text))


# ---- Գործիքներ (AI-ը կանչում է սրանք, թվերը գալիս են տվյալներից) ----------
def tool_list_services() -> list:
    return [{"id": s.id, "name": s.name, "category": s.category,
             "also_known_as": list(s.keywords)} for s in all_services()]


def tool_garages_for_service(service_id: int, open_now: bool = False) -> list:
    service = get_service(service_id)
    if service is None:
        return []
    now = datetime.now(TZ)
    ratings = garage_ratings()
    out = []
    for g, price in garages_for_service(service_id):
        if open_now and not is_open(g, now):
            continue
        out.append({"garage_id": g.id, "name": g.name, "address": g.address, "phone": g.phone,
                    "service_id": service_id, "service_name": service.name,
                    "price_amd": price, "duration_min": g.services[service_id].duration_min,
                    "open_now": is_open(g, now), "rating": rating_of(ratings, g.id)})
    return out


def tool_garage_info(garage_id: int) -> dict:
    g = get_garage(garage_id)
    if g is None:
        return {"error": "Գարաժը չի գտնվել"}
    return {"id": g.id, "name": g.name, "address": g.address, "phone": g.phone,
            "rating": rating_of(garage_ratings(), g.id),
            "hours": {DAY_NAMES[d]: f"{o:%H:%M}-{c:%H:%M}" for d, (o, c) in sorted(g.hours.items())},
            "closed_days": [DAY_NAMES[d] for d in range(7) if d not in g.hours],
            "services": [{"service_id": sid, "price_amd": gs.price} for sid, gs in g.services.items()]}


def run_tool(name: str, args: dict, sink: list | None = None) -> str:
    """sink-ը ստանում է garages_for_service-ի վերջին արդյունքը՝ քարտեր ցույց տալու համար։"""
    try:
        if name == "list_services":
            result = tool_list_services()
        elif name == "garages_for_service":
            result = tool_garages_for_service(int(args["service_id"]), bool(args.get("open_now", False)))
            if sink is not None:
                sink[:] = result
        elif name == "garage_info":
            result = tool_garage_info(int(args["garage_id"]))
        else:
            result = {"error": f"Անհայտ գործիք՝ {name}"}
    except (KeyError, ValueError, TypeError) as e:
        result = {"error": f"Սխալ արգումենտներ՝ {e}"}
    return json.dumps(result, ensure_ascii=False)


TOOLS = [
    {"name": "list_services", "description": "Ծառայությունների ամբողջ կատալոգը (id, անուն, կատեգորիա, նաև ինչպես են կոչում վարորդները)։",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "garages_for_service",
     "description": "Գարաժները, որոնք առաջարկում են ծառայությունը՝ գնի աճման կարգով (գին դրամով, տևողություն, հիմա բաց է թե ոչ, վարորդների գնահատական՝ միջին և կարծիքների թիվ)։ Վարորդը այս արդյունքը տեսնում է քարտերով։",
     "input_schema": {"type": "object", "properties": {
         "service_id": {"type": "integer"},
         "open_now": {"type": "boolean", "description": "true՝ միայն հիմա բաց գարաժները"}},
         "required": ["service_id"]}},
    {"name": "garage_info", "description": "Գարաժի հասցեն, հեռախոսը, աշխատանքային ժամերը, գները և գնահատականը։",
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
        "- Գները, ժամերը, հասցեներն ու հեռախոսները, գնահատականները վերցրու ՄԻԱՅՆ գործիքներից։ Երբեք մի հորինիր։\n"
        "- Խնդրի նկարագրությունից որոշիր կատալոգի ամենահարմար ծառայությունը։ Եթե մի քանի տարբերակ կա, նշիր։\n"
        "- Երբ գտնում ես գարաժներ (garages_for_service), վարորդը դրանք ավտոմատ տեսնում է քարտերով՝ գնով, "
        "գնահատականով և «Թողնել հայտ» կոճակով։ ՄԻ կրկնիր ամբողջ ցուցակը տեքստում. կարճ ասա առաջարկությունդ "
        "(օր.՝ ամենաէժանը, կամ ամենաբարձր գնահատվածը)։\n"
        "- Գնահատականը վստահելի է համարիր միայն եթե կարծիքների թիվը առնվազն 5 է. քիչ կարծիքի դեպքում ասա, որ կարծիքները քիչ են։\n"
        "- Դու չես ախտորոշում վերջնականապես. ասա «հավանաբար» և խորհուրդ տուր գարաժում ստուգել։\n"
        "- Եթե խնդիրը վտանգավոր է (արգելակները չեն աշխատում, ծուխ, յուղի ճնշման լամպ), խորհուրդ տուր չվարել։\n"
        "- Եթե ծառայությունը կատալոգում չկա, ազնվորեն ասա։\n"
        "- Վարորդը կարող է գրել լատինատառ կամ ռուսերեն. փորձիր հասկանալ, բայց պատասխանիր հայերեն տառերով և մեկ անգամ "
        "քաղաքավարի խնդրիր հաջորդիվ գրել հայերեն տառերով (մակնիշները՝ BMW, Toyota, կարելի է լատինատառ)։\n"
        "- Պատասխանիր հայերեն, կարճ և պարզ, գները՝ դրամով (֏)։ Ժամ ինքդ չես գրանցում. վարորդը քարտի վրա սեղմում է "
        "«Թողնել հայտ», և գարաժը նրան կզանգահարի։"
    )


# ---- AI ռեժիմ -----------------------------------------------------------------
def ai_reply(messages: list[dict]) -> tuple[str, list]:
    import anthropic
    client = anthropic.Anthropic()
    msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
    cards: list = []
    for _ in range(6):  # գործիքների կանչերի սահման
        resp = client.messages.create(model=MODEL, max_tokens=1024, system=system_prompt(),
                                      tools=TOOLS, messages=msgs)
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip(), cards
        msgs.append({"role": "assistant", "content": resp.content})
        results = [{"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input, cards)}
                   for b in resp.content if b.type == "tool_use"]
        msgs.append({"role": "user", "content": results})
    return "Չհաջողվեց պատասխանը պատրաստել։ Փորձեք նորից։", []


# ---- Պարզ ռեժիմ (առանց AI) ----------------------------------------------------
def simple_reply(text: str) -> tuple[str, list]:
    low = text.lower()
    if "բաց" in low and "գարաժ" in low:
        now = datetime.now(TZ)
        names = [g.name for g in all_garages() if is_open(g, now)]
        return (("Հիմա բաց են՝ " + ", ".join(names) + "։") if names else "Հիմա բոլոր գարաժները փակ են։"), []
    scored = sorted(((sum(k in low for k in s.keywords), s) for s in all_services()),
                    key=lambda p: -p[0])
    if not scored:
        return "Ծառայությունների կատալոգը դեռ դատարկ է։ Ադմինը պետք է ավելացնի ծառայություններ։", []
    if scored[0][0] == 0 and mostly_non_armenian(text):
        return ARMENIAN_HINT, []
    if scored[0][0] == 0:
        return ("Չհասկացա խնդիրը։ Նկարագրեք այլ կերպ, օրինակ՝ «արգելակելիս ճռռոց է լսվում»։ "
                "Առկա ծառայությունները՝ " + "; ".join(s.name for s in all_services()) + "։"), []
    service = scored[0][1]
    cards = tool_garages_for_service(service.id)
    if not cards:
        return f"Հավանական ծառայություն՝ {service.name}։ Դեռ ոչ մի գարաժ այն չի առաջարկում։", []
    return f"Հավանական ծառայություն՝ {service.name}։ Գարաժները՝ ամենաէժանից.", cards


def reply(messages: list[dict]) -> tuple[str, str, list]:
    """Վերադարձնում է (տեքստ, ռեժիմ, քարտեր)."""
    last = messages[-1]["content"] if messages else ""
    if os.getenv("ANTHROPIC_API_KEY") and ai_budget_ok():
        try:
            text, cards = ai_reply(messages)
            return text, "ai", cards
        except Exception as e:  # ցանց, բանալի, սահմանաչափ...
            print("AI սխալ:", repr(e))
            text, cards = simple_reply(last)
            return text + "\n\n(AI-ն հիմա անհասանելի է, պատասխանը պարզ որոնումից է։)", "simple", cards
    text, cards = simple_reply(last)
    return text, "simple", cards
