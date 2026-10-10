"""Roster outputs: CSV for payroll, .ics calendars, a message per person
(paste into WhatsApp), and a printable HTML rota."""
from __future__ import annotations

import csv
import hashlib
import html
import io
from datetime import timedelta

from .explain import Gap, StaffSummary
from .model import Problem, as_datetime


def _rows(p: Problem, assignments: list[tuple[str, str]]):
    shifts = {sh.id: sh for sh in p.shifts}
    people = p.staff_by_id()
    for sid, kid in sorted(assignments, key=lambda a: (shifts[a[1]].start, a[0])):
        yield people[sid], shifts[kid]


def to_csv(p: Problem, assignments: list[tuple[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "start", "end", "role", "staff_id", "staff", "paid_hours", "public_holiday"])
    for s, sh in _rows(p, assignments):
        start, end = as_datetime(p, sh.start), as_datetime(p, sh.end)
        w.writerow([sh.day.isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M"), sh.role, s.id,
                    s.name, round(sh.paid_minutes / 60, 2), sh.day in p.public_holidays])
    return buf.getvalue()


def to_ics(p: Problem, assignments: list[tuple[str, str]], staff_id: str) -> str:
    """One calendar per person. Floating local times, so it shows correctly
    in whatever timezone their phone is in for the shop's location."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//fairshift//{p.name}//EN", "CALSCALE:GREGORIAN"]
    for s, sh in _rows(p, assignments):
        if s.id != staff_id:
            continue
        uid = hashlib.sha1(f"{p.name}|{s.id}|{sh.id}".encode()).hexdigest()
        lines += ["BEGIN:VEVENT", f"UID:{uid}@fairshift",
                  f"DTSTAMP:{as_datetime(p, 0):%Y%m%dT%H%M%S}",
                  f"DTSTART:{as_datetime(p, sh.start):%Y%m%dT%H%M%S}",
                  f"DTEND:{as_datetime(p, sh.end):%Y%m%dT%H%M%S}",
                  f"SUMMARY:{sh.role} shift ({p.name})",
                  f"DESCRIPTION:Unpaid break {sh.break_minutes} min", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def messages(p: Problem, assignments: list[tuple[str, str]]) -> dict[str, str]:
    """A plain-text rota per person, ready to paste into a chat."""
    out: dict[str, list[str]] = {s.id: [] for s in p.staff}
    for s, sh in _rows(p, assignments):
        start, end = as_datetime(p, sh.start), as_datetime(p, sh.end)
        ph = " (public holiday)" if sh.day in p.public_holidays else ""
        out[s.id].append(f"• {start:%a %d %b} {start:%H:%M}–{end:%H:%M} {sh.role}{ph}")
    last = p.start + timedelta(days=p.days - 1)
    people = p.staff_by_id()
    return {sid: (f"Hi {people[sid].name}, your shifts at {p.name} for {p.start:%d %b}–{last:%d %b}:\n"
                  + ("\n".join(lines) if lines else "• no shifts this period"))
            for sid, lines in out.items()}


def to_html(p: Problem, assignments: list[tuple[str, str]], summary: list[StaffSummary],
            gap_list: list[Gap], totals: dict) -> str:
    """A self-contained printable rota: people down, days across."""
    days = [p.start + timedelta(d) for d in range(p.days)]
    cell: dict[tuple[str, int], list[str]] = {}
    for s, sh in _rows(p, assignments):
        a, b = as_datetime(p, sh.start), as_datetime(p, sh.end)
        cell.setdefault((s.id, p.day_index(sh.day)), []).append(
            f"<div class='sh'>{a:%H:%M}–{b:%H:%M}<span>{html.escape(sh.role)}</span></div>")
    by_id = {x.id: x for x in summary}
    head = "".join(f"<th class='{ 'ph' if d in p.public_holidays else ''}'>{d:%a}<br>{d:%d %b}</th>" for d in days)
    body = ""
    for s in p.staff:
        sm = by_id[s.id]
        cells = "".join(f"<td>{''.join(cell.get((s.id, i), [])) or '<span class=off>off</span>'}</td>"
                        for i in range(p.days))
        target = f" / {sm.target_hours:g}" if sm.target_hours is not None else ""
        ot = f" <b class=ot>+{sm.overtime_hours:g} OT</b>" if sm.overtime_hours else ""
        body += f"<tr><th>{html.escape(s.name)}<small>{sm.hours:g}h{target}{ot} · ${sm.pay:,.2f}</small></th>{cells}</tr>"
    gaps_html = "".join(
        f"<li><b>{html.escape(g.label)}</b> short {g.short}<ul>"
        + "".join(f"<li>{html.escape(n)}: {html.escape(w)}</li>" for n, w in g.reasons.items())
        + "</ul></li>" for g in gap_list) or "<li>Every shift is covered.</li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(p.name)} rota</title>
<style>
:root{{--bg:#fff;--fg:#1c1c1a;--mut:#6b6b66;--line:#e2e1dc;--chip:#eef2ff;--ph:#fff4e5;--bad:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--fg:#ecebe6;--mut:#9c9b95;--line:#2e2d2a;--chip:#232a40;--ph:#3a2f1c;--bad:#ff7b72}}}}
body{{font:14px/1.45 system-ui,sans-serif;margin:24px;background:var(--bg);color:var(--fg)}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid var(--line);padding:6px;vertical-align:top}}
thead th{{font-weight:600}} th small{{display:block;color:var(--mut);font-weight:400}}
th.ph{{background:var(--ph)}} .sh{{background:var(--chip);border-radius:6px;padding:3px 6px;margin:2px 0;white-space:nowrap}}
.sh span{{display:block;font-size:12px;color:var(--mut)}} .off{{color:var(--mut)}} .ot{{color:var(--bad)}}
.kpi{{display:flex;gap:24px;flex-wrap:wrap;margin:8px 0 16px}} .kpi div b{{display:block;font-size:20px}}
@media print{{body{{margin:8mm}} .noprint{{display:none}}}}
</style></head><body>
<h1>{html.escape(p.name)}: {p.start:%d %b}–{days[-1]:%d %b %Y}</h1>
<div class="kpi"><div><b>{totals['coverage']:.0%}</b>coverage</div><div><b>${totals['labour_cost']:,.2f}</b>labour cost</div>
<div><b>{totals['hours']:g}h</b>rostered</div><div><b>{totals['overtime_hours']:g}h</b>overtime</div></div>
<table><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>
<h2>Gaps</h2><ul>{gaps_html}</ul>
<p class="noprint" style="color:var(--mut)">Generated by fairshift. Labour-rule defaults follow the Singapore Employment Act Part IV limits; check them for your staff.</p>
</body></html>"""
