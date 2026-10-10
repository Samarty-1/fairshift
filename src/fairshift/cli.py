"""fairshift command line.

    fairshift demo                         solve the demo café, write every output
    fairshift solve shop.yaml --out rota/
    fairshift replan shop.yaml --roster rota/roster.json --absent farid --from 2026-10-15
    fairshift check shop.yaml --roster rota.csv   audit any roster, e.g. a hand-made one
    fairshift serve                        web app on http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import yaml

from . import audit, demo, explain, export, model, replan
from .solver import Solution, solve


def load(path: Path) -> model.Problem:
    with open(path, encoding="utf-8") as f:
        return model.parse(yaml.safe_load(f))


def result(p: model.Problem, sol: Solution) -> dict:
    return {
        "name": p.name, "start": p.start.isoformat(), "days": p.days,
        "totals": explain.totals(p, sol),
        "staff": [asdict(s) for s in explain.summarise(p, sol)],
        "gaps": [asdict(g) for g in explain.gaps(p, sol)],
        "assignments": [list(a) for a in sol.assignments],
    }


def write_outputs(p: model.Problem, sol: Solution, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    res = result(p, sol)
    summ, gap_list = explain.summarise(p, sol), explain.gaps(p, sol)
    (out / "roster.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (out / "roster.csv").write_text(export.to_csv(p, sol.assignments), encoding="utf-8")
    (out / "rota.html").write_text(export.to_html(p, sol.assignments, summ, gap_list, res["totals"]),
                                   encoding="utf-8")
    msgs = export.messages(p, sol.assignments)
    (out / "messages.txt").write_text("\n\n".join(msgs.values()) + "\n", encoding="utf-8")
    (out / "calendars").mkdir(exist_ok=True)
    for s in p.staff:
        (out / "calendars" / f"{s.id}.ics").write_text(export.to_ics(p, sol.assignments, s.id), encoding="utf-8")
    return res


def read_roster(p: model.Problem, path: Path) -> list[tuple[str, str]]:
    """roster.json from fairshift, or a CSV with staff_id,date,start,end,role
    (the same columns fairshift writes), e.g. exported from a spreadsheet."""
    if path.suffix == ".json":
        return [tuple(x) for x in json.loads(path.read_text(encoding="utf-8"))["assignments"]]
    import csv
    ids = {sh.id for sh in p.shifts}
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kid = f"{row['date']}-{row['role']}-{row['start']}-{row['end']}"
            if kid not in ids:
                raise ValueError(f"{path.name}: no demand line matches {kid}")
            out.append((row["staff_id"], kid))
    return out


def report(res: dict) -> None:
    t = res["totals"]
    print(f"{res['name']}: {t['status']}, coverage {t['coverage']:.1%}, labour ${t['labour_cost']:,.2f}, "
          f"{t['hours']:g}h ({t['overtime_hours']:g}h overtime), solved in {t['solve_seconds']}s")
    if t["changes_from_previous"] is not None:
        print(f"changes from the published roster: {t['changes_from_previous']}")
    for s in res["staff"]:
        target = f" (target {s['target_hours']:g})" if s["target_hours"] is not None else ""
        print(f"  {s['name']:<12} {s['hours']:>5.1f}h{target:<14} ${s['pay']:>8,.2f}")
    for g in res["gaps"]:
        print(f"GAP {g['label']} short {g['short']}")
        for name, why in g["reasons"].items():
            print(f"    {name}: {why}")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="fairshift", description="Staff rostering for shops and cafés")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="solve the demo café and write every output")
    d.add_argument("--out", type=Path, default=Path("demo-rota"))
    s = sub.add_parser("solve", help="solve a roster from YAML")
    s.add_argument("problem", type=Path)
    s.add_argument("--out", type=Path, default=Path("rota"))
    s.add_argument("--time-limit", type=float, default=20.0)
    r = sub.add_parser("replan", help="someone is absent: re-plan with minimal changes")
    r.add_argument("problem", type=Path)
    r.add_argument("--roster", type=Path, required=True, help="roster.json from a previous solve")
    r.add_argument("--absent", required=True, help="staff id")
    r.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    r.add_argument("--to", dest="end", type=date.fromisoformat)
    r.add_argument("--out", type=Path, default=Path("rota-replan"))
    c = sub.add_parser("check", help="audit a roster (CSV with staff_id + date/start/end/role, or roster.json)")
    c.add_argument("problem", type=Path)
    c.add_argument("--roster", type=Path, required=True)
    v = sub.add_parser("serve", help="run the web app")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    try:
        if a.cmd == "demo":
            p = model.parse(demo.cafe())
            res = write_outputs(p, solve(p), a.out)
            report(res)
            print(f"\nwrote {a.out}/rota.html, roster.csv, messages.txt, calendars/*.ics")
        elif a.cmd == "solve":
            p = load(a.problem)
            report(write_outputs(p, solve(p, time_limit=a.time_limit), a.out))
        elif a.cmd == "replan":
            p = load(a.problem)
            before = [tuple(x) for x in json.loads(a.roster.read_text(encoding="utf-8"))["assignments"]]
            q, sol = replan.replan(p, before, a.absent, a.start, a.end)
            res = write_outputs(q, sol, a.out)
            report(res)
            print("\nchanges:\n" + ("\n".join(replan.diff(before, sol.assignments, p)) or "none"))
        elif a.cmd == "check":
            p = load(a.problem)
            found = audit.audit(p, read_roster(p, a.roster))
            for v in found:
                print(f"{v.rule:<15} {v.staff:<12} {v.detail}")
            print(f"{len(found)} problem(s)" if found else "no rule broken")
            return 1 if found else 0
        elif a.cmd == "serve":
            import uvicorn
            uvicorn.run("fairshift.api:app", host=a.host, port=a.port)
    except (model.ProblemError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
