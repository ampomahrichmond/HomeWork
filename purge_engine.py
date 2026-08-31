#!/usr/bin/env python3
"""
Purge Request Tracking Engine
=============================
Point this at a folder of purge-request spreadsheets (.xlsx / .xlsm / .xls / .csv).
It reads every sheet in every file, maps varying column headers onto one canonical
schema, combines everything, runs data-quality checks, computes statistics, and
writes a single self-contained HTML dashboard (no internet needed to view it).

Usage:
    python purge_engine.py /path/to/folder
    python purge_engine.py /path/to/folder -o purge_dashboard.html

Requires: pandas, openpyxl   (pip install pandas openpyxl)
"""

import argparse
import html
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------------
# 1. CANONICAL SCHEMA + HEADER ALIASES
#    Add aliases here as teams invent new spellings. Matching is done on a
#    normalized form (lowercase, alphanumeric only), then by keyword fallback.
# ----------------------------------------------------------------------------

CANONICAL_COLUMNS = {
    "request_id":            ["request id", "req id", "request #", "request no", "request number", "id", "ticket id", "ticket #"],
    "record_owner":          ["record owner name", "record owner", "owner name", "owner", "data owner", "business owner", "requestor", "requester"],
    "department":            ["department", "dept", "business unit", "bu", "division", "lob", "line of business"],
    "application":           ["application system name", "application name", "application", "app name", "system name", "system", "app system", "source system"],
    "location":              ["location of the records to be purged", "location of records", "record location", "location", "storage location", "server/path", "path"],
    "data_type":             ["data type", "data type (structured, semi-structured or unstructured)", "type of data", "data classification", "structure type"],
    "description":           ["description of data", "data description", "description", "data desc", "details"],
    "retention_schedule":    ["retention schedule in place", "retention schedule in place (yes/no)", "retention schedule", "schedule in place", "rs in place", "retention schedule?"],
    "retention_activity":    ["retention business activity", "business activity", "retention activity", "rim business activity", "records class", "record class"],
    "retention_event":       ["retention event", "trigger event", "event", "retention trigger"],
    "retention_period":      ["retention period", "retention period (years)", "retention yrs", "retention duration", "period"],
    "reason_for_purge":      ["reason for purge", "purge reason", "reason", "justification", "purge justification"],
    "num_records":           ["# of records to be purged", "number of records", "record count", "num records", "records to be purged", "# records", "row count", "no of records"],
    "data_size":             ["size of table/data being purged", "size of data", "data size", "size", "table size", "volume", "size (gb)"],
    "proposed_purge_date":   ["proposed purge date", "purge date", "target purge date", "planned purge date", "scheduled purge date", "target date"],
    "status":                ["status", "request status", "purge status", "state"],
    "approver":              ["approver", "approved by", "legal approver", "approval"],
    "submitted_date":        ["submitted date", "date submitted", "request date", "date of request", "created date"],
}

# Fields that MUST be populated for a request to be considered complete.
CRITICAL_FIELDS = [
    "request_id", "record_owner", "department", "application",
    "data_type", "retention_schedule", "reason_for_purge", "proposed_purge_date",
]

# Fields that are nice to have; missing => warning, not critical.
IMPORTANT_FIELDS = ["location", "description", "num_records", "data_size", "retention_period"]

FIELD_LABELS = {
    "request_id": "Request ID", "record_owner": "Record Owner", "department": "Department",
    "application": "Application System", "location": "Record Location", "data_type": "Data Type",
    "description": "Description of Data", "retention_schedule": "Retention Schedule in Place",
    "retention_activity": "Retention Business Activity", "retention_event": "Retention Event",
    "retention_period": "Retention Period", "reason_for_purge": "Reason for Purge",
    "num_records": "# of Records", "data_size": "Size of Data",
    "proposed_purge_date": "Proposed Purge Date", "status": "Status",
    "approver": "Approver", "submitted_date": "Submitted Date",
}

VALID_DATA_TYPES = {"structured", "semi-structured", "unstructured"}


def _norm(s: str) -> str:
    """Normalize a header for matching: lowercase, alphanumeric only."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# Precompute normalized alias -> canonical lookup
_ALIAS_LOOKUP = {}
for canon, aliases in CANONICAL_COLUMNS.items():
    _ALIAS_LOOKUP[_norm(canon)] = canon
    for a in aliases:
        _ALIAS_LOOKUP[_norm(a)] = canon

# Keyword fallback (checked in order) when no exact alias hit
_KEYWORD_RULES = [
    ("request_id", ["requestid", "reqid", "ticketid"]),
    ("record_owner", ["owner", "requestor", "requester"]),
    ("department", ["department", "dept", "businessunit", "division"]),
    ("application", ["application", "appsystem", "systemname", "sourcesystem"]),
    ("location", ["location", "path"]),
    ("data_type", ["datatype", "typeofdata"]),
    ("retention_schedule", ["retentionschedule", "scheduleinplace"]),
    ("retention_activity", ["businessactivity", "recordclass", "recordsclass"]),
    ("retention_event", ["retentionevent", "triggerevent"]),
    ("retention_period", ["retentionperiod", "retentionyrs", "retentionduration"]),
    ("reason_for_purge", ["reason", "justification"]),
    ("num_records", ["records", "recordcount", "rowcount"]),
    ("data_size", ["size", "volume"]),
    ("proposed_purge_date", ["purgedate", "targetdate"]),
    ("submitted_date", ["submitted", "requestdate", "createddate"]),
    ("description", ["description", "datadesc", "details"]),
    ("status", ["status", "state"]),
    ("approver", ["approver", "approvedby", "approval"]),
]


def map_header(header) -> str | None:
    """Map a raw column header to a canonical field name, or None if unknown."""
    n = _norm(header)
    if not n:
        return None
    if n in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[n]
    for canon, keys in _KEYWORD_RULES:
        if any(k in n for k in keys):
            return canon
    return None


# ----------------------------------------------------------------------------
# 2. FILE READING
# ----------------------------------------------------------------------------

def read_folder(folder: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Read every spreadsheet/CSV in the folder; return combined df + file log."""
    frames, file_log = [], []
    patterns = ["*.xlsx", "*.xlsm", "*.xls", "*.csv"]
    files = sorted({p for pat in patterns for p in folder.glob(pat) if not p.name.startswith("~$")})

    if not files:
        print(f"No spreadsheet files found in {folder}", file=sys.stderr)
        sys.exit(1)

    for f in files:
        try:
            if f.suffix.lower() == ".csv":
                sheets = {"csv": pd.read_csv(f, dtype=str)}
            else:
                sheets = pd.read_excel(f, sheet_name=None, dtype=str)
        except Exception as e:
            file_log.append({"file": f.name, "sheet": "-", "rows": 0, "mapped": [], "unmapped": [], "error": str(e)})
            continue

        for sheet_name, raw in sheets.items():
            if raw is None or raw.empty:
                continue
            raw = raw.dropna(how="all").dropna(axis=1, how="all")
            if raw.empty:
                continue

            mapped_cols, unmapped, out = {}, [], {}
            for col in raw.columns:
                canon = map_header(col)
                if canon and canon not in out:  # first match wins
                    out[canon] = raw[col]
                    mapped_cols[col] = canon
                elif not canon:
                    unmapped.append(str(col))

            if "request_id" not in out and len(out) < 3:
                # Probably not a purge tracker sheet (e.g., a notes tab) — skip it
                continue

            df = pd.DataFrame(out)
            df["source_file"] = f.name
            df["source_sheet"] = sheet_name
            frames.append(df)
            file_log.append({
                "file": f.name, "sheet": sheet_name, "rows": len(df),
                "mapped": sorted(set(mapped_cols.values())), "unmapped": unmapped, "error": None,
            })

    if not frames:
        print("Files were found but none contained recognizable purge-request columns.", file=sys.stderr)
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)
    # Guarantee all canonical columns exist
    for c in CANONICAL_COLUMNS:
        if c not in combined.columns:
            combined[c] = pd.NA
    return combined, file_log


# ----------------------------------------------------------------------------
# 3. CLEANING / STANDARDIZATION
# ----------------------------------------------------------------------------

_MISSING_TOKENS = {"", "na", "n/a", "none", "null", "tbd", "tba", "unknown", "?", "-", "--", "pending"}


def is_missing(v) -> bool:
    if pd.isna(v):
        return True
    return str(v).strip().lower() in _MISSING_TOKENS


def clean_yes_no(v):
    if is_missing(v):
        return pd.NA
    s = str(v).strip().lower()
    if s in {"y", "yes", "true", "1", "in place", "active"}:
        return "Yes"
    if s in {"n", "no", "false", "0", "not in place", "missing"}:
        return "No"
    return str(v).strip().title()


def clean_data_type(v):
    if is_missing(v):
        return pd.NA
    s = str(v).strip().lower().replace("_", "-").replace("semi structured", "semi-structured").replace("semistructured", "semi-structured")
    for t in VALID_DATA_TYPES:
        if t in s:
            return t.title() if t != "semi-structured" else "Semi-structured"
    return str(v).strip()  # keep as-is; DQ check will flag it


def parse_number(v):
    if is_missing(v):
        return None
    s = re.sub(r"[,\s]", "", str(v))
    m = re.search(r"[\d.]+", s)
    if not m:
        return None
    try:
        n = float(m.group())
    except ValueError:
        return None
    mult = 1
    low = s.lower()
    if re.search(r"[\d.]\s*m(illion)?\b", low) or low.endswith("m"):
        mult = 1_000_000
    elif re.search(r"[\d.]\s*k\b", low) or low.endswith("k"):
        mult = 1_000
    elif "b" in low and "gb" not in low and "mb" not in low and "tb" not in low and "kb" not in low:
        if re.search(r"[\d.]\s*b(illion)?\b", low):
            mult = 1_000_000_000
    return n * mult


def parse_size_gb(v):
    """Parse a size string into GB (float) where possible."""
    if is_missing(v):
        return None
    s = str(v).strip().lower().replace(",", "")
    m = re.search(r"([\d.]+)\s*(tb|gb|mb|kb|b)?", s)
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2) or "gb"
    factor = {"tb": 1024, "gb": 1, "mb": 1 / 1024, "kb": 1 / (1024 * 1024), "b": 1 / (1024 ** 3)}
    return n * factor.get(unit, 1)


def parse_date(v):
    if is_missing(v):
        return None
    if isinstance(v, (datetime, date)):
        return pd.Timestamp(v).normalize()
    ts = pd.to_datetime(str(v).strip(), errors="coerce", dayfirst=False)
    if pd.isna(ts):
        return None
    return ts.normalize()


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ["request_id", "record_owner", "department", "application", "location",
              "description", "retention_activity", "retention_event", "retention_period",
              "reason_for_purge", "status", "approver"]:
        df[c] = df[c].map(lambda v: pd.NA if is_missing(v) else str(v).strip())

    # Title-case people/departments lightly to merge "IT" vs "It"? — no, keep as-is
    df["retention_schedule"] = df["retention_schedule"].map(clean_yes_no)
    df["data_type"] = df["data_type"].map(clean_data_type)
    df["num_records_n"] = df["num_records"].map(parse_number)
    df["data_size_gb"] = df["data_size"].map(parse_size_gb)
    df["proposed_purge_dt"] = df["proposed_purge_date"].map(parse_date)
    df["submitted_dt"] = df["submitted_date"].map(parse_date)
    return df


# ----------------------------------------------------------------------------
# 4. DATA QUALITY CHECKS + FOLLOW-UP ENGINE
# ----------------------------------------------------------------------------

def run_dq(df: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    """Adds per-row issue lists and severity. Returns df with dq columns."""
    critical_issues, warning_issues = [], []

    dup_ids = df.loc[df["request_id"].notna(), "request_id"]
    dup_set = set(dup_ids[dup_ids.duplicated(keep=False)])

    for _, row in df.iterrows():
        crit, warn = [], []

        for f in CRITICAL_FIELDS:
            if is_missing(row.get(f)):
                crit.append(f"Missing {FIELD_LABELS[f]}")

        for f in IMPORTANT_FIELDS:
            if is_missing(row.get(f)):
                warn.append(f"Missing {FIELD_LABELS[f]}")

        if not is_missing(row.get("request_id")) and row["request_id"] in dup_set:
            crit.append("Duplicate Request ID")

        dt_val = row.get("data_type")
        if not is_missing(dt_val) and str(dt_val).lower() not in VALID_DATA_TYPES:
            warn.append(f"Unrecognized Data Type: “{dt_val}”")

        if row.get("retention_schedule") == "No":
            crit.append("No retention schedule in place — needs review before purge")

        if not is_missing(row.get("proposed_purge_date")) and pd.isna(row.get("proposed_purge_dt")):
            crit.append(f"Unparseable Proposed Purge Date: “{row['proposed_purge_date']}” — need a real date")
        elif pd.notna(row.get("proposed_purge_dt")) and row["proposed_purge_dt"] < today:
            status = str(row.get("status") or "").lower()
            if not any(k in status for k in ("complete", "purged", "done", "closed")):
                crit.append(f"Proposed purge date has passed ({row['proposed_purge_dt'].date()}) and request is not marked complete")

        if not is_missing(row.get("num_records")) and pd.isna(row.get("num_records_n")):
            warn.append(f"Unparseable record count: “{row['num_records']}”")

        critical_issues.append(crit)
        warning_issues.append(warn)

    df = df.copy()
    df["dq_critical"] = critical_issues
    df["dq_warnings"] = warning_issues
    df["dq_severity"] = [
        "Critical" if c else ("Warning" if w else "Clean")
        for c, w in zip(critical_issues, warning_issues)
    ]
    return df


def build_followups(df: pd.DataFrame) -> list[dict]:
    """Group problem rows by who we chase: owner if known, else department, else source file."""
    problems = df[df["dq_severity"] != "Clean"]
    groups = {}
    for _, row in problems.iterrows():
        owner = row.get("record_owner")
        dept = row.get("department")
        if not is_missing(owner):
            key, contact_type = str(owner), "Record Owner"
        elif not is_missing(dept):
            key, contact_type = f"{dept} (no owner listed)", "Department"
        else:
            key, contact_type = f"{row['source_file']} (no owner or department)", "Source file"

        g = groups.setdefault(key, {
            "contact": key, "contact_type": contact_type,
            "department": None if is_missing(dept) else str(dept),
            "requests": [], "critical_count": 0, "warning_count": 0,
        })
        g["requests"].append({
            "request_id": "—" if is_missing(row.get("request_id")) else str(row["request_id"]),
            "application": "—" if is_missing(row.get("application")) else str(row["application"]),
            "source": f"{row['source_file']} › {row['source_sheet']}",
            "critical": row["dq_critical"],
            "warnings": row["dq_warnings"],
        })
        g["critical_count"] += len(row["dq_critical"])
        g["warning_count"] += len(row["dq_warnings"])

    return sorted(groups.values(), key=lambda g: (-g["critical_count"], -g["warning_count"]))


# ----------------------------------------------------------------------------
# 5. STATISTICS
# ----------------------------------------------------------------------------

def value_counts(df, col, top=12):
    s = df[col].dropna()
    vc = s.value_counts().head(top)
    return [(str(k), int(v)) for k, v in vc.items()]


def build_stats(df: pd.DataFrame, today: pd.Timestamp) -> dict:
    total = len(df)
    clean_ct = int((df["dq_severity"] == "Clean").sum())
    warn_ct = int((df["dq_severity"] == "Warning").sum())
    crit_ct = int((df["dq_severity"] == "Critical").sum())

    rs = df["retention_schedule"]
    rs_yes, rs_no, rs_blank = int((rs == "Yes").sum()), int((rs == "No").sum()), int(rs.isna().sum())

    total_records = df["num_records_n"].dropna().sum()
    total_gb = df["data_size_gb"].dropna().sum()

    overdue = int(((df["proposed_purge_dt"].notna()) & (df["proposed_purge_dt"] < today)
                   & ~df["status"].fillna("").str.lower().str.contains("complete|purged|done|closed", regex=True)).sum())
    next_90 = int(((df["proposed_purge_dt"].notna()) & (df["proposed_purge_dt"] >= today)
                   & (df["proposed_purge_dt"] <= today + pd.Timedelta(days=90))).sum())

    months = df["proposed_purge_dt"].dropna().dt.to_period("M").astype(str).value_counts().sort_index()
    timeline = [(m, int(c)) for m, c in months.items()]

    # Field completeness across the canonical schema
    completeness = []
    for f in CRITICAL_FIELDS + IMPORTANT_FIELDS:
        filled = int(df[f].map(lambda v: not is_missing(v)).sum())
        completeness.append({"field": FIELD_LABELS[f], "filled": filled, "total": total,
                             "pct": round(100 * filled / total) if total else 0,
                             "critical": f in CRITICAL_FIELDS})
    completeness.sort(key=lambda x: x["pct"])

    return {
        "total": total, "clean": clean_ct, "warning": warn_ct, "critical": crit_ct,
        "rs_yes": rs_yes, "rs_no": rs_no, "rs_blank": rs_blank,
        "total_records": total_records, "total_gb": total_gb,
        "overdue": overdue, "next_90": next_90,
        "by_department": value_counts(df, "department"),
        "by_data_type": value_counts(df, "data_type"),
        "by_application": value_counts(df, "application"),
        "by_reason": value_counts(df, "reason_for_purge", top=8),
        "timeline": timeline,
        "completeness": completeness,
    }


# ----------------------------------------------------------------------------
# 6. HTML REPORT
# ----------------------------------------------------------------------------

def esc(v):
    return html.escape("" if v is None else str(v))


def fmt_int(n):
    return f"{int(n):,}" if n else "0"


def fmt_gb(g):
    if not g:
        return "0 GB"
    if g >= 1024:
        return f"{g/1024:,.1f} TB"
    return f"{g:,.1f} GB"


def hbar_rows(pairs, color_class="bar-ink"):
    if not pairs:
        return '<p class="empty">Nothing recorded yet.</p>'
    mx = max(v for _, v in pairs) or 1
    rows = []
    for label, v in pairs:
        pct = max(3, round(100 * v / mx))
        rows.append(
            f'<div class="hrow"><div class="hlabel" title="{esc(label)}">{esc(label)}</div>'
            f'<div class="htrack"><div class="hfill {color_class}" style="width:{pct}%"></div></div>'
            f'<div class="hval">{v}</div></div>'
        )
    return "".join(rows)


def render_html(stats, followups, df, file_log, today) -> str:
    n_files = len({e["file"] for e in file_log if e["error"] is None})
    n_sheets = sum(1 for e in file_log if e["error"] is None)
    errors = [e for e in file_log if e["error"]]

    # --- follow-up section ---
    fu_html = []
    for g in followups:
        req_rows = []
        for r in g["requests"]:
            issues = "".join(f'<li class="iss-crit">{esc(i)}</li>' for i in r["critical"])
            issues += "".join(f'<li class="iss-warn">{esc(i)}</li>' for i in r["warnings"])
            req_rows.append(
                f'<tr><td class="mono">{esc(r["request_id"])}</td><td>{esc(r["application"])}</td>'
                f'<td class="src">{esc(r["source"])}</td><td><ul class="isslist">{issues}</ul></td></tr>'
            )
        badge = (f'<span class="pill pill-crit">{g["critical_count"]} critical</span>' if g["critical_count"] else "") + \
                (f'<span class="pill pill-warn">{g["warning_count"]} to verify</span>' if g["warning_count"] else "")
        dept = f' · {esc(g["department"])}' if g["department"] and g["contact_type"] == "Record Owner" else ""
        fu_html.append(
            f'<details class="fu" {"open" if g["critical_count"] else ""}>'
            f'<summary><span class="fu-name">{esc(g["contact"])}</span>'
            f'<span class="fu-meta">{esc(g["contact_type"])}{dept} · {len(g["requests"])} request(s)</span>{badge}</summary>'
            f'<table class="fu-table"><thead><tr><th>Request</th><th>Application</th><th>Source</th><th>What to chase</th></tr></thead>'
            f'<tbody>{"".join(req_rows)}</tbody></table></details>'
        )
    fu_block = "".join(fu_html) if fu_html else '<p class="allclear">Every request passed all checks. Nothing to chase.</p>'

    # --- completeness table ---
    comp_rows = []
    for c in stats["completeness"]:
        cls = "comp-bad" if c["pct"] < 70 else ("comp-mid" if c["pct"] < 95 else "comp-ok")
        req = " •" if c["critical"] else ""
        comp_rows.append(
            f'<div class="hrow"><div class="hlabel">{esc(c["field"])}{req}</div>'
            f'<div class="htrack"><div class="hfill {cls}" style="width:{max(2,c["pct"])}%"></div></div>'
            f'<div class="hval">{c["pct"]}%</div></div>'
        )

    # --- timeline ---
    tl = stats["timeline"]
    if tl:
        mx = max(v for _, v in tl) or 1
        tl_cols = "".join(
            f'<div class="tcol"><div class="tbar" style="height:{max(4, round(100*v/mx))}%"></div>'
            f'<div class="tnum">{v}</div><div class="tlab">{esc(m)}</div></div>'
            for m, v in tl
        )
        timeline_html = f'<div class="timeline">{tl_cols}</div>'
    else:
        timeline_html = '<p class="empty">No parseable purge dates yet.</p>'

    # --- full register ---
    reg_rows = []
    show_cols = ["request_id", "record_owner", "department", "application", "data_type",
                 "retention_schedule", "reason_for_purge", "num_records", "data_size", "proposed_purge_date"]
    for _, row in df.iterrows():
        sev = row["dq_severity"]
        cells = "".join(f"<td>{esc('—' if is_missing(row.get(c)) else row.get(c))}</td>" for c in show_cols)
        reg_rows.append(
            f'<tr class="sev-{sev.lower()}" data-sev="{sev}"><td><span class="dot dot-{sev.lower()}"></span>{sev}</td>'
            f'{cells}<td class="src">{esc(row["source_file"])}</td></tr>'
        )

    err_html = ""
    if errors:
        li = "".join(f'<li><strong>{esc(e["file"])}</strong> — {esc(e["error"])}</li>' for e in errors)
        err_html = f'<div class="ferr"><strong>Files that could not be read:</strong><ul>{li}</ul></div>'

    file_rows = "".join(
        f'<tr><td>{esc(e["file"])}</td><td>{esc(e["sheet"])}</td><td class="num">{e["rows"]}</td>'
        f'<td class="src">{esc(", ".join(e["unmapped"]) or "—")}</td></tr>'
        for e in file_log if e["error"] is None
    )

    rs_total = stats["rs_yes"] + stats["rs_no"] + stats["rs_blank"]
    rs_pct = round(100 * stats["rs_yes"] / rs_total) if rs_total else 0

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Purge Request Register — {today.date()}</title>
<style>
  :root {{
    --ink:#1C2B33; --paper:#F6F5F1; --panel:#FFFFFF; --line:#D8D5CC;
    --slate:#5E6B72; --ok:#2F6B4F; --warn:#9A6A12; --crit:#8C2F23; --accent:#24505E;
  }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ background:var(--paper); color:var(--ink); font:15px/1.5 "Segoe UI", system-ui, -apple-system, sans-serif; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:34px 28px 80px; }}
  h1,h2,h3,summary .fu-name {{ font-family: Georgia, "Times New Roman", serif; }}
  header {{ border-bottom:3px double var(--ink); padding-bottom:18px; margin-bottom:26px; }}
  header h1 {{ font-size:30px; font-weight:600; letter-spacing:.2px; }}
  header .sub {{ color:var(--slate); margin-top:6px; }}
  .band {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin:22px 0 30px; }}
  .stat {{ background:var(--panel); border:1px solid var(--line); border-top:3px solid var(--accent); padding:14px 16px; }}
  .stat.crit {{ border-top-color:var(--crit); }} .stat.warn {{ border-top-color:var(--warn); }} .stat.ok {{ border-top-color:var(--ok); }}
  .stat .n {{ font-size:26px; font-weight:600; font-family:Georgia, serif; }}
  .stat .l {{ color:var(--slate); font-size:13px; margin-top:2px; }}
  section {{ margin-bottom:38px; }}
  h2 {{ font-size:21px; font-weight:600; border-bottom:1px solid var(--line); padding-bottom:8px; margin-bottom:16px; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:26px; }}
  @media (max-width:820px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  .card {{ background:var(--panel); border:1px solid var(--line); padding:18px 20px; }}
  .card h3 {{ font-size:16px; margin-bottom:14px; }}
  .hrow {{ display:grid; grid-template-columns:180px 1fr 44px; gap:10px; align-items:center; margin-bottom:8px; }}
  .hlabel {{ font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .htrack {{ background:#ECEAE3; height:14px; }}
  .hfill {{ height:100%; }}
  .bar-ink {{ background:var(--accent); }} .bar-type {{ background:#3E6B5A; }} .bar-app {{ background:#6B5A3E; }}
  .comp-ok {{ background:var(--ok); }} .comp-mid {{ background:var(--warn); }} .comp-bad {{ background:var(--crit); }}
  .hval {{ font-size:13px; text-align:right; color:var(--slate); font-variant-numeric:tabular-nums; }}
  .timeline {{ display:flex; gap:10px; align-items:flex-end; height:150px; padding-top:10px; overflow-x:auto; }}
  .tcol {{ flex:1; min-width:52px; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; height:100%; }}
  .tbar {{ width:70%; background:var(--accent); }}
  .tnum {{ font-size:12px; color:var(--slate); margin-top:4px; }}
  .tlab {{ font-size:11px; color:var(--slate); }}
  .fu {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--crit); margin-bottom:12px; }}
  .fu summary {{ cursor:pointer; padding:13px 16px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
  .fu-name {{ font-size:17px; font-weight:600; }}
  .fu-meta {{ color:var(--slate); font-size:13px; }}
  .pill {{ font-size:12px; padding:2px 9px; border-radius:10px; color:#fff; }}
  .pill-crit {{ background:var(--crit); }} .pill-warn {{ background:var(--warn); }}
  .fu-table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
  .fu-table th {{ text-align:left; padding:8px 14px; border-top:1px solid var(--line); border-bottom:1px solid var(--line); background:#FBFAF7; font-weight:600; }}
  .fu-table td {{ padding:9px 14px; border-bottom:1px solid #EDEBE4; vertical-align:top; }}
  .isslist {{ margin:0; padding-left:18px; }}
  .iss-crit {{ color:var(--crit); }} .iss-warn {{ color:var(--warn); }}
  .mono {{ font-variant-numeric:tabular-nums; }}
  .src {{ color:var(--slate); font-size:12.5px; }}
  .allclear {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--ok); padding:16px; }}
  .register {{ width:100%; border-collapse:collapse; font-size:13px; background:var(--panel); border:1px solid var(--line); }}
  .register th {{ position:sticky; top:0; background:var(--ink); color:#F6F5F1; text-align:left; padding:9px 10px; font-weight:600; }}
  .register td {{ padding:8px 10px; border-bottom:1px solid #EDEBE4; vertical-align:top; }}
  .dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; }}
  .dot-critical {{ background:var(--crit); }} .dot-warning {{ background:var(--warn); }} .dot-clean {{ background:var(--ok); }}
  .filters {{ margin-bottom:12px; display:flex; gap:8px; }}
  .filters button {{ border:1px solid var(--line); background:var(--panel); padding:6px 14px; cursor:pointer; font:inherit; font-size:13px; }}
  .filters button.active {{ background:var(--ink); color:#fff; border-color:var(--ink); }}
  .regwrap {{ max-height:520px; overflow:auto; border:1px solid var(--line); }}
  .ferr {{ background:#FBEEE9; border:1px solid var(--crit); padding:12px 16px; margin-bottom:14px; font-size:13.5px; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .empty {{ color:var(--slate); font-style:italic; }}
  .footnote {{ color:var(--slate); font-size:12.5px; margin-top:6px; }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>Purge Request Register</h1>
  <div class="sub">Data Retention &amp; Disposition · generated {today.strftime('%B %d, %Y')} ·
  {n_files} file(s), {n_sheets} sheet(s) read</div>
</header>

{err_html}

<div class="band">
  <div class="stat"><div class="n">{stats['total']}</div><div class="l">Purge requests</div></div>
  <div class="stat crit"><div class="n">{stats['critical']}</div><div class="l">With critical issues</div></div>
  <div class="stat warn"><div class="n">{stats['warning']}</div><div class="l">With items to verify</div></div>
  <div class="stat ok"><div class="n">{stats['clean']}</div><div class="l">Complete &amp; clean</div></div>
  <div class="stat"><div class="n">{fmt_int(stats['total_records'])}</div><div class="l">Records slated for purge</div></div>
  <div class="stat"><div class="n">{fmt_gb(stats['total_gb'])}</div><div class="l">Data volume slated</div></div>
  <div class="stat crit"><div class="n">{stats['overdue']}</div><div class="l">Past proposed date, not complete</div></div>
  <div class="stat"><div class="n">{stats['next_90']}</div><div class="l">Purges due in next 90 days</div></div>
</div>

<section>
  <h2>Who to follow up with</h2>
  <p class="footnote" style="margin-bottom:14px">Grouped by record owner where one is listed; otherwise by department, then by source file. Owners with critical gaps are expanded.</p>
  {fu_block}
</section>

<section>
  <h2>Retention schedule coverage</h2>
  <div class="card">
    <div class="hrow"><div class="hlabel">Schedule in place — Yes</div><div class="htrack"><div class="hfill comp-ok" style="width:{max(2, round(100*stats['rs_yes']/max(rs_total,1)))}%"></div></div><div class="hval">{stats['rs_yes']}</div></div>
    <div class="hrow"><div class="hlabel">Schedule in place — No</div><div class="htrack"><div class="hfill comp-bad" style="width:{max(2, round(100*stats['rs_no']/max(rs_total,1)))}%"></div></div><div class="hval">{stats['rs_no']}</div></div>
    <div class="hrow"><div class="hlabel">Not answered</div><div class="htrack"><div class="hfill comp-mid" style="width:{max(2, round(100*stats['rs_blank']/max(rs_total,1)))}%"></div></div><div class="hval">{stats['rs_blank']}</div></div>
    <p class="footnote">{rs_pct}% of requests confirm a retention schedule is in place. Requests answering “No” are flagged as critical above — a purge without an approved schedule needs governance review first.</p>
  </div>
</section>

<section class="grid2">
  <div class="card"><h3>Requests by department</h3>{hbar_rows(stats['by_department'], 'bar-ink')}</div>
  <div class="card"><h3>Requests by data type</h3>{hbar_rows(stats['by_data_type'], 'bar-type')}</div>
  <div class="card"><h3>Requests by application system</h3>{hbar_rows(stats['by_application'], 'bar-app')}</div>
  <div class="card"><h3>Reasons for purge</h3>{hbar_rows(stats['by_reason'], 'bar-ink')}</div>
</section>

<section>
  <h2>Proposed purge timeline</h2>
  <div class="card">{timeline_html}</div>
</section>

<section>
  <h2>Field completeness</h2>
  <div class="card">
    {''.join(comp_rows)}
    <p class="footnote">• marks fields required for a request to be considered complete.</p>
  </div>
</section>

<section>
  <h2>Full register</h2>
  <div class="filters">
    <button class="active" onclick="filt('All',this)">All ({stats['total']})</button>
    <button onclick="filt('Critical',this)">Critical ({stats['critical']})</button>
    <button onclick="filt('Warning',this)">To verify ({stats['warning']})</button>
    <button onclick="filt('Clean',this)">Clean ({stats['clean']})</button>
  </div>
  <div class="regwrap">
  <table class="register" id="reg">
    <thead><tr><th>Check</th><th>Request ID</th><th>Owner</th><th>Department</th><th>Application</th>
    <th>Data Type</th><th>Ret. Sched.</th><th>Reason</th><th># Records</th><th>Size</th><th>Purge Date</th><th>Source</th></tr></thead>
    <tbody>{''.join(reg_rows)}</tbody>
  </table>
  </div>
</section>

<section>
  <h2>Files read</h2>
  <div class="regwrap" style="max-height:260px">
  <table class="register">
    <thead><tr><th>File</th><th>Sheet</th><th>Rows</th><th>Columns not recognized (add aliases in script if needed)</th></tr></thead>
    <tbody>{file_rows}</tbody>
  </table>
  </div>
</section>

</div>
<script>
function filt(sev, btn) {{
  document.querySelectorAll('.filters button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('#reg tbody tr').forEach(tr => {{
    tr.style.display = (sev === 'All' || tr.dataset.sev === sev) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


# ----------------------------------------------------------------------------
# 7. MAIN
# ----------------------------------------------------------------------------

def browse_for_folder() -> str | None:
    """Open a native folder-picker dialog and return the chosen path (or None if cancelled)."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(title="Select folder containing purge request spreadsheets")
    root.destroy()
    return path or None


def main():
    ap = argparse.ArgumentParser(description="Analyze a folder of purge-request spreadsheets and build an HTML dashboard.")
    ap.add_argument("folder", nargs="?", default=None,
                     help="Folder containing the purge request .xlsx/.csv files (omit to pick via a browse dialog)")
    ap.add_argument("-o", "--output", default="purge_dashboard.html", help="Output HTML file (default: purge_dashboard.html)")
    ap.add_argument("--as-of", default=None, help="Override 'today' for overdue checks, e.g. 2026-08-31")
    args = ap.parse_args()

    if args.folder:
        folder = Path(args.folder).expanduser()
    else:
        chosen = browse_for_folder()
        if not chosen:
            print("No folder selected.", file=sys.stderr)
            sys.exit(1)
        folder = Path(chosen)

    if not folder.is_dir():
        print(f"Not a folder: {folder}", file=sys.stderr)
        sys.exit(1)

    today = pd.Timestamp(args.as_of).normalize() if args.as_of else pd.Timestamp.today().normalize()

    print(f"Reading spreadsheets from {folder} ...")
    combined, file_log = read_folder(folder)
    print(f"  {len(combined)} rows from {len({e['file'] for e in file_log if not e['error']})} file(s).")

    df = clean(combined)
    df = run_dq(df, today)
    followups = build_followups(df)
    stats = build_stats(df, today)

    out = Path(args.output)
    out.write_text(render_html(stats, followups, df, file_log, today), encoding="utf-8")

    print(f"\n  Requests: {stats['total']}  |  Critical: {stats['critical']}  |  "
          f"To verify: {stats['warning']}  |  Clean: {stats['clean']}")
    print(f"  Follow-ups needed with {len(followups)} owner(s)/group(s).")
    print(f"\nDashboard written to {out.resolve()}")


if __name__ == "__main__":
    main()
