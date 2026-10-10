"""Build and solve the roster as a CP-SAT model (Google OR-Tools).

Hard rules (never broken):
  role and availability, approved leave, manager pins, no overlapping
  shifts, rest between working days, hours per day, the overtime cap, and a
  rest day in every run of consecutive days.

Soft goals, in this order of weight:
  1. cover every shift (an uncovered minute costs far more than any wage;
     a shift's priority multiplies that, so a missing supervisor goes last)
  2. labour cost, including overtime and public-holiday premiums
  3. fairness: each person's weekly hours close to their target
  4. preferred days off
  5. when re-planning, change as little of the previous roster as possible

An uncovered shift is therefore a result, not a failure: the solver reports
it, and explain.py says who could have taken it and why they didn't.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta

from ortools.sat.python import cp_model

from .model import Problem, Shift, Staff, weekday

# objective weights, in the solver's unit (cents per hour x minutes, i.e. 60x cents)
UNCOVERED_PER_MINUTE = 1_000_000
FAIRNESS_PER_MINUTE = 300
PREFERRED_DAY_OFF = 60_000          # about $10
CHANGE_FROM_PREVIOUS = 120_000      # about $20 per assignment added or removed


@dataclass
class Solution:
    status: str
    assignments: list[tuple[str, str]]          # (staff id, shift id)
    uncovered: dict[str, int]                   # shift id -> heads short
    objective: float
    wall_seconds: float


def eligible(staff: Staff, shift: Shift, p: Problem) -> str | None:
    """None if this person may work this shift at all, else the reason not."""
    if shift.role not in staff.roles:
        return "not trained for this role"
    if shift.day in staff.unavailable_dates:
        return "on leave"
    if staff.availability:
        windows = staff.availability.get(weekday(shift.day), [])
        base = p.day_index(shift.day) * 24 * 60
        s, e = shift.start - base, shift.end - base
        if not any(a <= s and e <= b for a, b in windows):
            return "not available at that time"
    return None


def conflicts(a: Shift, b: Shift, min_rest_minutes: int) -> bool:
    """Two shifts one person cannot both work: they overlap, or they start
    on different days with less than the minimum rest between them. Split
    shifts on the same day are allowed (the daily hours cap still applies)."""
    first, second = (a, b) if a.start <= b.start else (b, a)
    if second.start < first.end:
        return True
    return first.day != second.day and second.start - first.end < min_rest_minutes


def week_blocks(p: Problem) -> list[tuple[int, int]]:
    """Consecutive 7-day blocks [first day, last day + 1) from the start date."""
    return [(d, min(d + 7, p.days)) for d in range(0, p.days, 7)]


def solve(p: Problem, time_limit: float = 20.0, workers: int = 8) -> Solution:
    m = cp_model.CpModel()
    r = p.rules
    rest = int(r.min_rest_between_shifts_hours * 60)

    x: dict[tuple[str, str], cp_model.IntVar] = {}
    for s in p.staff:
        for sh in p.shifts:
            if eligible(s, sh, p) is None:
                x[s.id, sh.id] = m.new_bool_var(f"x[{s.id},{sh.id}]")
    for sid, kid in p.pinned:
        if (sid, kid) not in x:
            st = p.staff_by_id()[sid]
            sh = next(k for k in p.shifts if k.id == kid)
            raise ValueError(f"pinned {st.name} to {sh.label}, but: {eligible(st, sh, p)}")
        m.add(x[sid, kid] == 1)

    objective = []

    # 1. cover each shift up to its need; shortfall is allowed but very costly
    uncovered = {}
    for sh in p.shifts:
        heads = [x[s.id, sh.id] for s in p.staff if (s.id, sh.id) in x]
        short = m.new_int_var(0, sh.need, f"short[{sh.id}]")
        m.add(sum(heads) + short == sh.need)
        if p.is_past(sh):
            # history: exactly what was worked, nothing added after the fact
            for s in p.staff:
                if (s.id, sh.id) in x and (s.id, sh.id) not in p.pinned:
                    m.add(x[s.id, sh.id] == 0)
            continue
        uncovered[sh.id] = short
        objective.append(short * (UNCOVERED_PER_MINUTE * sh.paid_minutes * sh.priority))

    by_staff = {s.id: [sh for sh in p.shifts if (s.id, sh.id) in x] for s in p.staff}
    ot_total_cap = r.overtime_cap_minutes(p.days)
    for s in p.staff:
        mine = by_staff[s.id]
        rate = round(s.hourly_rate * 100)          # cents per hour

        # no overlaps, and rest between working days
        for i, a in enumerate(mine):
            for b in mine[i + 1:]:
                if conflicts(a, b, rest):
                    m.add(x[s.id, a.id] + x[s.id, b.id] <= 1)

        # hours per calendar day
        for d in range(p.days):
            today = [sh for sh in mine if p.day_index(sh.day) == d]
            if today:
                m.add(sum(x[s.id, sh.id] * sh.paid_minutes for sh in today) <= int(r.max_hours_per_day * 60))

        # a rest day in every run of max_consecutive_days + 1 days
        worked = []
        for d in range(p.days):
            today = [x[s.id, sh.id] for sh in mine if p.day_index(sh.day) == d]
            w = m.new_bool_var(f"worked[{s.id},{d}]")
            if today:
                m.add_max_equality(w, today)
            else:
                m.add(w == 0)
            worked.append(w)
            if weekday(p.start + timedelta(d)) in s.preferred_days_off:
                objective.append(w * PREFERRED_DAY_OFF)
        span = r.max_consecutive_days + 1
        for d in range(0, p.days - span + 1):
            m.add(sum(worked[d:d + span]) <= r.max_consecutive_days)

        # pay: base wage, public-holiday premium
        for sh in mine:
            mult = r.public_holiday_multiplier if sh.day in p.public_holidays else 1.0
            objective.append(x[s.id, sh.id] * round(rate * mult) * sh.paid_minutes)

        # weekly hours: normal hours, overtime beyond them, contract cap, fairness
        ot_vars = []
        for d0, d1 in week_blocks(p):
            frac = (d1 - d0) / 7
            week = [sh for sh in mine if d0 <= p.day_index(sh.day) < d1]
            minutes = sum(x[s.id, sh.id] * sh.paid_minutes for sh in week) if week else 0
            if s.max_hours is not None:
                m.add(minutes <= int(s.max_hours * 60 * frac))
            ot = m.new_int_var(0, 7 * 24 * 60, f"ot[{s.id},{d0}]")
            m.add(ot >= minutes - int(r.normal_hours_per_week * 60 * frac))
            ot_vars.append(ot)
            objective.append(ot * round(rate * (r.overtime_multiplier - 1)))
            if s.target_hours is not None:
                dev = m.new_int_var(0, 7 * 24 * 60, f"dev[{s.id},{d0}]")
                target = int(s.target_hours * 60 * frac)
                m.add(dev >= minutes - target)
                m.add(dev >= target - minutes)
                objective.append(dev * FAIRNESS_PER_MINUTE)
        m.add(sum(ot_vars) <= ot_total_cap)

    # stay close to the previous roster when re-planning
    if p.previous:
        for key, var in x.items():
            objective.append((1 - var if key in p.previous else var) * CHANGE_FROM_PREVIOUS)

    m.minimize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 1
    t0 = time.perf_counter()
    status = solver.solve(m)
    wall = time.perf_counter() - t0
    name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # only reachable if pins or hard rules contradict each other
        return Solution(name, [], {sh.id: sh.need for sh in p.shifts}, float("nan"), wall)
    return Solution(
        status=name,
        assignments=sorted(k for k, v in x.items() if solver.value(v)),
        uncovered={k: solver.value(v) for k, v in uncovered.items() if solver.value(v)},
        objective=solver.objective_value / 60 / 100,
        wall_seconds=wall,
    )
