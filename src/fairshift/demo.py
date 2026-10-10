"""A fictional café for the demo and the tests. Nothing here is real data."""
from __future__ import annotations

from typing import Any


def cafe() -> dict[str, Any]:
    """Kopi & Co: open 07:00-22:00, busier at weekends, 12 staff with mixed
    roles, contracts and availability. One weekday is marked as a public
    holiday to show the pay premium; it is a demo date, not a real one."""
    staff = [
        # full-timers: target close to 44h
        {"id": "aisha", "name": "Aisha", "roles": ["supervisor", "barista"], "hourly_rate": 16.0, "target_hours": 44},
        {"id": "ben", "name": "Ben", "roles": ["supervisor", "cashier"], "hourly_rate": 15.5, "target_hours": 44,
         "preferred_days_off": ["sun"]},
        {"id": "chen", "name": "Chen Wei", "roles": ["kitchen"], "hourly_rate": 14.0, "target_hours": 44},
        {"id": "divya", "name": "Divya", "roles": ["kitchen", "cashier"], "hourly_rate": 13.5, "target_hours": 40},
        {"id": "farid", "name": "Farid", "roles": ["barista", "cashier"], "hourly_rate": 13.0, "target_hours": 40},
        # part-timers: capped by contract, available at set times
        {"id": "grace", "name": "Grace", "roles": ["barista", "cashier"], "hourly_rate": 11.0, "max_hours": 24,
         "target_hours": 20, "availability": {"mon": "07:00-15:00", "wed": "07:00-15:00", "fri": "07:00-22:00",
                                               "sat": "07:00-22:00"}},
        {"id": "hui", "name": "Hui Min", "roles": ["cashier"], "hourly_rate": 10.5, "max_hours": 20, "target_hours": 16,
         "availability": {"sat": "07:00-22:00", "sun": "07:00-22:00", "thu": "14:00-22:00"}},
        {"id": "ivan", "name": "Ivan", "roles": ["kitchen"], "hourly_rate": 11.5, "max_hours": 30, "target_hours": 24,
         "availability": {d: "11:00-22:00" for d in ["tue", "wed", "thu", "fri", "sat", "sun"]}},
        {"id": "jun", "name": "Jun Hao", "roles": ["barista"], "hourly_rate": 11.0, "max_hours": 24, "target_hours": 16,
         "availability": {"fri": "14:00-22:00", "sat": "07:00-22:00", "sun": "07:00-22:00"}},
        {"id": "kavya", "name": "Kavya", "roles": ["cashier", "barista"], "hourly_rate": 10.5, "max_hours": 16,
         "target_hours": 12, "availability": {"mon": "14:00-22:00", "tue": "14:00-22:00", "sun": "07:00-15:00"}},
        {"id": "liam", "name": "Liam", "roles": ["kitchen", "cashier"], "hourly_rate": 12.0, "max_hours": 32,
         "target_hours": 24, "unavailable_dates": ["2026-10-16"]},
        {"id": "mei", "name": "Mei Ling", "roles": ["barista", "supervisor"], "hourly_rate": 14.5, "max_hours": 30,
         "target_hours": 24, "availability": {d: "07:00-22:00" for d in ["mon", "tue", "thu", "sat", "sun"]}},
    ]
    weekdays, weekend = ["mon", "tue", "wed", "thu", "fri"], ["sat", "sun"]
    demand = [
        {"days": weekdays + weekend, "time": "07:00-15:00", "role": "supervisor", "need": 1, "break_minutes": 45,
         "priority": 3},
        {"days": weekdays + weekend, "time": "14:00-22:00", "role": "supervisor", "need": 1, "break_minutes": 45,
         "priority": 3},
        {"days": weekdays, "time": "07:00-15:00", "role": "barista", "need": 1, "break_minutes": 45},
        {"days": weekend, "time": "07:00-15:00", "role": "barista", "need": 2, "break_minutes": 45},
        {"days": weekdays + weekend, "time": "14:00-22:00", "role": "barista", "need": 1, "break_minutes": 45},
        {"days": weekdays + weekend, "time": "07:00-15:00", "role": "cashier", "need": 1, "break_minutes": 45},
        {"days": weekdays + weekend, "time": "11:00-15:00", "role": "cashier", "need": 1},     # lunch peak
        {"days": weekend, "time": "14:00-22:00", "role": "cashier", "need": 1, "break_minutes": 45},
        {"days": weekdays + weekend, "time": "10:00-18:00", "role": "kitchen", "need": 1, "break_minutes": 45},
        {"days": ["fri", "sat", "sun"], "time": "14:00-22:00", "role": "kitchen", "need": 1, "break_minutes": 45},
    ]
    return {
        "name": "Kopi & Co (demo)",
        "start": "2026-10-12",
        "days": 7,
        "public_holidays": ["2026-10-14"],
        "staff": staff,
        "demand": demand,
    }
