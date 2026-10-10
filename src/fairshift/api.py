"""HTTP API and the single-page web app.

    GET  /                 the app
    GET  /api/demo         the demo café as YAML
    POST /api/solve        {"yaml": "..."} -> roster
    POST /api/replan       {"yaml": "...", "assignments": [[staff, shift]...],
                            "absent": "farid", "from": "2026-10-15", "to": null}
"""
from __future__ import annotations

from datetime import date, timedelta
from importlib import resources

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import demo, explain, export, model, replan
from .cli import result
from .solver import solve

MAX_YAML = 200_000          # bytes: a large shop is a few KB
TIME_LIMIT = 15.0           # seconds per request

app = FastAPI(title="fairshift", version="0.1.0")


class SolveRequest(BaseModel):
    yaml: str = Field(max_length=MAX_YAML)


class ReplanRequest(SolveRequest):
    assignments: list[tuple[str, str]]
    absent: str
    from_: date = Field(alias="from")
    to: date | None = None


def _problem(text: str) -> model.Problem:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise HTTPException(422, f"YAML: {e}") from e
    if not isinstance(doc, dict):
        raise HTTPException(422, "expected a YAML mapping")
    try:
        return model.parse(doc)
    except (model.ProblemError, KeyError, TypeError) as e:
        raise HTTPException(422, f"{type(e).__name__}: {e}") from e


def _respond(p: model.Problem, sol) -> dict:
    res = result(p, sol)
    res["rota_html"] = export.to_html(p, sol.assignments, explain.summarise(p, sol), explain.gaps(p, sol),
                                      res["totals"])
    res["csv"] = export.to_csv(p, sol.assignments)
    res["messages"] = export.messages(p, sol.assignments)
    return res


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return resources.files("fairshift").joinpath("static/index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/demo")
def demo_yaml() -> dict:
    return {"yaml": yaml.safe_dump(demo.cafe(), sort_keys=False, allow_unicode=True, width=120)}


@app.post("/api/solve")
def api_solve(req: SolveRequest) -> dict:
    p = _problem(req.yaml)
    try:
        return _respond(p, solve(p, time_limit=TIME_LIMIT))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/replan")
def api_replan(req: ReplanRequest) -> dict:
    p = _problem(req.yaml)
    try:
        q, sol = replan.replan(p, req.assignments, req.absent, req.from_, req.to, time_limit=TIME_LIMIT)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e)) from e
    res = _respond(q, sol)
    res["changes"] = replan.diff(req.assignments, sol.assignments, p)
    res["yaml"] = record_absence(req.yaml, req.absent, req.from_, req.to or p.start + timedelta(p.days - 1))
    return res


def record_absence(text: str, staff_id: str, start: date, end: date) -> str:
    """The shop's YAML with the absence written in, so a second sick call
    re-plans from the first one instead of quietly undoing it."""
    doc = yaml.safe_load(text)
    for s in doc.get("staff", []):
        if str(s.get("id") or s.get("name")) == staff_id:
            dates = {str(d) for d in s.get("unavailable_dates", [])}
            dates |= {(start + timedelta(k)).isoformat() for k in range((end - start).days + 1)}
            s["unavailable_dates"] = sorted(dates)
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)
