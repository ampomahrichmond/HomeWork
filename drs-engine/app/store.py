"""SQLite persistence: issuances register, reviewer feedback (training data), approved new activities."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS issuances (
  id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT, status TEXT, title TEXT, data_owner TEXT,
  business_unit TEXT, final_level TEXT, coverage TEXT, confidence INTEGER, payload TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, issuance_id TEXT, created_at TEXT, action TEXT,
  text TEXT, activity_id TEXT, level TEXT, reviewer TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS custom_activities (
  id TEXT PRIMARY KEY, created_at TEXT, category_id TEXT, category TEXT, name TEXT, level TEXT,
  definition TEXT, trigger_event TEXT, keywords TEXT, source_issuance TEXT, approved_by TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()
        with self._c() as c:
            c.executescript(SCHEMA)

    def _c(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    # ---------------------------------------------------------- issuances
    def next_id(self) -> str:
        year = datetime.now().year
        with self._c() as c:
            n = c.execute("SELECT COUNT(*) FROM issuances WHERE id LIKE ?", (f"DRS-{year}-%",)).fetchone()[0]
        return f"DRS-{year}-{n + 1:05d}"

    def save_issuance(self, det: dict, status: str = "Draft") -> dict:
        with self.lock:
            iid = det.get("issuance_id") or self.next_id()
            ts = now()
            det.setdefault("issued_at", ts)
            det["issuance_id"], det["status"], det["updated_at"] = iid, det.get("status", status), ts
            req = det["request"]
            with self._c() as c:
                c.execute("""INSERT OR REPLACE INTO issuances
                    (id, created_at, updated_at, status, title, data_owner, business_unit, final_level, coverage,
                     confidence, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                          (iid, det["issued_at"], ts, det["status"], req.get("title", ""), req.get("data_owner", ""),
                           req.get("business_unit", ""), det["final_level"], det["coverage"], det["confidence"],
                           json.dumps(det)))
        return det

    def get(self, iid: str) -> dict | None:
        with self._c() as c:
            r = c.execute("SELECT payload FROM issuances WHERE id=?", (iid,)).fetchone()
        return json.loads(r["payload"]) if r else None

    def list(self, q: str = "", status: str = "") -> list[dict]:
        sql, args = "SELECT * FROM issuances WHERE 1=1", []
        if q:
            sql += " AND (title LIKE ? OR id LIKE ? OR data_owner LIKE ? OR business_unit LIKE ?)"
            args += [f"%{q}%"] * 4
        if status:
            sql += " AND status LIKE ?"
            args.append(f"{status}%")
        sql += " ORDER BY created_at DESC"
        with self._c() as c:
            rows = c.execute(sql, args).fetchall()
        out = []
        for r in rows:
            p = json.loads(r["payload"])
            out.append({"id": r["id"], "created_at": r["created_at"], "status": r["status"], "title": r["title"],
                        "data_owner": r["data_owner"], "business_unit": r["business_unit"],
                        "final_level": r["final_level"], "coverage": r["coverage"], "confidence": r["confidence"],
                        "activity": p["governing"]["activity"], "category": p["governing"]["category"],
                        "retention": p["final_level_label"], "review_required": p.get("review_required")})
        return out

    def delete(self, iid: str) -> None:
        with self._c() as c:
            c.execute("DELETE FROM issuances WHERE id=?", (iid,))

    # ------------------------------------------------------------ feedback
    def add_feedback(self, issuance_id, action, text, activity_id, level, reviewer, notes):
        with self._c() as c:
            c.execute("""INSERT INTO feedback (issuance_id, created_at, action, text, activity_id, level, reviewer, notes)
                         VALUES (?,?,?,?,?,?,?,?)""", (issuance_id, now(), action, text, activity_id, level, reviewer, notes))

    def training_examples(self) -> list[dict]:
        with self._c() as c:
            rows = c.execute("SELECT text, activity_id FROM feedback WHERE activity_id IS NOT NULL").fetchall()
        return [dict(r) for r in rows]

    def feedback_count(self) -> int:
        with self._c() as c:
            return c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]

    # --------------------------------------------------- custom activities
    def add_custom_activity(self, rec: dict) -> dict:
        with self._c() as c:
            n = c.execute("SELECT COUNT(*) FROM custom_activities WHERE category_id=?", (rec["category_id"],)).fetchone()[0]
            rec["id"] = f"{rec['category_id']}.X{n + 1}"
            c.execute("""INSERT INTO custom_activities (id, created_at, category_id, category, name, level, definition,
                         trigger_event, keywords, source_issuance, approved_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (rec["id"], now(), rec["category_id"], rec["category"], rec["name"], rec["level"],
                       rec["definition"], rec["trigger_event"], json.dumps(rec.get("keywords", [])),
                       rec.get("source_issuance"), rec.get("approved_by")))
        return rec

    def custom_activities(self) -> list[dict]:
        with self._c() as c:
            rows = c.execute("SELECT * FROM custom_activities ORDER BY id").fetchall()
        return [{**dict(r), "keywords": json.loads(r["keywords"] or "[]")} for r in rows]

    # --------------------------------------------------------------- stats
    def stats(self) -> dict:
        with self._c() as c:
            total = c.execute("SELECT COUNT(*) FROM issuances").fetchone()[0]
            by_level = {r[0]: r[1] for r in c.execute("SELECT final_level, COUNT(*) FROM issuances GROUP BY final_level")}
            by_cov = {r[0]: r[1] for r in c.execute("SELECT coverage, COUNT(*) FROM issuances GROUP BY coverage")}
            by_status = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM issuances GROUP BY status")}
            avg = c.execute("SELECT AVG(confidence) FROM issuances").fetchone()[0]
        return {"total": total, "by_level": by_level, "by_coverage": by_cov, "by_status": by_status,
                "avg_confidence": round(avg or 0), "feedback": self.feedback_count(),
                "custom_activities": len(self.custom_activities())}
