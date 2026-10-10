"""Turn a solution into what a manager needs: hours and pay per person, and
for every gap, who could have covered it and the exact rule that stopped them."""
from __future__ import annotations

from dataclasses import dataclass

from .model import Problem, Shift, Staff
from .solver import Solution, conflicts, eligible, week_blocks


@dataclass
class StaffSummary:
    id: str
    name: str
    shifts: int
    hours: float
    overtime_hours: float
    pay: float
    target_hours: float | None
    days_worked: int


@dataclass
class Gap:
    shift: str
    label: str
    short: int
    reasons: dict[str, str]        # staff name -> why they couldn't take it


def _pay(p: Problem, s: Staff, mine: list[Shift]) -> tuple[float, float]:
    r = p.rules
    base = sum(s.hourly_rate * sh.paid_minutes / 60
               * (r.public_holiday_multiplier if sh.day in p.public_holidays else 1.0) for sh in mine)
    ot_minutes = 0.0
    for d0, d1 in week_blocks(p):
        frac = (d1 - d0) / 7
        week = sum(sh.paid_minutes for sh in mine if d0 <= p.day_index(sh.day) < d1)
        ot_minutes += max(0.0, week - r.normal_hours_per_week * 60 * frac)
    premium = s.hourly_rate * (r.overtime_multiplier - 1) * ot_minutes / 60
    return round(base + premium, 2), ot_minutes / 60


def summarise(p: Problem, sol: Solution) -> list[StaffSummary]:
    shifts = {sh.id: sh for sh in p.shifts}
    out = []
    for s in p.staff:
        mine = [shifts[k] for sid, k in sol.assignments if sid == s.id]
        pay, ot = _pay(p, s, mine)
        out.append(StaffSummary(
            id=s.id, name=s.name, shifts=len(mine),
            hours=round(sum(sh.paid_minutes for sh in mine) / 60, 2), overtime_hours=round(ot, 2),
            pay=pay, target_hours=s.target_hours, days_worked=len({sh.day for sh in mine})))
    return out


def why_not(p: Problem, sol: Solution, s: Staff, k: Shift) -> str:
    """The first rule that stops `s` taking shift `k`, given everything else
    they are already rostered on."""
    reason = eligible(s, k, p)
    if reason:
        return reason
    shifts = {sh.id: sh for sh in p.shifts}
    mine = [shifts[kid] for sid, kid in sol.assignments if sid == s.id]
    if k in mine:
        return "already on it"
    r = p.rules
    rest = int(r.min_rest_between_shifts_hours * 60)
    for other in mine:
        if conflicts(k, other, rest):
            overlap = not (other.end <= k.start or k.end <= other.start)
            return (f"already on {other.label}" if overlap
                    else f"needs {r.min_rest_between_shifts_hours:g}h rest around {other.label}")
    today = sum(sh.paid_minutes for sh in mine if sh.day == k.day)
    if today + k.paid_minutes > r.max_hours_per_day * 60:
        return f"would work over {r.max_hours_per_day:g}h that day"
    for d0, d1 in week_blocks(p):
        if d0 <= p.day_index(k.day) < d1 and s.max_hours is not None:
            week = sum(sh.paid_minutes for sh in mine if d0 <= p.day_index(sh.day) < d1)
            if week + k.paid_minutes > s.max_hours * 60 * (d1 - d0) / 7:
                return f"would pass their {s.max_hours:g}h contract cap"
    days = sorted({p.day_index(sh.day) for sh in mine} | {p.day_index(k.day)})
    run = best = 1
    for a, b in zip(days, days[1:]):
        run = run + 1 if b == a + 1 else 1
        best = max(best, run)
    if best > r.max_consecutive_days:
        return f"would work {best} days in a row (max {r.max_consecutive_days})"
    with_k = mine + [k]
    _, ot = _pay(p, s, with_k)
    if ot * 60 > r.overtime_cap_minutes(p.days):
        return "would exceed the overtime cap"
    return "no rule blocks it (raise the time limit and re-solve)"


def gaps(p: Problem, sol: Solution) -> list[Gap]:
    shifts = {sh.id: sh for sh in p.shifts}
    out = []
    for kid, short in sorted(sol.uncovered.items(), key=lambda kv: shifts[kv[0]].start):
        k = shifts[kid]
        trained = [s for s in p.staff if k.role in s.roles]
        reasons = {s.name: why_not(p, sol, s, k) for s in trained}
        reasons = {n: why for n, why in reasons.items() if why != "already on it"}
        out.append(Gap(kid, k.label, short, reasons or {"(nobody)": f"no staff are trained as {k.role}"}))
    return out


def totals(p: Problem, sol: Solution) -> dict:
    summ = summarise(p, sol)
    need = sum(sh.need * sh.paid_minutes for sh in p.shifts if not p.is_past(sh))
    short = sum(n * next(sh.paid_minutes for sh in p.shifts if sh.id == k) for k, n in sol.uncovered.items())
    changes = None
    if p.previous:
        now = set(sol.assignments)
        changes = len(now ^ set(p.previous))
    return {
        "status": sol.status,
        "labour_cost": round(sum(s.pay for s in summ), 2),
        "hours": round(sum(s.hours for s in summ), 2),
        "overtime_hours": round(sum(s.overtime_hours for s in summ), 2),
        "coverage": round(1 - short / need, 4) if need else 1.0,
        "uncovered_shifts": len(sol.uncovered),
        "changes_from_previous": changes,
        "solve_seconds": round(sol.wall_seconds, 2),
    }
