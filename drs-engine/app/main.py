"""FastAPI application - serves the API and the web UI on localhost."""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import RetentionEngine
from .exporters import issuance_pdf, register_xlsx, schedule_xlsx
from .llm import LLMAdvisor
from .store import Store, now

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATIC = ROOT / "static"

store = Store(Path(os.getenv("DRS_DB", DATA / "drs.db")))
llm = LLMAdvisor()
engine = RetentionEngine(DATA, store=store, llm=llm)

app = FastAPI(title="Retention Schedule Determination Engine", version="1.0")


class AssessRequest(BaseModel):
    title: str = ""
    description: str
    data_owner: str = ""
    business_unit: str = ""
    system: str = ""
    asset_type: str = "Dataset"
    record_copy: str = "Official record"
    components: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=lambda: ["US"])
    client_data: bool = False
    employee_data: bool = False
    pii: bool = False
    legal_hold: bool = False
    use_llm: bool = True
    save: bool = True


class ReviewRequest(BaseModel):
    action: str  # approve | override | reject
    reviewer: str = ""
    notes: str = ""
    activity_id: str | None = None
    level: str | None = None
    adopt_proposal: bool = False  # for gaps: add proposed activity to the schedule extension


def _get(iid: str) -> dict:
    d = store.get(iid)
    if not d:
        raise HTTPException(404, "Issuance not found")
    return d


@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.status(), "activities": len(engine.activities),
            "training_examples": len(engine.example_texts), "schedule": engine.schedule["schedule_version"]}


@app.get("/api/schedule")
def schedule():
    cats: dict[str, dict] = {}
    for a in engine.activities:
        c = cats.setdefault(a.category_id, {"id": a.category_id, "name": a.category, "activities": []})
        c["activities"].append({**engine.activity_view(a.id), "keywords": a.keywords})
    ordered = sorted(cats.values(), key=lambda c: int(c["id"]) if c["id"].isdigit() else 99)
    return {"levels": engine.levels, "categories": ordered, "source_note": engine.schedule["source_note"]}


@app.get("/api/knowledge")
def knowledge():
    return engine.knowledge


@app.post("/api/assess")
def assess(req: AssessRequest):
    payload = req.model_dump()
    save = payload.pop("save")
    det = engine.determine(payload)
    if save:
        det = store.save_issuance(det, "Draft")
    return det


@app.get("/api/issuances")
def issuances(q: str = "", status: str = ""):
    return store.list(q, status)


@app.get("/api/issuances/{iid}")
def issuance(iid: str):
    return _get(iid)


@app.delete("/api/issuances/{iid}")
def delete_issuance(iid: str):
    store.delete(iid)
    return {"ok": True}


@app.post("/api/issuances/{iid}/review")
def review(iid: str, rv: ReviewRequest):
    d = _get(iid)
    req = d["request"]
    text = ". ".join(x for x in [req.get("title"), req.get("description")] + (req.get("components") or []) if x)
    action = rv.action.lower()
    learned_id = None

    if action == "approve":
        if d["coverage"] == "gap" and rv.adopt_proposal and d.get("proposal"):
            p = d["proposal"]
            rec = store.add_custom_activity({
                "category_id": p["proposed_category_id"], "category": p["proposed_category"],
                "name": p["proposed_activity"], "level": p["proposed_level"], "definition": p["proposed_definition"],
                "trigger_event": p["trigger_event"], "keywords": [p["proposed_activity"].lower()],
                "source_issuance": iid, "approved_by": rv.reviewer})
            engine.fit()
            d = engine.apply_override(d, rec["id"], d["final_level"])
            d["coverage_label"] = "Covered - new activity approved by DRD"
            learned_id = rec["id"]
        else:
            learned_id = d["governing"].get("activity_id")
        d["status"] = "Approved"
    elif action == "override":
        if rv.activity_id and rv.activity_id not in engine.by_id:
            raise HTTPException(400, "Unknown activity id")
        d = engine.apply_override(d, rv.activity_id, rv.level)
        d["status"] = "Approved (Override)"
        learned_id = rv.activity_id or d["governing"].get("activity_id")
    elif action == "reject":
        d["status"] = "Rejected"
    else:
        raise HTTPException(400, "action must be approve, override or reject")

    d["review"] = {"action": action, "reviewer": rv.reviewer, "notes": rv.notes, "at": now(),
                   "activity_id": rv.activity_id, "level": rv.level}
    store.add_feedback(iid, action, text, learned_id if action != "reject" else None, d["final_level"], rv.reviewer, rv.notes)
    if learned_id:
        engine.fit()  # the model learns from every reviewer decision
    return store.save_issuance(d)


@app.get("/api/issuances/{iid}/export")
def export(iid: str, fmt: str = "pdf"):
    d = _get(iid)
    if fmt == "pdf":
        return Response(issuance_pdf(d), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{iid}.pdf"'})
    if fmt == "xlsx":
        return Response(register_xlsx([d], f"Retention Schedule Issuance {iid}"),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{iid}.xlsx"'})
    if fmt == "json":
        return Response(json.dumps(d, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{iid}.json"'})
    raise HTTPException(400, "fmt must be pdf, xlsx or json")


@app.get("/api/register.xlsx")
def register(ids: str = ""):
    rows = store.list()
    wanted = set(ids.split(",")) if ids else None
    dets = [store.get(r["id"]) for r in rows if not wanted or r["id"] in wanted]
    return Response(register_xlsx(dets), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="retention_register.xlsx"'})


@app.get("/api/schedule.xlsx")
def schedule_download():
    return Response(schedule_xlsx(engine), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="retention_schedule.xlsx"'})


@app.get("/api/batch/template.csv")
def batch_template():
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(["title", "description", "data_owner", "business_unit", "asset_type", "components",
                "client_data", "employee_data", "pii", "legal_hold", "jurisdictions", "record_copy"])
    w.writerow(["Client 360 data product", "Unified client view for advisors", "Jane Doe", "Client Data Products",
                "Data Product", "Client account master | Client call transcripts | Reg BI reviews", "Y", "N", "Y", "N",
                "US", "Copy / derived"])
    return Response(s.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="batch_template.csv"'})


@app.post("/api/batch")
async def batch(file: UploadFile = File(...), use_llm: bool = False):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    yes = lambda v: str(v or "").strip().lower() in ("y", "yes", "true", "1", "x")
    out = []
    for row in csv.DictReader(io.StringIO(raw)):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not row.get("description"):
            continue
        req = {"title": row.get("title", ""), "description": row["description"],
               "data_owner": row.get("data_owner", ""), "business_unit": row.get("business_unit", ""),
               "asset_type": row.get("asset_type") or "Dataset",
               "components": [c.strip() for c in row.get("components", "").split("|") if c.strip()],
               "client_data": yes(row.get("client_data")), "employee_data": yes(row.get("employee_data")),
               "pii": yes(row.get("pii")), "legal_hold": yes(row.get("legal_hold")),
               "jurisdictions": [j.strip().upper() for j in (row.get("jurisdictions") or "US").replace(";", ",").split(",") if j.strip()],
               "record_copy": row.get("record_copy") or "Official record", "use_llm": use_llm, "system": row.get("system", "")}
        out.append(store.save_issuance(engine.determine(req), "Draft"))
    return {"count": len(out), "ids": [d["issuance_id"] for d in out],
            "results": [{"id": d["issuance_id"], "title": d["request"]["title"], "level": d["final_level"],
                         "activity": d["governing"]["activity"], "coverage": d["coverage"],
                         "confidence": d["confidence"]} for d in out]}


@app.get("/api/stats")
def stats():
    s = store.stats()
    allx = [store.get(r["id"]) for r in store.list()]
    gaps = [d for d in allx if d["coverage"] == "gap" or d.get("original_coverage") == "gap"]
    s["by_coverage"]["gap"] = len(gaps)
    s["gaps"] = [{"id": d["issuance_id"], "title": d["request"].get("title"), "status": d["status"],
                  **(d.get("proposal") or {})} for d in gaps]
    s["custom"] = store.custom_activities()
    s["llm"] = llm.status()
    s["training_examples"] = len(engine.example_texts)
    return s


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
