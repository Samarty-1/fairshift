"""Someone called in sick: re-plan the rest of the period with as few changes
as possible.

Shifts that already started stay as they were (they happened). The absent
person is marked unavailable from the given date. Every other existing
assignment is kept unless moving it is the only way to cover a gap, because
each change from the published roster carries a penalty in the solver.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from .model import Problem
from .solver import Solution, solve


def absent(p: Problem, roster: list[tuple[str, str]], staff_id: str, start: date,
           end: date | None = None) -> Problem:
    """The problem to re-solve: `staff_id` is away from `start` to `end`
    (inclusive, default the end of the period); shifts before `start` are
    pinned as worked; the published roster becomes `previous`."""
    people = p.staff_by_id()
    if staff_id not in people:
        raise ValueError(f"unknown staff id {staff_id!r}")
    last = end or date.fromordinal(p.start.toordinal() + p.days - 1)
    away = {date.fromordinal(o) for o in range(start.toordinal(), last.toordinal() + 1)}
    staff = tuple(replace(s, unavailable_dates=s.unavailable_dates | frozenset(away)) if s.id == staff_id else s
                  for s in p.staff)
    shifts = {sh.id: sh for sh in p.shifts}
    worked = frozenset((sid, kid) for sid, kid in roster if shifts[kid].day < start)
    still_planned = frozenset((sid, kid) for sid, kid in roster
                              if not (sid == staff_id and shifts[kid].day in away))
    return replace(p, staff=staff, pinned=p.pinned | worked, previous=still_planned, locked_before=start)


def replan(p: Problem, roster: list[tuple[str, str]], staff_id: str, start: date,
           end: date | None = None, time_limit: float = 20.0) -> tuple[Problem, Solution]:
    q = absent(p, roster, staff_id, start, end)
    return q, solve(q, time_limit=time_limit)


def diff(before: list[tuple[str, str]], after: list[tuple[str, str]], p: Problem) -> list[str]:
    """Human-readable changes, for the message to the team."""
    shifts, people = {sh.id: sh for sh in p.shifts}, p.staff_by_id()
    b, a = set(before), set(after)
    lines = [f"- {people[s].name} off {shifts[k].label}" for s, k in sorted(b - a, key=lambda x: shifts[x[1]].start)]
    lines += [f"+ {people[s].name} on {shifts[k].label}" for s, k in sorted(a - b, key=lambda x: shifts[x[1]].start)]
    return lines
