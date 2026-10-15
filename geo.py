"""Հասցեից կետ գտնելը (Nominatim / OpenStreetMap)՝ ըստ նրանց օգտագործման քաղաքականության։

https://operations.osmfoundation.org/policies/nominatim/
 - սահմանը ամբողջ հավելվածի համար է (բոլոր օգտատերերը միասին)՝ առավելագույնը 1 հարցում/վայրկյան,
 - պարտադիր է նույնականացնող User-Agent (մեր կոնտակտով),
 - ավտոլրացում («որոնում՝ տառ առ տառ») չկա. միայն կոճակով,
 - արդյունքները քեշավորվում են, զանգվածային որոնում չկա։
Շատ գարաժներ/հաճախակի որոնումների դեպքում անցեք վճարովի/սեփական geocoder-ի (օր.՝ Google, Mapbox, սեփական Nominatim)։
"""
import os
import threading
import time

import httpx

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
CONTACT = os.getenv("NOMINATIM_CONTACT", "")  # ձեր էլ. փոստը՝ OSM-ի կանոնների համաձայն
USER_AGENT = f"AIAutoService/1.0 ({CONTACT or 'no-contact-set'})"
# Հայաստանի մոտավոր սահմանները՝ պատահական սխալ կետերից (0,0 և այլն) պաշտպանվելու համար
LAT_MIN, LAT_MAX, LNG_MIN, LNG_MAX = 38.5, 41.6, 43.0, 47.0

_lock = threading.Lock()
_last_call = 0.0
_cache: dict[str, dict | None] = {}


def in_armenia(lat: float, lng: float) -> bool:
    return LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX


def _fetch(query: str) -> list:
    r = httpx.get(NOMINATIM_URL, timeout=8,
                  params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "am", "accept-language": "hy,en"},
                  headers={"User-Agent": USER_AGENT, "Referer": os.getenv("PUBLIC_URL", "https://autoservice.example")})
    r.raise_for_status()
    return r.json()


def geocode(query: str) -> dict | None:
    """Վերադարձնում է {lat, lng, label} կամ None (չգտնվեց)։ Բարձրացնում է RuntimeError՝ եթե ծառայությունը անհասանելի է։"""
    key = " ".join(query.lower().split())
    with _lock:   # lock-ը միաժամանակ ապահովում է «1 հարցում/վայրկյան» ամբողջ հավելվածի համար
        if key in _cache:
            return _cache[key]
        global _last_call
        wait = 1.05 - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            data = _fetch(query)
        except Exception as e:
            raise RuntimeError("Որոնման ծառայությունը հասանելի չէ") from e
        finally:
            _last_call = time.time()
        res = None
        if data:
            lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
            if in_armenia(lat, lng):
                res = {"lat": lat, "lng": lng, "label": data[0].get("display_name", "")}
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = res
        return res
