"""Downloadable outputs: PDF issuance, Excel issuance / register, JSON."""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#1C1C1E")
GREY = colors.HexColor("#6E6E73")
LINE = colors.HexColor("#E5E5EA")
BLUE = colors.HexColor("#0A84FF")
LEVEL_COLORS = {"I": "#34C759", "II": "#30B0C7", "III": "#0A84FF", "IV": "#5E5CE6", "V": "#FF9F0A", "VI": "#FF375F"}


def _esc(s) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def issuance_pdf(d: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title=f"Retention Schedule Issuance {d['issuance_id']}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=INK,
                        alignment=TA_LEFT, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, textColor=GREY)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, textColor=INK,
                        spaceBefore=12, spaceAfter=5)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
    small = ParagraphStyle("s", parent=body, fontSize=8.5, leading=11, textColor=GREY)
    big = ParagraphStyle("big", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=19)

    req, g = d["request"], d["governing"]
    lvl_col = colors.HexColor(LEVEL_COLORS.get(d["final_level"], "#0A84FF"))
    el = [Paragraph("Retention Schedule Issuance", h1),
          Paragraph(f"{_esc(d['issuance_id'])} &nbsp;·&nbsp; Status: <b>{_esc(d['status'])}</b> &nbsp;·&nbsp; "
                    f"Issued {_esc(d['issued_at'][:10])} &nbsp;·&nbsp; {_esc(d['schedule_version'])}", sub),
          Spacer(1, 12)]

    hero = Table([[Paragraph(f"<font color='white'><b>LEVEL {d['final_level']}</b></font>", big),
                   Paragraph(f"<b>{_esc(d['final_level_label'])}</b><br/>{_esc(d['retention_statement'])}", body)]],
                 colWidths=[1.35 * inch, 5.65 * inch])
    hero.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), lvl_col), ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F2F2F7")),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "CENTER"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 10),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    el.append(hero)

    def kv(rows):
        t = Table([[Paragraph(f"<b>{_esc(k)}</b>", small), Paragraph(_esc(v), body)] for k, v in rows],
                  colWidths=[1.9 * inch, 5.1 * inch])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return t

    el += [Paragraph("Determination", h2), kv([
        ("Coverage", d["coverage_label"]),
        ("Business category", g["category"]),
        ("Governing business activity", g["activity"] + (f"  ({g['activity_id']})" if g.get("activity_id") else "")),
        ("Schedule level of activity", g["level_label"]),
        ("Retention trigger", d["trigger_event"]),
        ("Regulatory uplift applied", "Yes" if d["regulatory_uplift"] else "No"),
        ("Disposition", d["disposition"]),
        ("Confidence", f"{d['confidence']}%" + ("  -  DRD review required" if d.get("review_required") else "")),
    ])]

    el += [Paragraph("Data asset", h2), kv([
        ("Title", req.get("title")), ("Asset type", req.get("asset_type")),
        ("Data owner", req.get("data_owner")), ("Business unit / product team", req.get("business_unit")),
        ("Record status", req.get("record_copy")), ("System / platform", req.get("system")),
        ("Jurisdictions", ", ".join(req.get("jurisdictions") or [])),
        ("Data flags", ", ".join(lab for k, lab in [("client_data", "Client data"), ("employee_data", "Employee data"),
                                                   ("pii", "Personal information"), ("legal_hold", "Legal hold")]
                                  if req.get(k)) or "None"),
        ("Description", req.get("description")),
    ])]

    el.append(Paragraph("Rationale", h2))
    for r in d["rationale"]:
        el.append(Paragraph("• " + _esc(r), body))
    for n in d.get("notes", []):
        el.append(Paragraph("• " + _esc(n), body))

    if d.get("components"):
        rows = [["Source / component", "Business activity", "Level", "Match"]]
        for c in d["components"]:
            rows.append([Paragraph(_esc(c["text"]), small), Paragraph(_esc(c["activity"]) if c["matched"] else
                         "<i>no confident match</i>", small), c["level"] if c["matched"] else "-", f"{c['score']:.2f}"])
        t = Table(rows, colWidths=[3.1 * inch, 2.5 * inch, 0.6 * inch, 0.8 * inch], repeatRows=1)
        t.setStyle(_grid())
        el += [Paragraph("Component breakdown", h2), t]

    if d.get("regulatory"):
        rows = [["Requirement", "Citation", "Minimum", "Met by schedule"]]
        for r in d["regulatory"]:
            f = r.get("floor")
            mn = ("Ceiling / minimization" if r["type"] == "ceiling" else "Permanent" if f and f["trigger"] == "permanent"
                  else f"{f['years']} yrs after {f.get('event') or 'creation'}" if f else "-")
            met = "-" if r["type"] == "ceiling" else ("Yes" if r.get("satisfied_by_schedule") else f"No -> Level {r.get('minimum_level')}")
            rows.append([Paragraph(_esc(r["name"]), small), Paragraph(_esc(r["citation"]), small), Paragraph(_esc(mn), small), met])
        t = Table(rows, colWidths=[2.2 * inch, 2.3 * inch, 1.5 * inch, 1.0 * inch], repeatRows=1)
        t.setStyle(_grid())
        el += [Paragraph("Regulatory minimums considered", h2), t,
               Paragraph("Regulatory references are decision support and must be validated by Legal/Compliance.", small)]

    if d.get("proposal"):
        p = d["proposal"]
        el += [Paragraph("Proposed new business activity (pending DRD approval)", h2), kv([
            ("Proposed activity", p["proposed_activity"]), ("Proposed category", p["proposed_category"]),
            ("Proposed level", p["proposed_level"]), ("Trigger", p["trigger_event"]),
            ("Nearest existing activity", f"{p['nearest_activity']} (similarity {p['nearest_score']:.2f})"),
            ("Definition", p["proposed_definition"])])]

    if d.get("review"):
        rv = d["review"]
        el += [Paragraph("Review and approval", h2), kv([
            ("Decision", rv.get("action", "").title()), ("Reviewer", rv.get("reviewer")),
            ("Date", (rv.get("at") or "")[:10]), ("Notes", rv.get("notes"))])]

    sig = Table([["Data Owner", "", "DRD / Records Management", ""],
                 ["Signature / date", "", "Signature / date", ""]], colWidths=[1.5 * inch, 2 * inch, 1.5 * inch, 2 * inch])
    sig.setStyle(TableStyle([("LINEBELOW", (1, 0), (1, 1), 0.5, GREY), ("LINEBELOW", (3, 0), (3, 1), 0.5, GREY),
                             ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), GREY),
                             ("TOPPADDING", (0, 0), (-1, -1), 12)]))
    el += [Spacer(1, 14), KeepTogether([Paragraph("Acknowledgement", h2), sig])]

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(0.75 * inch, 0.45 * inch, "Internal Use Only - Generated by the Retention Schedule Determination Engine")
        canvas.drawRightString(LETTER[0] - 0.75 * inch, 0.45 * inch, f"{d['issuance_id']}  ·  Page {_doc.page}")
        canvas.restoreState()

    doc.build(el, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _grid():
    return TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F7")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                       ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
                       ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])


# ---------------------------------------------------------------- Excel
HDR_FILL = PatternFill("solid", fgColor="1C1C1E")
HDR_FONT = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
THIN = Border(bottom=Side(style="thin", color="E5E5EA"))

REGISTER_COLS = [
    ("Issuance ID", 18), ("Issued", 12), ("Status", 18), ("Asset title", 34), ("Asset type", 15), ("Data owner", 20),
    ("Business unit", 20), ("Category", 26), ("Business activity", 36), ("Retention level", 9),
    ("Retention period", 40), ("Trigger event", 36), ("Retention statement", 60), ("Coverage", 30),
    ("Regulatory uplift", 10), ("Regulatory citations", 50), ("Confidence %", 11), ("Review required", 10),
    ("Legal hold", 9), ("Disposition", 50), ("Description", 60),
]


def _register_row(d: dict) -> list:
    r, g = d["request"], d["governing"]
    return [d["issuance_id"], d["issued_at"][:10], d["status"], r.get("title"), r.get("asset_type"), r.get("data_owner"),
            r.get("business_unit"), g["category"], g["activity"], d["final_level"], d["final_level_label"],
            d["trigger_event"], d["retention_statement"], d["coverage_label"], "Yes" if d["regulatory_uplift"] else "No",
            "; ".join(x["citation"] for x in d.get("regulatory", [])), d["confidence"],
            "Yes" if d.get("review_required") else "No", "Yes" if r.get("legal_hold") else "No", d["disposition"],
            r.get("description")]


def _sheet(ws, cols, rows):
    ws.append([c for c, _ in cols])
    for i, (_, w) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        cell = ws.cell(row=1, column=i)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = THIN
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 30


def register_xlsx(dets: list[dict], title="Retention Schedule Register") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Register"
    _sheet(ws, REGISTER_COLS, [_register_row(d) for d in dets])

    comp_cols = [("Issuance ID", 18), ("Kind", 11), ("Source / component", 60), ("Business activity", 36),
                 ("Level", 8), ("Match score", 11), ("Matched", 9)]
    _sheet(wb.create_sheet("Components"), comp_cols,
           [[d["issuance_id"], c["kind"], c["text"], c["activity"], c["level"], c["score"], "Yes" if c["matched"] else "No"]
            for d in dets for c in d.get("components", [])])

    reg_cols = [("Issuance ID", 18), ("Requirement", 40), ("Citation", 45), ("Jurisdiction", 11), ("Type", 9),
                ("Minimum", 30), ("Met by schedule", 14), ("Minimum level", 12), ("Note", 60)]
    rr = []
    for d in dets:
        for x in d.get("regulatory", []):
            f = x.get("floor")
            mn = "-" if not f else ("Permanent" if f["trigger"] == "permanent" else f"{f['years']} yrs after {f.get('event') or 'creation'}")
            rr.append([d["issuance_id"], x["name"], x["citation"], x["jurisdiction"], x["type"], mn,
                       "-" if x["type"] == "ceiling" else ("Yes" if x.get("satisfied_by_schedule") else "No"),
                       x.get("minimum_level", "-"), x["note"]])
    _sheet(wb.create_sheet("Regulatory"), reg_cols, rr)

    prop_cols = [("Issuance ID", 18), ("Proposed activity", 36), ("Proposed category", 26), ("Proposed level", 10),
                 ("Trigger", 30), ("Nearest existing activity", 32), ("Definition", 70)]
    _sheet(wb.create_sheet("Proposed activities"), prop_cols,
           [[d["issuance_id"], p["proposed_activity"], p["proposed_category"], p["proposed_level"], p["trigger_event"],
             p["nearest_activity"], p["proposed_definition"]] for d in dets if (p := d.get("proposal"))])

    meta = wb.create_sheet("About")
    meta.append([title])
    meta.append([f"Generated {datetime.now():%Y-%m-%d %H:%M}"])
    meta.append(["Regulatory references are decision support only and must be validated by Legal/Compliance."])
    meta["A1"].font = Font(bold=True, size=14)
    meta.column_dimensions["A"].width = 100

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def schedule_xlsx(engine) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Retention Schedule"
    cols = [("Category", 30), ("Activity ID", 11), ("Business activity", 40), ("Approved retention", 44),
            ("Trigger event", 44), ("Definition", 80), ("Source", 22)]
    rows = [[a.category, a.id, a.name, engine.levels[a.level]["label"], a.trigger_event, a.definition,
             "DRD-approved extension" if a.custom else "General Retention Schedule"] for a in engine.activities]
    _sheet(ws, cols, rows)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
