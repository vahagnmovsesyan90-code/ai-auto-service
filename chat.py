"""Chat-ի ուղեղը. AI (Claude) + գործիքներ, իսկ առանց բանալու՝ պարզ որոնում.
Բանալի՝ export ANTHROPIC_API_KEY=... (Windows՝ set ANTHROPIC_API_KEY=...)
Պատասխանը՝ (տեքստ, ռեժիմ, քարտեր). քարտերը գարաժների առաջարկներն են «Թողնել հայտ» կոճակով։"""
import json
import logging
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from data import DAY_NAMES
from queries import (all_garages, all_services, garage_ratings, garages_for_service, get_garage,
                     get_service, is_open, rating_of)

TZ = ZoneInfo("Asia/Yerevan")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
EFFORT = os.getenv("AI_EFFORT", "low")  # low՝ արագ և էժան chat-ի համար. medium/high՝ եթե պատասխանները թույլ են
MAX_TOKENS = 4096  # thinking-ը նույնպես հաշվվում է այստեղ, ուստի 1024-ը քիչ է
log = logging.getLogger("chat")
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
                    "open_now": is_open(g, now), "rating": rating_of(ratings, g.id),
                    "lat": g.lat, "lng": g.lng})
    return out


def tool_garage_info(garage_id: int) -> dict:
    g = get_garage(garage_id)
    if g is None:
        return {"error": "Գարաժը չի գտնվել"}
    return {"id": g.id, "name": g.name, "address": g.address, "phone": g.phone,
            "has_location": g.lat is not None,
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
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True},
    {"name": "garages_for_service",
     "description": "Գարաժները, որոնք առաջարկում են ծառայությունը՝ գնի աճման կարգով (գին դրամով, տևողություն, հիմա բաց է թե ոչ, վարորդների գնահատական՝ միջին և կարծիքների թիվ)։ Վարորդը այս արդյունքը տեսնում է քարտերով։",
     "input_schema": {"type": "object", "properties": {
         "service_id": {"type": "integer"},
         "open_now": {"type": "boolean", "description": "true՝ միայն հիմա բաց գարաժները"}},
         "required": ["service_id", "open_now"], "additionalProperties": False}, "strict": True},
    {"name": "garage_info", "description": "Գարաժի հասցեն, հեռախոսը, աշխատանքային ժամերը, գները և գնահատականը։",
     "input_schema": {"type": "object", "properties": {"garage_id": {"type": "integer"}},
                      "required": ["garage_id"], "additionalProperties": False}, "strict": True},
]


def catalog_text() -> str:
    """Կատալոգը system prompt-ի համար. AI-ն այն տեսնում է առանց գործիք կանչելու։"""
    lines = []
    for s in all_services():
        kw = f" (վարորդները նաև ասում են՝ {', '.join(s.keywords)})" if s.keywords else ""
        lines.append(f"- id {s.id}: {s.name} — {s.category}{kw}")
    return "\n".join(lines) or "- (կատալոգը դեռ դատարկ է)"


def system_prompt() -> list[dict]:
    """Երկու բլոկ. առաջինը կայուն է (կանոններ + կատալոգ) և քեշավորվում է, երկրորդը՝ ժամը։"""
    stable = (
        "Դու ավտոսերվիսների հարթակի օգնականն ես Երևանում։ Վարորդը նկարագրում է մեքենայի խնդիրը, "
        "դու գտնում ես կատալոգի համապատասխան ծառայությունը և գարաժները։\n\n"
        "Ծառայությունների կատալոգ.\n" + catalog_text() + "\n\n"
        "Ինչպես հասկանալ վարորդին.\n"
        "- Վարորդները գրում են այնպես, ինչպես խոսում են. խոսակցական և ռուսերենից փոխառված բառեր հայատառ "
        "(ակ, պագրիշկա, բալոն, ռեզին, դիսկ, տորմուզ, կալոդկա, մասլո, ստոյկա, ամորտ, կոնդիցիոներ, կոմպ), լատինատառ "
        "հայերեն (pagrishka, tormuz, masloy), ռուսերեն կամ անգլերեն, ուղղագրական սխալներով, մեքենայի մասի "
        "անունով կամ միայն ախտանիշով («ղեկը թափ է տալիս», «ծուխ է գալիս»)։\n"
        "- Հասկացիր իմաստը և ինքդ կապիր կատալոգի ծառայության հետ. կատալոգի բառերը օրինակ են, ոչ սահման։ "
        "Օրինակ՝ «ակ», «անիվ», «պագրիշկա», «բալոն», «ռեզին», «շին», «դիսկ», «կալյոսա» բոլորը անվադողի/անիվի խնդիր են. «տորմուզ», «կալոդկա» արգելակ. "
        "«մասլո» յուղ. «ստոյկա», «ամորտ», «թակոց է գալիս փոսերի վրա» կախոց. «check engine», «լամպ վառվեց» ախտորոշում. "
        "«կոնդիցիոներ», «չի սառեցնում» օդորակիչ։\n"
        "- Գործիր, մի հարցաքննիր։ Եթե կատալոգում մեկ հավանական ծառայություն կա, միանգամից կանչիր garages_for_service "
        "և մեկ նախադասությամբ ասա, թե ինչ ես հասկացել («Հասկացա՝ անիվի խնդիր է»)։ Հստակեցնող հարց տուր միայն այն դեպքում, "
        "երբ երկու տարբեր ծառայություն իրոք հավասարապես հավանական են, և նույնիսկ այդ դեպքում՝ մեկ կարճ հարց։\n"
        "- Եթե կոնկրետ աշխատանքը կատալոգում չկա (օր.՝ դիսկի ուղղում, լամպի փոխարինում), ընտրիր ամենամոտ ծառայությունը, "
        "ցույց տուր այդ գարաժները և ասա, որ ճշգրիտ աշխատանքը գարաժը տեղում կորոշի։\n\n"
        "Կանոններ.\n"
        "- Գները, ժամերը, հասցեները, հեռախոսները և գնահատականները վերցրու միայն գործիքներից։\n"
        "- Երբ garages_for_service-ը արդյունք է տալիս, վարորդը դրանք տեսնում է քարտերով՝ գնով, գնահատականով և "
        "«Թողնել հայտ» կոճակով։ Ցուցակը տեքստում մի կրկնիր. կարճ ասա, թե որն է հարմար (ամենաէժանը, ամենաբարձր գնահատվածը)։\n"
        "- Գնահատականը վստահելի է, եթե կարծիքների թիվը առնվազն 5 է. քիչ կարծիքի դեպքում ասա, որ կարծիքները քիչ են։\n"
        "- Դու վերջնական ախտորոշում չես տալիս. ասա «հավանաբար» և խորհուրդ տուր գարաժում ստուգել։\n"
        "- Եթե խնդիրը վտանգավոր է (արգելակները չեն աշխատում, ծուխ, յուղի ճնշման լամպ), խորհուրդ տուր չվարել։\n"
        "- Եթե ծառայությունը կատալոգում չկա, ազնվորեն ասա։\n"
        "- Պատասխանիր հայերեն տառերով, կարճ և պարզ, գները՝ դրամով, նշանը «֏» (ոչ «ֆ»), օրինակ՝ 5000 ֏։ "
        "Ինչ լեզվով կամ տառերով էլ վարորդը գրի, պարզապես պատասխանիր. երբեք մի խնդրիր նրան գրել հայերեն տառերով։\n"
        "- Գրիր սովորական տեքստով, առանց markdown-ի (առանց **, #, աղյուսակների). ցուցակի համար տողի սկզբում «•» դիր։\n"
        "- Ժամ ինքդ չես գրանցում. վարորդը քարտի վրա սեղմում է «Թողնել հայտ», և գարաժը նրան կզանգահարի։"
    )
    now = datetime.now(TZ)
    return [{"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"Հիմա Երևանում՝ {DAY_NAMES[now.weekday()]}, {now:%Y-%m-%d %H:%M}։"}]


# ---- AI ռեժիմ -----------------------------------------------------------------
def ai_reply(messages: list[dict]) -> tuple[str, list]:
    import anthropic
    client = anthropic.Anthropic()
    msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
    cards: list = []
    for _ in range(6):  # գործիքների կանչերի սահման
        resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system_prompt(),
                                      tools=TOOLS, output_config={"effort": EFFORT}, messages=msgs)
        u = resp.usage
        log.info("ai model=%s stop=%s in=%s cache_read=%s out=%s req=%s", resp.model, resp.stop_reason,
                 u.input_tokens, getattr(u, "cache_read_input_tokens", None), u.output_tokens,
                 getattr(resp, "_request_id", None))
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not text:  # refusal, max_tokens կամ դատարկ պատասխան. վարորդին դատարկ տող չենք ցույց տալիս
                log.warning("ai դատարկ պատասխան, stop=%s", resp.stop_reason)
                text, more = simple_reply(messages[-1]["content"])
                return text, cards or more
            return text, cards
        msgs.append({"role": "assistant", "content": resp.content})
        results = [{"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input, cards)}
                   for b in resp.content if b.type == "tool_use"]
        msgs.append({"role": "user", "content": results})
    return "Չհաջողվեց պատասխանը պատրաստել։ Փորձեք նորից։", cards


# ---- Պարզ ռեժիմ (առանց AI) ----------------------------------------------------
def simple_reply(text: str) -> tuple[str, list]:
    low = text.lower()
    if "բաց" in low and "գարաժ" in low:
        now = datetime.now(TZ)
        names = [g.name for g in all_garages() if is_open(g, now)]
        return (("Հիմա բաց են՝ " + ", ".join(names) + "։") if names else "Հիմա բոլոր գարաժները փակ են։"), []
    scored = sorted(((sum(kw_hit(k, low) for k in s.keywords), s) for s in all_services()),
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


# ---- Գարաժների որոնում (կատալոգի էջ). տեքստ -> ծառայություններ, ինչպես օգնականում -------
_resolve_cache: dict[str, tuple[list[int], str]] = {}


def kw_hit(keyword: str, low: str) -> bool:
    """Բանալի բառը տեքստում։ Կարճ (≤3 տառ) բառերը՝ միայն բառասկզբում («ակ»-ը չի համընկնում «արգելակ»-ի հետ, բայց համընկնում է «ակերը»-ի),
    երկարները՝ որպես ենթատող («ճռռ» -> «ճռռոց»)։"""
    k = keyword.strip().lower()
    if not k:
        return False
    if len(k) <= 3:
        return re.search(r"(?<!\w)" + re.escape(k), low) is not None
    return k in low


def _resolve_simple(low: str) -> list[int]:
    """Առանց AI. ծառայության անուն, կատեգորիա կամ բանալի բառեր տեքստում։"""
    return [s.id for s in all_services()
            if s.name.lower() in low or kw_hit(low, s.name.lower()) or kw_hit(low, s.category.lower())   # կարճ հարցումը՝ միայն բառասկզբում («ակ»-ը ≠ «արգելակ»)
            or any(kw_hit(k, low) for k in s.keywords)]


def _resolve_ai(text: str) -> list[int]:
    """AI-ը կատալոգից ընտրում է վարորդի նկարագրությանը համապատասխան ծառայությունները (մեկ կանչ, առանց գործիքների)։"""
    import anthropic
    client = anthropic.Anthropic()
    valid = {s.id for s in all_services()}
    system = ("Դու ավտոսերվիսի օգնական ես։ Վարորդը գարաժ է փնտրում և նկարագրում է խնդիրը կամ ծառայությունը։ "
              "Կատալոգից ընտրիր ԲՈԼՈՐ ծառայությունները, որոնք համապատասխանում են նրա տեքստին (նաև անուղղակի կամ խոսակցական "
              "նկարագրության դեպքում)։ Հաշվի առ, որ վարորդները հաճախ գրում են խոսակցական կամ ռուսերենից եկած բառերով, նաև լատինատառ "
              "(օր.՝ «ակ», «պագրիշկա», «шина», «pagrishka» = անվադող/անիվ, «կոլոդկա» = արգելակային կոլոդկա, «ամորտիզատոր» = կախոց)։ "
              "Հոմանիշ բառերը պետք է տան նույն արդյունքը։ Պատասխանիր ՄԻԱՅՆ JSON զանգվածով՝ id-ների ցուցակ, օր.՝ [2,5]։ Եթե ոչինչ չի համապատասխանում՝ []։\n\n"
              "Կատալոգ՝\n" + catalog_text())
    resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system, output_config={"effort": EFFORT},
                                  messages=[{"role": "user", "content": text}])
    raw = "".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\[[\d,\s]*\]", raw)
    ids = json.loads(m.group(0)) if m else []
    log.info("ai search %r -> %s req=%s", text, ids, getattr(resp, "_request_id", None))
    return [i for i in dict.fromkeys(ids) if i in valid]


def resolve_services(text: str) -> tuple[list[int], str]:
    """Վարորդի ազատ տեքստ -> համապատասխան ծառայությունների id-ներ և ռեժիմ («ai» | «simple»)։
    Նույն հարցումը հիշվում է, որպեսզի էջավորումն ու կրկնվող որոնումները AI չկանչեն։"""
    low = " ".join(text.lower().split())[:100]
    if not low:
        return [], "none"
    if low in _resolve_cache:
        return _resolve_cache[low]
    simple = _resolve_simple(low)
    ids, mode = simple, "simple"
    if len(low) >= 3 and os.getenv("ANTHROPIC_API_KEY") and ai_budget_ok():   # 1-2 տառի համար AI իմաստ չունի
        try:
            ids, mode = list(dict.fromkeys(_resolve_ai(low) + simple)), "ai"   # AI-ի ընտրությունը + բանալի բառերի համընկնումները. հոմանիշները կայուն արդյունք են տալիս
        except Exception as e:  # ցանց, բանալի, սահմանաչափ... -> պարզ որոնում
            log.error("AI որոնման սխալ: %r", e)
    if len(_resolve_cache) >= 500:
        _resolve_cache.clear()
    _resolve_cache[low] = (ids, mode)
    return ids, mode


def reply(messages: list[dict]) -> tuple[str, str, list]:
    """Վերադարձնում է (տեքստ, ռեժիմ, քարտեր)."""
    last = messages[-1]["content"] if messages else ""
    if os.getenv("ANTHROPIC_API_KEY") and ai_budget_ok():
        try:
            text, cards = ai_reply(messages)
            return text, "ai", cards
        except Exception as e:  # ցանց, բանալի, սահմանաչափ...
            log.error("AI սխալ: %r", e)
            text, cards = simple_reply(last)
            return text + "\n\n(AI-ն հիմա անհասանելի է, պատասխանը պարզ որոնումից է։)", "simple", cards
    text, cards = simple_reply(last)
    return text, "simple", cards
