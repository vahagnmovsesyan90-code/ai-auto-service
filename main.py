"""Փուլ 1. Ցուցադրություն. գործարկում՝ python main.py"""
from datetime import datetime

from data import DAY_NAMES
from queries import (all_garages, all_services, find_services, garages_for_service,
                     get_garage, is_open, open_garages)


def show_catalog():
    print("=== Ծառայությունների կատալոգ ===")
    for s in all_services():
        print(f"{s.id}. {s.name} ({s.category})")


def show_garages():
    print("\n=== Գարաժներ ===")
    for g in all_garages():
        days = ", ".join(DAY_NAMES[d] for d in sorted(g.hours))
        print(f"{g.name} — {g.address}, {g.phone} | աշխատում է՝ {days}")


def show_cheapest(service_id: int):
    print("\n=== Ամենաէժանը ըստ ծառայության ===")
    for g, price in garages_for_service(service_id):
        print(f"  {g.name}: {price:,} ֏ ({g.services[service_id].duration_min} ր)")


if __name__ == "__main__":
    show_catalog()
    show_garages()

    found = find_services("արգելակ")
    print("\nՈրոնում «արգելակ»:", [s.name for s in found])
    show_cheapest(found[0].id)

    now = datetime.now()
    print(f"\nԲաց են հիմա ({now:%Y-%m-%d %H:%M}):",
          [g.name for g in open_garages(now)] or "ոչ մեկը")
    saturday_eve = datetime(2026, 10, 3, 19, 0)  # Շաբաթ, 19:00
    print("Շաբաթ 19:00, Garage Kentron բա՞ց է:", is_open(get_garage(2), saturday_eve))
