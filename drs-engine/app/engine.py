"""
Retention determination engine.

How a determination is made
---------------------------
1. Text understanding - the request (title, description, components) is scored against
   every business activity using three signals:
     * keyword/phrase evidence from a curated domain vocabulary per activity
     * TF-IDF similarity (word + character n-grams) to the activity profile
     * nearest-neighbour similarity to labelled examples (seed + reviewer decisions),
       so the engine learns from every approval / override
   plus small priors from structured inputs (asset type, client/employee data flags).
2. Decomposition - data products and multi-source datasets are split into components;
   each component is classified on its own.
3. Precedence - a commingled asset inherits the longest retention of its components
   (levels are ordered I < II < III < IV < V < VI).
4. Regulatory floor test - an external knowledge base of regulatory minimums is matched
   against the request; if the schedule level does not meet a floor, the level is uplifted.
5. Coverage - strong matches are "Covered"; weak matches are "Inferred" (review);
   no match produces a proposed new business activity for DRD approval.
6. Optional LLM second opinion (local Ollama or Anthropic API) is blended in.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---- thresholds (tuned on the seed scenarios; adjust in one place) ----
HIGH = 0.43       # strong match -> covered
LOW = 0.27        # below this -> not covered by the schedule
COMPONENT_MIN = 0.24
SENTENCE_MULTI = 0.50  # a single sentence must be this strong to add a second activity

ASSET_PRIORS = {
    "Communication": {"2.1": 0.06, "2.2": 0.04, "2.3": 0.04},
    "Report / Dashboard": {"5.1": 0.06, "8.1": 0.03},
    "Application / System": {"4.3": 0.05},
    "Contract / Agreement": {"4.2": 0.05, "4.1": 0.03, "7.1": 0.03},
    "Policy / Procedure": {"9.3": 0.06},
    "Regulatory Filing": {"8.1": 0.07},
    "Legal Matter": {"6.1": 0.08},
}
STOP = {"data", "record", "records", "information", "system", "file", "files", "the", "and", "for", "of"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\n+|\s*[••]\s*|\s+-\s+", text or "")
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 12]


def _split_fragments(text: str) -> list[str]:
    """Break list-style descriptions ("joins A, B and C") into candidate source fragments."""
    frags = []
    for sent in _split_sentences(text) or [text]:
        for f in re.split(r",|;|\band\b|\bplus\b|\bas well as\b|\balong with\b|\bcombined with\b|\bjoined with\b", sent):
            f = f.strip(" .")
            if len(f.split()) >= 2:
                frags.append(f)
    return frags


@dataclass
class Activity:
    id: str
    name: str
    level: str
    definition: str
    trigger_event: str
    keywords: list[str]
    category_id: str
    category: str
    custom: bool = False
    patterns: list[tuple[re.Pattern, float, str]] = field(default_factory=list)

    def profile(self) -> str:
        return " ".join([self.name, self.category, self.definition, " ".join(self.keywords)])


class RetentionEngine:
    def __init__(self, data_dir: Path, store=None, llm=None):
        self.data_dir = Path(data_dir)
        self.store = store
        self.llm = llm
        self.schedule = json.loads((self.data_dir / "schedule.json").read_text())
        self.knowledge = json.loads((self.data_dir / "regulatory_knowledge.json").read_text())
        self.seed = json.loads((self.data_dir / "seed_examples.json").read_text())["examples"]
        self.levels = self.schedule["levels"]
        self.fit()

    # ------------------------------------------------------------------ model
    def fit(self) -> None:
        acts: list[Activity] = []
        for cat in self.schedule["categories"]:
            for a in cat["activities"]:
                acts.append(Activity(a["id"], a["name"], a["level"], a["definition"], a["trigger_event"],
                                     a["keywords"], cat["id"], cat["name"]))
        if self.store:
            for c in self.store.custom_activities():
                acts.append(Activity(c["id"], c["name"], c["level"], c["definition"], c["trigger_event"],
                                     c.get("keywords", []), c["category_id"], c["category"], custom=True))
        for a in acts:
            a.patterns = []
            for kw in a.keywords:
                kw_l = kw.lower()
                w = 1.0 + 0.6 * (len(kw_l.split()) - 1)
                a.patterns.append((re.compile(r"(?<![a-z0-9])" + re.escape(kw_l) + r"(?![a-z0-9])"), w, kw))
        self.activities = acts
        self.by_id = {a.id: a for a in acts}

        examples = [(e["text"], e["activity_id"]) for e in self.seed]
        if self.store:
            examples += [(e["text"], e["activity_id"]) for e in self.store.training_examples()]
        examples = [(t, aid) for t, aid in examples if aid in self.by_id]
        self.example_texts = [t for t, _ in examples]
        self.example_labels = [aid for _, aid in examples]

        corpus = [a.profile() for a in acts] + self.example_texts
        self.wv = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1)
        self.cv = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
        self.wv.fit(corpus)
        self.cv.fit(corpus)
        profiles = [a.profile() for a in acts]
        self.P = (self.wv.transform(profiles), self.cv.transform(profiles))
        self.E = (self.wv.transform(self.example_texts), self.cv.transform(self.example_texts)) if examples else None

    # ---------------------------------------------------------------- scoring
    def score_text(self, text: str, priors: dict[str, float] | None = None) -> list[dict]:
        t = _norm(text).lower()
        if not t:
            return []
        qw, qc = self.wv.transform([t]), self.cv.transform([t])
        tf = 0.55 * cosine_similarity(qw, self.P[0])[0] + 0.45 * cosine_similarity(qc, self.P[1])[0]
        knn = {a.id: 0.0 for a in self.activities}
        if self.E is not None:
            sims = 0.55 * cosine_similarity(qw, self.E[0])[0] + 0.45 * cosine_similarity(qc, self.E[1])[0]
            for s, lab in zip(sims, self.example_labels):
                knn[lab] = max(knn[lab], float(s))
        out = []
        for i, a in enumerate(self.activities):
            hits, matched = 0.0, []
            for pat, w, kw in a.patterns:
                if pat.search(t):
                    hits += w
                    matched.append(kw)
            kw_score = 1 - math.exp(-0.55 * hits)
            tf_n = min(1.0, float(tf[i]) / 0.32)
            knn_n = min(1.0, knn[a.id] / 0.55)
            score = 0.42 * kw_score + 0.26 * tf_n + 0.32 * knn_n
            score += (priors or {}).get(a.id, 0.0)
            out.append({
                "activity_id": a.id, "score": round(min(score, 1.0), 4),
                "signals": {"keywords": round(kw_score, 3), "similarity": round(tf_n, 3), "examples": round(knn_n, 3)},
                "matched_keywords": matched[:8],
            })
        out.sort(key=lambda r: r["score"], reverse=True)
        return out

    # ------------------------------------------------------------- utilities
    def level_rank(self, lvl: str) -> int:
        return self.levels[lvl]["rank"]

    def satisfies(self, lvl: str, floor: dict) -> bool:
        L = self.levels[lvl]
        if L["trigger"] == "permanent":
            return True
        if floor["trigger"] == "permanent":
            return False
        if floor["trigger"] == "event":
            return L["trigger"] == "event" and L["years"] >= floor["years"]
        return L["years"] >= floor["years"]

    def min_level_for(self, floor: dict) -> str:
        for lvl in sorted(self.levels, key=self.level_rank):
            if self.satisfies(lvl, floor):
                return lvl
        return "VI"

    def activity_view(self, aid: str) -> dict:
        a = self.by_id[aid]
        L = self.levels[a.level]
        return {"activity_id": a.id, "activity": a.name, "category_id": a.category_id, "category": a.category,
                "level": a.level, "level_label": L["label"], "years": L["years"], "trigger": L["trigger"],
                "trigger_event": a.trigger_event, "definition": a.definition, "custom": a.custom}

    def retention_statement(self, lvl: str, trigger_event: str) -> str:
        L = self.levels[lvl]
        if L["trigger"] == "permanent":
            return "Retain permanently for the life of the organization (and any successor)."
        if L["trigger"] == "event":
            return f"Retain for {L['years']} years after the triggering event ({trigger_event.lower()}), then dispose."
        return f"Retain for {L['years']} years from the date of creation, then dispose."

    def match_regulations(self, text: str, jurisdictions: list[str], governing_cat: str | None) -> list[dict]:
        t = text.lower()
        juris = set(jurisdictions or ["US"])
        out = []
        for r in self.knowledge["rules"]:
            rj = set(r["jurisdiction"].split("/"))
            if not (rj & juris):
                continue
            hits = [k for k in r["applies_when"] if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t)]
            forced = r["id"] == "CIRO-BR" and "CA" in juris and governing_cat in {"1", "2", "5", "8", "9"}
            if hits or forced:
                out.append({**r, "matched_on": hits or ["Canadian jurisdiction"]})
        return out

    # ------------------------------------------------------------- determine
    def determine(self, req: dict) -> dict:
        title = _norm(req.get("title", ""))
        desc = _norm(req.get("description", ""))
        components = [c.strip() for c in (req.get("components") or []) if c and c.strip()]
        asset_type = req.get("asset_type") or "Dataset"
        flags = {k: bool(req.get(k)) for k in ("client_data", "employee_data", "pii", "legal_hold")}
        record_copy = req.get("record_copy") or "Official record"
        jurisdictions = req.get("jurisdictions") or ["US"]
        full_text = " ".join([title, desc] + components)

        priors = dict(ASSET_PRIORS.get(asset_type, {}))
        if flags["client_data"]:
            for aid in ("1.1", "2.1", "9.1"):
                priors[aid] = priors.get(aid, 0) + 0.03
        if flags["employee_data"]:
            for aid in ("10.1", "10.2", "9.2"):
                priors[aid] = priors.get(aid, 0) + 0.03

        whole = self.score_text(f"{title}. {desc}. " + ". ".join(components), priors)
        top = whole[0]
        rationale: list[str] = []
        is_product = asset_type in ("Data Product", "Dataset") or bool(components)

        # ---- component / segment decomposition
        comp_results = []
        seg_sources = [("Component", c) for c in components]
        if is_product and not components:
            sents = _split_sentences(desc)
            frags = _split_fragments(desc) if asset_type == "Data Product" else []
            seen = set()
            for s in (sents if len(sents) > 1 else []) + frags:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    seg_sources.append(("Segment", s))
        for kind, seg in seg_sources:
            sc = self.score_text(seg, priors)
            if not sc:
                continue
            best = sc[0]
            min_needed = COMPONENT_MIN if kind == "Component" else SENTENCE_MULTI
            comp_results.append({
                "kind": kind, "text": seg, "matched": best["score"] >= min_needed,
                "score": best["score"], "matched_keywords": best["matched_keywords"],
                **self.activity_view(best["activity_id"]),
            })

        candidates: dict[str, float] = {}
        if top["score"] >= LOW:
            candidates[top["activity_id"]] = top["score"]
        for c in comp_results:
            if c["matched"]:
                candidates[c["activity_id"]] = max(candidates.get(c["activity_id"], 0), c["score"])
        if is_product and len(whole) > 1:
            for alt in whole[1:4]:
                ratio = 0.68 if asset_type == "Data Product" else 0.88
                if alt["score"] >= max(HIGH, ratio * top["score"]):
                    candidates[alt["activity_id"]] = max(candidates.get(alt["activity_id"], 0), alt["score"])

        # ---- optional LLM second opinion
        llm_view = None
        if self.llm and self.llm.enabled and req.get("use_llm", True):
            llm_view = self.llm.classify(req, self)
            if llm_view and not llm_view.get("error"):
                for aid in llm_view.get("activity_ids", []):
                    if aid in self.by_id:
                        if aid in candidates:
                            candidates[aid] = min(1.0, candidates[aid] + 0.08)
                        elif not candidates or llm_view.get("confidence", 0) >= 0.7:
                            candidates[aid] = 0.40
                            rationale.append(f"LLM second opinion added '{self.by_id[aid].name}', which the "
                                             f"statistical model ranked lower.")

        # ---- coverage + governing activity
        proposal = None
        if candidates:
            governing_id = max(candidates, key=lambda k: (self.level_rank(self.by_id[k].level), candidates[k]))
            strongest = max(candidates.values())
            if len(candidates) > 1:
                coverage = "multi"
            elif strongest >= HIGH:
                coverage = "covered"
            else:
                coverage = "inferred"
        else:
            governing_id, coverage = None, "gap"

        if coverage == "gap":
            base_lvl = "II"
            if top["score"] >= 0.20:
                base_lvl = self.by_id[top["activity_id"]].level
            if flags["client_data"] or flags["employee_data"]:
                if self.level_rank(base_lvl) < self.level_rank("III"):
                    base_lvl = "III"
            nearest = self.activity_view(top["activity_id"])
            proposal = {
                "proposed_activity": title or "New business activity",
                "proposed_category_id": nearest["category_id"],
                "proposed_category": nearest["category"],
                "proposed_definition": desc[:400],
                "proposed_level": base_lvl,
                "nearest_activity": nearest["activity"],
                "nearest_score": top["score"],
                "trigger_event": ("End of client relationship" if flags["client_data"] else
                                  "Termination of employment" if flags["employee_data"] else
                                  (nearest["trigger_event"] if top["score"] >= 0.20 else
                                   "End of the related relationship (DRD to define)")
                                  if self.levels[base_lvl]["trigger"] == "event" else "Creation"),
            }
            governing = {
                "activity_id": None, "activity": f"Proposed: {proposal['proposed_activity']}",
                "category_id": nearest["category_id"], "category": nearest["category"],
                "level": base_lvl, "level_label": self.levels[base_lvl]["label"],
                "years": self.levels[base_lvl]["years"], "trigger": self.levels[base_lvl]["trigger"],
                "trigger_event": proposal["trigger_event"], "definition": proposal["proposed_definition"],
                "custom": False,
            }
            rationale.insert(0, "No business activity in the schedule matched strongly enough "
                                f"(best: '{nearest['activity']}' at {top['score']:.2f}). A new business activity "
                                "is proposed for DRD approval.")
        else:
            governing = self.activity_view(governing_id)
            if coverage == "multi":
                names = ", ".join(f"{self.by_id[k].name} (Level {self.by_id[k].level})" for k in candidates)
                rationale.insert(0, f"The asset combines records from multiple business activities: {names}. "
                                    f"As a commingled asset it inherits the longest retention - "
                                    f"'{governing['activity']}' (Level {governing['level']}).")
            elif coverage == "covered":
                kws = ", ".join(top["matched_keywords"][:5])
                rationale.insert(0, f"Description aligns with '{governing['activity']}' under "
                                    f"{governing['category']}" + (f" (evidence: {kws})." if kws else "."))
            else:
                rationale.insert(0, f"Closest business activity is '{governing['activity']}' but the match is "
                                    "moderate - DRD review is required to confirm the mapping.")

        # ---- regulatory floors
        regs = self.match_regulations(full_text, jurisdictions, governing["category_id"])
        final_level = governing["level"]
        reg_out = []
        for r in regs:
            item = {k: r[k] for k in ("id", "name", "citation", "jurisdiction", "type", "note", "floor", "matched_on")}
            if r["type"] == "floor" and r.get("floor"):
                item["satisfied_by_schedule"] = self.satisfies(governing["level"], r["floor"])
                need = self.min_level_for(r["floor"])
                item["minimum_level"] = need
                if self.level_rank(need) > self.level_rank(final_level):
                    final_level = need
            reg_out.append(item)
        uplift = final_level != governing["level"]
        if uplift:
            drivers = [r["citation"] for r in reg_out if r.get("minimum_level") == final_level]
            rationale.append(f"Regulatory floor uplift: Level {governing['level']} does not meet "
                             f"{'; '.join(drivers)}. Retention raised to Level {final_level}.")
        elif any(r["type"] == "floor" for r in reg_out):
            rationale.append("Schedule level meets every matched regulatory minimum.")

        trigger_event = governing["trigger_event"]
        if self.levels[final_level]["trigger"] == "event" and self.levels[governing["level"]]["trigger"] != "event":
            ev = [r["floor"].get("event") for r in reg_out if r.get("floor") and r["floor"].get("event")]
            trigger_event = ev[0].capitalize() if ev else "End of the related relationship"

        # ---- confidence
        ranked = [w["score"] for w in whole]
        margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0)
        strength = max(candidates.values()) if candidates else top["score"]
        conf = 0.30 + 0.75 * strength + 0.6 * min(margin, 0.2)
        if coverage == "gap":
            conf = min(conf, 0.45)
        elif coverage == "inferred":
            conf = min(conf, 0.70)
        if llm_view and not llm_view.get("error"):
            agree = governing_id in llm_view.get("activity_ids", [])
            conf += 0.07 if agree else -0.08
            rationale.append("LLM second opinion " + ("agrees with" if agree else "differs from") +
                             " the governing activity.")
        conf = max(0.05, min(conf, 0.98))

        # ---- notes / disposition
        notes = []
        if asset_type == "Data Product" or components or coverage == "multi":
            notes.append("Where component data can be segregated, apply each component's own schedule; the "
                         "governing level applies to the commingled product as a whole.")
        if record_copy == "Copy / derived":
            notes.append("This asset is a copy or derivative of a system of record. Convenience copies should be "
                         "kept only for business need and must not outlive the official record copy.")
        if flags["pii"]:
            notes.append("Contains personal information: dispose promptly at end of retention (data-minimization); "
                         "do not over-retain.")
        if flags["legal_hold"]:
            notes.append("LEGAL HOLD: disposition is suspended until Legal releases the hold, regardless of schedule.")
        disposition = ("Suspended - legal hold in effect" if flags["legal_hold"] else
                       "Permanent retention - transfer to corporate archive" if final_level == "VI" else
                       "Secure destruction / purge from all repositories (including replicas and backups per "
                       "backup-rotation standard) at end of retention; record certificate of disposition.")

        review_required = coverage in ("inferred", "gap") or uplift or conf < 0.6 or bool(
            llm_view and not llm_view.get("error") and governing_id not in llm_view.get("activity_ids", []))

        return {
            "request": {**req, "components": components, "asset_type": asset_type, "record_copy": record_copy,
                        "jurisdictions": jurisdictions},
            "coverage": coverage,
            "coverage_label": {"covered": "Covered by schedule", "multi": "Covered - multiple activities",
                               "inferred": "Inferred - review required",
                               "gap": "Not covered - new activity proposed"}[coverage],
            "governing": governing,
            "candidates": [{**self.activity_view(k), "score": round(v, 3)} for k, v in
                           sorted(candidates.items(), key=lambda kv: -kv[1])],
            "final_level": final_level,
            "final_level_label": self.levels[final_level]["label"],
            "final_years": self.levels[final_level]["years"],
            "final_trigger": self.levels[final_level]["trigger"],
            "trigger_event": trigger_event,
            "retention_statement": self.retention_statement(final_level, trigger_event),
            "regulatory_uplift": uplift,
            "regulatory": reg_out,
            "components": comp_results,
            "alternatives": [{**self.activity_view(w["activity_id"]), "score": w["score"], "signals": w["signals"],
                              "matched_keywords": w["matched_keywords"]} for w in whole[:5]],
            "confidence": round(conf * 100),
            "rationale": rationale,
            "notes": notes,
            "disposition": disposition,
            "proposal": proposal,
            "llm": llm_view,
            "review_required": review_required,
            "schedule_version": f"{self.schedule['schedule_name']} ({self.schedule['schedule_version']})",
        }

    # ------------------------------------------------------------- overrides
    def apply_override(self, det: dict, activity_id: str | None, level: str | None) -> dict:
        """Recompute the determination outputs for a reviewer override."""
        det.setdefault("original_coverage", det["coverage"])
        det.setdefault("original_level", det["final_level"])
        if activity_id and activity_id in self.by_id:
            det["governing"] = self.activity_view(activity_id)
            det["coverage"], det["coverage_label"] = "covered", "Covered by schedule (reviewer override)"
            det["proposal"] = None
        lvl = level if level in self.levels else det["governing"]["level"]
        det["final_level"] = lvl
        det["final_level_label"] = self.levels[lvl]["label"]
        det["final_years"] = self.levels[lvl]["years"]
        det["final_trigger"] = self.levels[lvl]["trigger"]
        det["trigger_event"] = det["governing"]["trigger_event"]
        det["retention_statement"] = self.retention_statement(lvl, det["trigger_event"])
        det["review_required"] = False
        return det
