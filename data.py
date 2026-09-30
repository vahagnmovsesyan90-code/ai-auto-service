"""Փուլ 1. Ավտոսերվիսի տվյալները (մոդելներ + նմուշային տվյալներ)."""
from dataclasses import dataclass, field
from datetime import time

# Շաբաթվա օրեր՝ 0 = Երկուշաբթի ... 6 = Կիրակի (ինչպես Python-ի weekday())
DAY_NAMES = ["Երկ", "Երք", "Չրք", "Հնգ", "Ուրբ", "Շբթ", "Կիր"]


@dataclass(frozen=True)
class Service:
    """Ծառայություն ընդհանուր կատալոգից (նույնն է բոլոր գարաժների համար)."""
    id: int
    name: str
    category: str
    keywords: tuple[str, ...] = ()  # բառեր, որոնցով վարորդը նկարագրում է խնդիրը


@dataclass
class GarageService:
    """Կոնկրետ գարաժի գինը և տևողությունը կատալոգի ծառայության համար."""
    service_id: int
    price: int          # դրամ
    duration_min: int   # րոպե


@dataclass
class Garage:
    id: int
    name: str
    address: str
    phone: str
    # օր -> (բացում, փակում); եթե օրը բացակայում է, գարաժը փակ է
    hours: dict[int, tuple[time, time]] = field(default_factory=dict)
    # service_id -> GarageService
    services: dict[int, GarageService] = field(default_factory=dict)


def _week(open_t: time, close_t: time, days=range(7)):
    return {d: (open_t, close_t) for d in days}


SERVICES = [
    Service(1, "Յուղի և ֆիլտրի փոխարինում", "Սպասարկում",
            ("յուղ", "ֆիլտր", "սպասարկում")),
    Service(2, "Արգելակային կոլոդկաների փոխարինում", "Արգելակներ",
            ("արգելակ", "կոլոդկա", "ճռռոց", "ձայն")),
    Service(3, "Անվադողերի փոխարինում և հավասարակշռում", "Անվադողեր",
            ("անվադող", "դող", "անիվ", "թրթռ")),
    Service(4, "Համակարգչային ախտորոշում", "Էլեկտրոնիկա",
            ("check engine", "լամպ", "ախտորոշ", "սկաներ", "վառվ")),
    Service(5, "Կախոցի ստուգում", "Կախոց",
            ("կախոց", "թակոց", "ամորտիզատոր")),
    Service(6, "Օդորակիչի լիցքավորում", "Կլիմա",
            ("օդորակիչ", "ֆրեոն", "չի սառեցնում")),
]

GARAGES = [
    Garage(
        1, "AutoPro Երևան", "Արշակունյաց 12", "+374 10 000001",
        hours=_week(time(9), time(18), range(0, 6)),  # Երկ–Շբթ
        services={
            1: GarageService(1, 8000, 45),
            2: GarageService(2, 15000, 90),
            3: GarageService(3, 6000, 40),
            4: GarageService(4, 5000, 30),
        },
    ),
    Garage(
        2, "Garage Kentron", "Տերյան 40", "+374 10 000002",
        hours=_week(time(10), time(19), range(0, 5)),  # Երկ–Ուրբ
        services={
            1: GarageService(1, 7000, 45),
            2: GarageService(2, 18000, 100),
            4: GarageService(4, 4000, 30),
            5: GarageService(5, 12000, 60),
            6: GarageService(6, 10000, 60),
        },
    ),
    Garage(
        3, "Speed Service", "Բաղրամյան 88", "+374 10 000003",
        hours=_week(time(8), time(20)),  # ամեն օր
        services={
            1: GarageService(1, 9000, 40),
            2: GarageService(2, 14000, 80),
            3: GarageService(3, 5000, 35),
            5: GarageService(5, 11000, 60),
        },
    ),
]
