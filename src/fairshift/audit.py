"""Check any roster against the rules: one the solver produced, or one a
manager wrote by hand in a spreadsheet.

Deliberately written separately from the solver's constraints, so the tests
check the solver against an independent reading of the same rules.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .model import Problem, weekday


@dataclass(frozen=True)
class Violation:
    staff: str
    rule: str
    detail: str


def audit(p: Problem, assignments: list[tuple[str, str]]) -> list[Violation]:
    r = p.rules
    people = p.staff_by_id()
    shifts = {sh.id: sh for sh in p.shifts}
    out: list[Violation] = []
    mine: dict[str, list] = defaultdict(list)
    for sid, kid in assignments:
        if sid not in people or kid not in shifts:
            out.append(Violation(sid, "unknown", f"unknown staff or shift {kid}"))
            continue
        mine[sid].append(shifts[kid])

    head = defaultdict(int)
    for sid, kid in assignments:
        head[kid] += 1
    for kid, n in head.items():
        if kid in shifts and n > shifts[kid].need:
            out.append(Violation("-", "overstaffed", f"{shifts[kid].label}: {n} for {shifts[kid].need}"))

    for sid, ss in mine.items():
        s = people[sid]
        ss = sorted(ss, key=lambda k: k.start)
        name = s.name
        for k in ss:
            if k.role not in s.roles:
                out.append(Violation(name, "role", f"{k.label}: not trained as {k.role}"))
            if k.day in s.unavailable_dates:
                out.append(Violation(name, "leave", f"{k.label}: on leave"))
            if s.availability:
                base = p.day_index(k.day) * 1440
                ok = any(a <= k.start - base and k.end - base <= b for a, b in s.availability.get(weekday(k.day), []))
                if not ok:
                    out.append(Violation(name, "availability", f"{k.label}: outside their availability"))
        for a, b in zip(ss, ss[1:]):
            if b.start < a.end:
                out.append(Violation(name, "overlap", f"{a.label} and {b.label}"))
            elif a.day != b.day and b.start - a.end < r.min_rest_between_shifts_hours * 60:
                out.append(Violation(name, "rest", f"{(b.start - a.end) / 60:g}h between {a.label} and {b.label}"))
        per_day = defaultdict(int)
        for k in ss:
            per_day[k.day] += k.paid_minutes
        for d, mins in per_day.items():
            if mins > r.max_hours_per_day * 60:
                out.append(Violation(name, "daily hours", f"{d}: {mins / 60:g}h"))
        days = sorted(p.day_index(d) for d in per_day)
        run = 0
        for i, d in enumerate(days):
            run = run + 1 if i and d == days[i - 1] + 1 else 1
            if run > r.max_consecutive_days:
                out.append(Violation(name, "rest day", f"{run} days in a row up to day {d + 1}"))
                break
        overtime = 0.0
        for w0 in range(0, p.days, 7):
            w1 = min(w0 + 7, p.days)
            frac = (w1 - w0) / 7
            mins = sum(m for d, m in per_day.items() if w0 <= p.day_index(d) < w1)
            if s.max_hours is not None and mins > s.max_hours * 60 * frac + 1e-9:
                out.append(Violation(name, "contract hours", f"{mins / 60:g}h > {s.max_hours * frac:g}h"))
            overtime += max(0.0, mins - r.normal_hours_per_week * 60 * frac)
        if overtime > r.overtime_cap_minutes(p.days):
            out.append(Violation(name, "overtime cap", f"{overtime / 60:g}h"))
    return out
