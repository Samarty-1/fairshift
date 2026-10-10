"""The rostering problem: who is available, what cover is needed, which rules apply.

Everything is plain data loaded from YAML (or JSON through the API) and
validated up front, so the solver only ever sees a consistent problem. Times
are minutes from the start of the planning period; dates are real calendar
dates, so public holidays and multi-week rules line up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class ProblemError(ValueError):
    """The input describes a problem that cannot be set up (not merely an
    unsolvable one: those come back as coverage gaps with reasons)."""


@dataclass(frozen=True)
class Rules:
    """Labour rules. The defaults follow the Singapore Employment Act limits
    for staff covered by Part IV (44 normal hours a week, 12 hours a day,
    72 overtime hours a month, one rest day a week, overtime at 1.5x). They
    are configurable because coverage depends on salary and contract: check
    them against MOM guidance for your staff. This is not legal advice."""
    normal_hours_per_week: float = 44
    max_hours_per_day: float = 12
    max_overtime_hours_per_month: float = 72
    overtime_multiplier: float = 1.5
    max_consecutive_days: int = 6
    min_rest_between_shifts_hours: float = 11
    max_hours_without_break: float = 6
    public_holiday_multiplier: float = 2.0

    def overtime_cap_minutes(self, days: int) -> int:
        """The monthly overtime cap, pro-rated to the planning period."""
        return int(round(self.max_overtime_hours_per_month * 60 * days / 30))


@dataclass(frozen=True)
class Staff:
    id: str
    name: str
    roles: frozenset[str]
    hourly_rate: float
    max_hours: float | None = None          # contract cap per week
    target_hours: float | None = None       # what they hope for per week (fairness)
    availability: dict[str, list[tuple[int, int]]] = field(default_factory=dict)  # weekday -> windows
    unavailable_dates: frozenset[date] = frozenset()
    preferred_days_off: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Shift:
    id: str
    day: date
    start: int          # minutes from period start
    end: int
    role: str
    need: int
    break_minutes: int = 0
    priority: int = 1           # an uncovered head here costs priority x more

    @property
    def paid_minutes(self) -> int:
        return self.end - self.start - self.break_minutes

    @property
    def label(self) -> str:
        def hm(m: int) -> str:
            m %= 24 * 60
            return f"{m // 60:02d}:{m % 60:02d}"
        return f"{self.day:%a %d %b} {hm(self.start)}-{hm(self.end)} {self.role}"


@dataclass(frozen=True)
class Problem:
    name: str
    start: date
    days: int
    rules: Rules
    staff: tuple[Staff, ...]
    shifts: tuple[Shift, ...]
    public_holidays: frozenset[date] = frozenset()
    # manager decisions the solver must keep: (staff id, shift id)
    pinned: frozenset[tuple[str, str]] = frozenset()
    # a previous roster to stay close to when re-planning: (staff id, shift id)
    previous: frozenset[tuple[str, str]] = frozenset()
    # re-planning from this date: earlier days already happened, so their
    # assignments are exactly the pinned ones and their gaps are history
    locked_before: date | None = None

    def is_past(self, shift: "Shift") -> bool:
        return self.locked_before is not None and shift.day < self.locked_before

    def day_index(self, d: date) -> int:
        return (d - self.start).days

    def staff_by_id(self) -> dict[str, Staff]:
        return {s.id: s for s in self.staff}


# --- parsing ---------------------------------------------------------------------

def _minutes(text: str) -> int:
    try:
        t = time.fromisoformat(text.strip())
    except ValueError as e:
        raise ProblemError(f"bad time {text!r}: use HH:MM") from e
    return t.hour * 60 + t.minute


def _window(text: str) -> tuple[int, int]:
    """'07:00-15:00' -> minutes after midnight; an end before the start runs
    past midnight ('18:00-02:00')."""
    try:
        a, b = text.split("-")
    except ValueError as e:
        raise ProblemError(f"bad window {text!r}: use HH:MM-HH:MM") from e
    s, e = _minutes(a), _minutes(b)
    return (s, e + 24 * 60 if e <= s else e)


def _date(v: Any) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError as e:
        raise ProblemError(f"bad date {v!r}: use YYYY-MM-DD") from e


def parse(doc: dict[str, Any]) -> Problem:
    """Build and validate a Problem from a YAML/JSON document."""
    if "start" not in doc:
        raise ProblemError("missing 'start' (the first date of the roster)")
    start = _date(doc["start"])
    days = int(doc.get("days", 7))
    if not 1 <= days <= 31:
        raise ProblemError("'days' must be between 1 and 31")
    rules = Rules(**doc.get("rules", {}))

    staff = []
    seen: set[str] = set()
    for i, s in enumerate(doc.get("staff", [])):
        sid = str(s.get("id") or s.get("name") or f"staff{i}")
        if sid in seen:
            raise ProblemError(f"duplicate staff id {sid!r}")
        seen.add(sid)
        avail: dict[str, list[tuple[int, int]]] = {}
        for day, windows in (s.get("availability") or {}).items():
            day = day.lower()[:3]
            if day not in DAYS:
                raise ProblemError(f"{sid}: unknown weekday {day!r}")
            windows = [windows] if isinstance(windows, str) else windows
            avail[day] = [_window(w) for w in windows]
        staff.append(Staff(
            id=sid, name=str(s.get("name", sid)), roles=frozenset(map(str, s.get("roles", []))),
            hourly_rate=float(s.get("hourly_rate", 0)),
            max_hours=s.get("max_hours"), target_hours=s.get("target_hours"),
            availability=avail,
            unavailable_dates=frozenset(_date(d) for d in s.get("unavailable_dates", [])),
            preferred_days_off=frozenset(d.lower()[:3] for d in s.get("preferred_days_off", [])),
        ))
    if not staff:
        raise ProblemError("no staff")

    shifts = []
    for i, d in enumerate(doc.get("demand", [])):
        # a demand line applies to explicit dates, or to weekdays in the period
        if "date" in d:
            dates = [_date(d["date"])]
        else:
            wanted = [w.lower()[:3] for w in ([d["day"]] if isinstance(d.get("day"), str)
                                              else d.get("days", DAYS))]
            dates = [start + timedelta(k) for k in range(days)
                     if DAYS[(start + timedelta(k)).weekday()] in wanted]
        s0, e0 = _window(d["time"])
        for day in dates:
            k = (day - start).days
            if not 0 <= k < days:
                continue
            base = k * 24 * 60
            shift = Shift(id=f"{day.isoformat()}-{d['role']}-{d['time']}", day=day,
                          start=base + s0, end=base + e0, role=str(d["role"]),
                          need=int(d.get("need", 1)), break_minutes=int(d.get("break_minutes", 0)),
                          priority=int(d.get("priority", 1)))
            if shift.paid_minutes <= 0:
                raise ProblemError(f"{shift.label}: break is as long as the shift")
            if (shift.end - shift.start) > rules.max_hours_without_break * 60 and not shift.break_minutes:
                raise ProblemError(f"{shift.label}: longer than {rules.max_hours_without_break:g}h "
                                   "with no break; add break_minutes")
            shifts.append(shift)
    if not shifts:
        raise ProblemError("no demand: add shifts under 'demand'")
    ids = [s.id for s in shifts]
    if len(set(ids)) != len(ids):
        raise ProblemError("two demand lines describe the same shift; merge them and raise 'need'")

    shift_ids, staff_ids = set(ids), {s.id for s in staff}

    def pairs(key: str) -> frozenset[tuple[str, str]]:
        out = set()
        for p in doc.get(key, []):
            if p["staff"] not in staff_ids or p["shift"] not in shift_ids:
                raise ProblemError(f"{key}: unknown staff or shift in {p}")
            out.add((p["staff"], p["shift"]))
        return frozenset(out)

    return Problem(
        name=str(doc.get("name", "Roster")), start=start, days=days, rules=rules,
        staff=tuple(staff), shifts=tuple(shifts),
        public_holidays=frozenset(_date(d) for d in doc.get("public_holidays", [])),
        pinned=pairs("pinned"), previous=pairs("previous"),
    )


def weekday(d: date) -> str:
    return DAYS[d.weekday()]


def as_datetime(p: Problem, minute: int) -> datetime:
    return datetime.combine(p.start, time()) + timedelta(minutes=minute)
