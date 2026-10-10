from datetime import date

import pytest

from fairshift import audit, demo, explain, export, model, replan
from fairshift.solver import solve


def tiny(**over):
    """Two staff, one role, three days."""
    doc = {
        "name": "Tiny", "start": "2026-10-12", "days": 3,
        "staff": [
            {"id": "a", "name": "Ann", "roles": ["barista"], "hourly_rate": 10},
            {"id": "b", "name": "Bo", "roles": ["barista"], "hourly_rate": 20},
        ],
        "demand": [{"time": "08:00-14:00", "role": "barista", "need": 1}],
    }
    doc.update(over)
    return model.parse(doc)


@pytest.fixture(scope="module")
def cafe():
    p = model.parse(demo.cafe())
    return p, solve(p)


# --- the solver obeys every rule, checked independently -----------------------------

def test_demo_roster_breaks_no_rule(cafe):
    p, sol = cafe
    assert sol.status == "OPTIMAL"
    assert audit.audit(p, sol.assignments) == []


def test_cheapest_qualified_person_gets_the_shift():
    p = tiny()
    sol = solve(p)
    assert {s for s, _ in sol.assignments} == {"a"}                # $10 beats $20


def test_rest_day_rule_forces_a_second_person():
    p = tiny(days=7, staff=[{"id": "a", "name": "Ann", "roles": ["barista"], "hourly_rate": 10},
                            {"id": "b", "name": "Bo", "roles": ["barista"], "hourly_rate": 20}])
    sol = solve(p)
    ann = [k for s, k in sol.assignments if s == "a"]
    assert len(ann) == 6 and not sol.uncovered                     # Bo covers Ann's rest day


def test_rest_between_days():
    p = tiny(days=2, staff=[{"id": "a", "name": "Ann", "roles": ["barista"], "hourly_rate": 10}],
             demand=[{"date": "2026-10-12", "time": "14:00-22:00", "role": "barista", "break_minutes": 45},
                     {"date": "2026-10-13", "time": "06:00-12:00", "role": "barista"}])
    sol = solve(p)
    assert len(sol.assignments) == 1 and len(sol.uncovered) == 1   # 8h gap < 11h rest
    gap = explain.gaps(p, sol)[0]
    assert "rest" in gap.reasons["Ann"]


def test_overtime_is_paid_and_capped():
    staff = [{"id": "a", "name": "Ann", "roles": ["cook"], "hourly_rate": 10}]
    demand = [{"days": ["mon", "tue", "wed", "thu", "fri", "sat"], "time": "08:00-18:00", "role": "cook",
               "break_minutes": 60}]
    p = model.parse({"start": "2026-10-12", "days": 7, "staff": staff, "demand": demand})
    sol = solve(p)
    s = explain.summarise(p, sol)[0]
    assert s.hours == 54 and s.overtime_hours == 10                # 6 x 9h, 44 normal
    assert s.pay == pytest.approx(54 * 10 + 10 * 10 * 0.5)
    tight = model.parse({"start": "2026-10-12", "days": 7, "staff": staff, "demand": demand,
                         "rules": {"max_overtime_hours_per_month": 30}})   # 7-day share: 7h
    sol = solve(tight)
    assert explain.summarise(tight, sol)[0].overtime_hours <= 7
    assert audit.audit(tight, sol.assignments) == []


def test_public_holiday_premium():
    p = tiny(days=1, public_holidays=["2026-10-12"])
    sol = solve(p)
    assert explain.summarise(p, sol)[0].pay == 6 * 10 * 2.0


def test_priority_protects_critical_roles():
    staff = [{"id": "a", "name": "Ann", "roles": ["supervisor", "barista"], "hourly_rate": 10}]
    demand = [{"date": "2026-10-12", "time": "08:00-14:00", "role": "barista", "need": 1},
              {"date": "2026-10-12", "time": "08:00-14:00", "role": "supervisor", "need": 1, "priority": 3}]
    p = model.parse({"start": "2026-10-12", "days": 1, "staff": staff, "demand": demand})
    sol = solve(p)
    assert [k for _, k in sol.assignments][0].endswith("supervisor-08:00-14:00")


def test_fairness_spreads_hours_towards_targets():
    staff = [{"id": "a", "name": "Ann", "roles": ["barista"], "hourly_rate": 10, "target_hours": 18},
             {"id": "b", "name": "Bo", "roles": ["barista"], "hourly_rate": 10, "target_hours": 18}]
    p = tiny(days=6, staff=staff)
    hours = sorted(s.hours for s in explain.summarise(p, solve(p)))
    assert hours == [18, 18]


def test_pins_are_kept():
    p = tiny(pinned=[{"staff": "b", "shift": "2026-10-12-barista-08:00-14:00"}])
    sol = solve(p)
    assert ("b", "2026-10-12-barista-08:00-14:00") in sol.assignments


def test_pinning_someone_ineligible_is_an_error():
    p = tiny(staff=[{"id": "a", "name": "Ann", "roles": ["barista"], "hourly_rate": 10,
                     "unavailable_dates": ["2026-10-12"]}],
             pinned=[{"staff": "a", "shift": "2026-10-12-barista-08:00-14:00"}])
    with pytest.raises(ValueError, match="on leave"):
        solve(p)


# --- re-planning -----------------------------------------------------------------

def test_replan_never_rewrites_the_past(cafe):
    p, sol = cafe
    q, new = replan.replan(p, sol.assignments, "farid", date(2026, 10, 15))
    past = {a for a in sol.assignments if q.day_index(next(s.day for s in p.shifts if s.id == a[1])) < 3}
    past_new = {a for a in new.assignments if q.day_index(next(s.day for s in p.shifts if s.id == a[1])) < 3}
    assert past == past_new
    assert not any(s == "farid" and k >= "2026-10-15" for s, k in new.assignments)
    assert audit.audit(q, new.assignments) == []


def test_replan_changes_only_what_it_must():
    staff = [{"id": "a", "name": "Ann", "roles": ["barista"], "hourly_rate": 10},
             {"id": "b", "name": "Bo", "roles": ["barista"], "hourly_rate": 20},
             {"id": "c", "name": "Cy", "roles": ["barista"], "hourly_rate": 30}]
    p = tiny(days=3, staff=staff)
    sol = solve(p)
    assert {s for s, _ in sol.assignments} == {"a"}
    q, new = replan.replan(p, sol.assignments, "a", date(2026, 10, 13), date(2026, 10, 13))
    changes = set(new.assignments) ^ set(sol.assignments)
    assert changes == {("a", "2026-10-13-barista-08:00-14:00"), ("b", "2026-10-13-barista-08:00-14:00")}


# --- input validation and outputs --------------------------------------------------

@pytest.mark.parametrize("over, msg", [
    ({"days": 0}, "between 1 and 31"),
    ({"demand": [{"time": "08:00-16:00", "role": "barista"}]}, "no break"),
    ({"demand": [{"time": "8am-4pm", "role": "barista"}]}, "HH:MM"),
    ({"staff": []}, "no staff"),
])
def test_bad_input_is_explained(over, msg):
    with pytest.raises(model.ProblemError, match=msg):
        tiny(**over)


def test_overnight_shift_crosses_midnight():
    p = tiny(days=1, demand=[{"time": "22:00-04:00", "role": "barista"}])
    assert p.shifts[0].paid_minutes == 6 * 60


def test_audit_catches_a_hand_written_roster_breaking_rules():
    p = tiny(days=2, staff=[{"id": "a", "name": "Ann", "roles": ["barista"], "hourly_rate": 10, "max_hours": 7}],
             demand=[{"date": "2026-10-12", "time": "14:00-22:00", "role": "barista", "break_minutes": 45},
                     {"date": "2026-10-13", "time": "06:00-12:00", "role": "barista"}])
    rules = {v.rule for v in audit.audit(p, [("a", s.id) for s in p.shifts])}
    assert {"rest", "contract hours"} <= rules


def test_exports(cafe):
    p, sol = cafe
    csv_text = export.to_csv(p, sol.assignments)
    assert csv_text.count("\n") == len(sol.assignments) + 1
    ics = export.to_ics(p, sol.assignments, "aisha")
    assert ics.count("BEGIN:VEVENT") == sum(1 for s, _ in sol.assignments if s == "aisha")
    msg = export.messages(p, sol.assignments)["aisha"]
    assert msg.startswith("Hi Aisha") and "(public holiday)" in msg
    html = export.to_html(p, sol.assignments, explain.summarise(p, sol), explain.gaps(p, sol),
                          explain.totals(p, sol))
    assert "<table>" in html and "Kopi &amp; Co" in html
