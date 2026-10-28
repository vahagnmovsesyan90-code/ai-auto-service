"""AI ռեժիմի թեստ՝ իրական anthropic SDK, բայց կեղծ սերվեր (իրական բանալի պետք չէ).
Գործարկում՝ python test_ai.py"""
import json, os, tempfile
import testdb
os.environ["DATABASE_URL"] = testdb.create()
os.environ["ANTHROPIC_API_KEY"] = "fake-key"

import anthropic
try:
    import httpx2 as httpx   # նոր SDK-ները օգտագործում են httpx2
except ImportError:
    import httpx
import chat

calls = []


def msg(content, stop):
    return httpx.Response(200, json={"id": "msg_x", "type": "message", "role": "assistant",
        "model": "claude-sonnet-5-5", "content": content, "stop_reason": stop,
        "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})


def handler(request: httpx.Request):
    body = json.loads(request.content)
    calls.append(body)
    n = len(calls)
    if n == 1:   # AI-ը նախ խնդրում է կատալոգը
        return msg([{"type": "text", "text": "Ստուգեմ։"},
                    {"type": "tool_use", "id": "toolu_1", "name": "list_services", "input": {}}], "tool_use")
    if n == 2:   # հետո՝ գարաժները ծառայության համար
        return msg([{"type": "tool_use", "id": "toolu_2", "name": "garages_for_service",
                     "input": {"service_id": 2, "open_now": False}}], "tool_use")
    return msg([{"type": "text", "text": "Հավանաբար արգելակային կոլոդկաներն են։ Ամենաէժանը՝ Speed Service, 14,000 ֏։"}], "end_turn")


RealClient = anthropic.Anthropic
anthropic.Anthropic = lambda: RealClient(api_key="fake", max_retries=0,
                                         http_client=httpx.Client(transport=httpx.MockTransport(handler)))

# 1. Նորմալ հոսք՝ երկու գործիք, հետո վերջնական պատասխան
text, mode, cards = chat.reply([{"role": "user", "content": "արգելակելիս ճռռոց է լսվում"}])
assert mode == "ai" and "14,000" in text, (mode, text)
assert [(x["name"], x["price_amd"]) for x in cards][:1] == [("Speed Service", 14000)] and len(cards) == 3   # քարտերը գալիս են գործիքի արդյունքից
assert len(calls) == 3
sys_text = "".join(b["text"] for b in calls[0]["system"])
assert "Կանոններ" in sys_text and "Հիմա Երևանում" in sys_text                      # system prompt-ը՝ ժամանակով
assert "Արգելակային կոլոդկաների" in sys_text and "պագրիշկա" in sys_text           # կատալոգը և խոսակցական բառերը prompt-ում են
assert calls[0]["system"][0].get("cache_control") == {"type": "ephemeral"}        # կայուն մասը քեշավորվում է
assert calls[0]["output_config"] == {"effort": "low"} and calls[0]["max_tokens"] >= 4096
assert all(t.get("strict") for t in calls[0]["tools"])
assert {t["name"] for t in calls[0]["tools"]} == {"list_services", "garages_for_service", "garage_info"}
assert calls[0]["messages"] == [{"role": "user", "content": "արգելակելիս ճռռոց է լսվում"}]
# 2-րդ հարցման մեջ պետք է լինեն AI-ի tool_use և մեր tool_result-ը՝ իրական տվյալներով
m2 = calls[1]["messages"]
assert m2[1]["role"] == "assistant" and any(b["type"] == "tool_use" for b in m2[1]["content"])
res = m2[2]["content"][0]
assert res["type"] == "tool_result" and res["tool_use_id"] == "toolu_1"
assert "Արգելակային կոլոդկաների" in res["content"]
res2 = calls[2]["messages"][4]["content"][0]
assert res2["tool_use_id"] == "toolu_2" and json.loads(res2["content"])[0]["price_amd"] == 14000
print("AI հոսքը (tool use) աշխատում է ✓")

# 3. Անվավեր գործիքի արգումենտներ՝ սխալը վերադառնում է AI-ին, ոչ թե փլուզում
assert "error" in json.loads(chat.run_tool("garages_for_service", {}))
assert "error" in json.loads(chat.run_tool("no_such_tool", {}))
print("Գործիքների սխալները մշակվում են ✓")

# 4. AI-ն անհասանելի է (օր.՝ սխալ բանալի, 401) -> անցնում է պարզ ռեժիմի
def bad(request): return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
anthropic.Anthropic = lambda: RealClient(api_key="bad", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(bad)))
text, mode, cards = chat.reply([{"role": "user", "content": "արգելակ ճռռոց"}])
assert mode == "simple" and "անհասանելի" in text and cards[0]["price_amd"] == 14000, (mode, text)
print("AI-ի անկման դեպքում fallback-ը աշխատում է ✓")

# 5. Անվերջ գործիքային հանգույցից պաշտպանություն
calls.clear()
def loop(request): return msg([{"type": "tool_use", "id": "t", "name": "list_services", "input": {}}], "tool_use")
anthropic.Anthropic = lambda: RealClient(api_key="x", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(loop)))
assert "Չհաջողվեց" in chat.ai_reply([{"role": "user", "content": "x"}])[0]
print("Անվերջ հանգույցից պաշտպանությունը աշխատում է ✓")

# 5b. Դատարկ պատասխան (օր.՝ max_tokens թողեց միայն thinking, կամ refusal) -> պարզ ռեժիմի տեքստ, ոչ դատարկ տող
def empty(request): return msg([{"type": "thinking", "thinking": "", "signature": "x"}], "max_tokens")
anthropic.Anthropic = lambda: RealClient(api_key="x", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(empty)))
text, cards = chat.ai_reply([{"role": "user", "content": "արգելակ ճռռոց"}])
assert text and "կոլոդկա" in text.lower() and cards[0]["price_amd"] == 14000, (text, cards)
print("Դատարկ AI պատասխանի դեպքում fallback-ը աշխատում է ✓")

# 6. Օրական սահման. սահմանը անցնելիս AI-ը չի կանչվում (ծախս չկա), chat-ը շարունակում է աշխատել
calls.clear()
anthropic.Anthropic = lambda: RealClient(api_key="x", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
chat.AI_DAILY_LIMIT = 2
chat._ai_usage.update(day=None, n=0)
modes = []
for _ in range(4):
    calls.clear()
    modes.append((chat.reply([{"role": "user", "content": "արգելակ ճռռոց"}])[1], len(calls)))
assert [m for m, _ in modes] == ["ai", "ai", "simple", "simple"], modes
assert modes[2][1] == 0 and modes[3][1] == 0                      # սահմանից հետո API կանչ չկա
print("AI-ի օրական սահմանը աշխատում է ✓")

# 7. Գարաժների որոնումը՝ նույն AI-ով. տեքստը վերածվում է ծառայությունների, կրկնվող հարցումը՝ հիշողությունից (կանչ չկա)
calls.clear(); chat.AI_DAILY_LIMIT = 200; chat._ai_usage.update(day=None, n=0); chat._resolve_cache.clear()
def search_handler(request: httpx.Request):
    body = json.loads(request.content); calls.append(body)
    assert "tools" not in body and "Կախոցի ստուգում" in body["system"]                      # կատալոգը prompt-ում է, գործիքներ չկան
    return msg([{"type": "text", "text": "Հավանաբար կախոցն է։ [5, 99]"}], "end_turn")
anthropic.Anthropic = lambda: RealClient(api_key="x", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(search_handler)))
assert chat.resolve_services("մեքենան փոսերի վրա թխկթխկում է") == ([5], "ai") and len(calls) == 1   # 99-ը կատալոգում չկա, դեն է նետվում
assert chat.resolve_services("  Մեքենան փոսերի վրա թխկթխկում Է ") == ([5], "ai") and len(calls) == 1   # նույն հարցումը՝ առանց նոր կանչի
assert chat.resolve_services("") == ([], "none")
calls.clear(); chat._resolve_cache.clear()
def empty_handler(request: httpx.Request):
    calls.append(json.loads(request.content)); return msg([{"type": "text", "text": "[]"}], "end_turn")
anthropic.Anthropic = lambda: RealClient(api_key="x", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(empty_handler)))
assert chat.resolve_services("պագրիշկա փոխել") == ([3], "ai") and len(calls) == 1              # AI-ը բաց թողեց, բանալի բառը լրացրեց
anthropic.Anthropic = lambda: RealClient(api_key="bad", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(bad)))
assert chat.resolve_services("թակոց") == ([5], "simple")                                           # AI-ի սխալի դեպքում՝ բանալի բառերով
print("AI որոնումը (գարաժների էջ) աշխատում է ✓")
