# fairshift

**Rosters for shops and cafés that are legal, fair and costed, built in
under a second. When someone calls in sick, a new plan that changes as
little as possible.**

Most small F&B and retail managers build next week's rota by hand in a
spreadsheet or a group chat. That's a couple of hours a week. The mistakes
cost money (unplanned overtime, public-holiday pay) or break the rules (no
rest day, 12+ hour days). fairshift builds the rota with an optimizer and
explains every gap it can't fill.

```
Staff + availability + cover needed  →  Solve  →  Rota, costs, gaps with reasons  →  Sick call?  →  Re-plan
```

| Module | What it does |
|---|---|
| **Solve** | Builds the rota with Google OR-Tools CP-SAT. Hard rules: roles, availability, leave, no overlaps, rest between days, max hours a day, a rest day each week, overtime cap. Then it covers every shift, minimises wage cost (overtime and public-holiday premiums included), keeps hours fair against each person's target, and respects preferred days off |
| **Priorities** | Mark critical cover (a supervisor on every shift) so that, when the shop can't cover everything, the less critical shift goes short instead |
| **Explain** | Every uncovered shift lists each trained person and the exact rule that stopped them: *"Farid: would work 7 days in a row"*, *"Aisha: needs 11h rest around Wed 14:00–22:00"* |
| **Re-plan** | A sick call re-plans the rest of the week. Shifts already worked are locked, and every change from the published rota carries a penalty, so people's plans move only when they must. Returns the change list to send the team |
| **Check** | Audits any rota, including a hand-made spreadsheet, against the same rules. The checker is written separately from the solver, so it doubles as the test oracle |
| **Share** | CSV for payroll, an `.ics` calendar per person, a ready-to-paste message per person, a printable HTML rota |
| **Web app** | Edit the shop, build, re-plan around a sick call, download, copy messages. FastAPI + one HTML page, in Docker |

## Try it in 30 seconds

```bash
pip install -e ".[api]"
fairshift demo
```

The demo is a fictional café: 12 staff (full-time and part-time, mixed
roles, set availability, one on leave) covering 56 shifts over a week, with
a public holiday:

```
Kopi & Co (demo): OPTIMAL, coverage 97.1%, labour $5,452.86, 372h (0h overtime), solved in 0.05s
  Aisha         43.5h (target 44)   $  812.00
  ...
GAP Wed 14 Oct 14:00-22:00 barista short 1
    Aisha: already on Wed 14 Oct 14:00-22:00 supervisor
    Farid: needs 11h rest around Thu 15 Oct 07:00-15:00 barista
    Grace: not available at that time
    ...
```

Then Farid calls in sick from Thursday:

```bash
fairshift replan examples/cafe.yaml --roster demo-rota/roster.json --absent farid --from 2026-10-15
```

Nothing before Thursday changes, Farid comes off his shifts, and the
remaining gaps come with reasons, so the manager knows who to call first.

```bash
fairshift solve my-shop.yaml --out rota/              # your shop
fairshift check my-shop.yaml --roster my-rota.csv     # audit a rota you made by hand
fairshift serve                                       # web app on http://127.0.0.1:8000
docker compose up                                     # same, in a container
```

## Describing a shop

```yaml
name: Kopi & Co
start: 2026-10-12          # first day of the rota
days: 7
public_holidays: [2026-10-14]
rules:                     # optional; defaults below
  normal_hours_per_week: 44
  max_hours_per_day: 12
  max_overtime_hours_per_month: 72      # pro-rated to the rota's length
  overtime_multiplier: 1.5
  max_consecutive_days: 6               # i.e. a rest day in every 7
  min_rest_between_shifts_hours: 11     # between working days; same-day split shifts are allowed
  max_hours_without_break: 6            # longer shifts must declare break_minutes
  public_holiday_multiplier: 2.0
staff:
  - id: grace
    name: Grace
    roles: [barista, cashier]
    hourly_rate: 11.0
    max_hours: 24                       # contract cap per week
    target_hours: 20                    # what fairness aims for
    availability: {mon: "07:00-15:00", fri: "07:00-22:00"}   # omit = any time
    unavailable_dates: [2026-10-16]
    preferred_days_off: [sun]
demand:
  - {days: [sat, sun], time: "07:00-15:00", role: barista, need: 2, break_minutes: 45}
  - {days: [mon, tue, wed, thu, fri, sat, sun], time: "14:00-22:00", role: supervisor, need: 1,
     break_minutes: 45, priority: 3}
  - {date: 2026-10-16, time: "18:00-02:00", role: kitchen, need: 1, break_minutes: 30}   # past midnight
pinned:                    # manager decisions the solver must keep
  - {staff: grace, shift: 2026-10-12-barista-07:00-15:00}
```

**Labour rules.** The defaults follow the Singapore Employment Act limits for
staff covered by Part IV:
- 44 normal hours a week
- 12 hours a day
- 72 overtime hours a month
- a rest day each week
- overtime at 1.5×

Who is covered depends on salary and contract, so every rule is
configurable. Check them against MOM guidance for your staff; this is not
legal advice. The 11-hour rest between working days is a common good
practice rather than a statutory figure, and is configurable too.

## How it works

`solver.py` turns the shop into a CP-SAT model:
- **Variables:** one boolean per person per shift they could legally work.
- **Hard constraints:** rest and overlap conflicts are pairwise. Day and
  week totals are linear. "A rest day in every 7" is a sliding window over
  per-day *worked* indicators.
- **Objective:** one weighted objective in cents. An uncovered minute costs
  more than any wage, scaled by the shift's priority. Then come wages with
  overtime and public-holiday premiums (overtime is an auxiliary variable per
  week). Then come fairness (absolute deviation from each person's target),
  preferred days off and, when re-planning, a change penalty.

The demo week solves to proven optimality in about 0.05 s.

`explain.py` works out *why* a gap stayed open. For each trained person it
finds the first rule that blocks them, given everything else they are
rostered on. `audit.py` re-implements the rules independently, and every
solver test passes the result through it.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

There are 24 tests:
- Every rule in isolation: cheapest person wins, rest day, rest between
  days, overtime pay and the overtime cap, public-holiday premium, priority,
  fairness, pins.
- Re-planning never rewrites the past and changes only what it must.
- The audit catches a hand-made rota that breaks rules.
- Input errors are explained, overnight shifts work, and every export
  format is checked.
- API tests show that two sick calls in a row compound instead of undoing
  each other. That was a real bug, caught while building the web flow.

What it is and isn't good for yet, and who it's for: [docs/PRODUCT.md](docs/PRODUCT.md).
