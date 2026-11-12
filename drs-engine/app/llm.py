"""
Optional LLM second opinion.

Configure with environment variables (see .env.example):
  DRS_LLM_PROVIDER = none | ollama | anthropic       (default: none)
  DRS_LLM_MODEL    = e.g. llama3.1:8b (ollama) or claude-sonnet-5-5 (anthropic)
  OLLAMA_URL       = http://localhost:11434            (ollama only)
  ANTHROPIC_API_KEY                                   (anthropic only)

Ollama keeps all descriptions on the local machine. Only enable an external API if your
data-handling policy allows asset descriptions to leave the firm.
"""
from __future__ import annotations

import json
import os
import re

import httpx

PROMPT = """You are a records-retention analyst for a US/Canadian broker-dealer and investment adviser.
Map the data asset below to one or more BUSINESS ACTIVITIES from the firm's retention schedule.
A data product that commingles records from several activities should list every activity it contains.
If nothing fits, return an empty list and propose a new activity.

RETENTION SCHEDULE (id | category | activity | level | definition):
{schedule}

LEVELS: {levels}

DATA ASSET:
Title: {title}
Asset type: {asset_type}
Description: {description}
Components: {components}
Flags: client data={client_data}, employee data={employee_data}, PII={pii}

Respond with JSON only, no prose:
{{"activity_ids": ["<id>", ...], "confidence": <0-1>, "reasoning": "<2-3 sentences>",
  "regulatory_considerations": ["<short note>", ...],
  "new_activity": null or {{"name": "...", "category": "...", "level": "I-VI", "why": "..."}}}}"""


class LLMAdvisor:
    def __init__(self):
        self.provider = os.getenv("DRS_LLM_PROVIDER", "none").lower()
        self.model = os.getenv("DRS_LLM_MODEL") or ("llama3.1:8b" if self.provider == "ollama" else "claude-sonnet-5-5")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def enabled(self) -> bool:
        if self.provider == "ollama":
            return True
        if self.provider == "anthropic":
            return bool(self.api_key)
        return False

    def status(self) -> dict:
        return {"provider": self.provider, "model": self.model if self.enabled else None, "enabled": self.enabled}

    def _prompt(self, req: dict, engine) -> str:
        sched = "\n".join(f"{a.id} | {a.category} | {a.name} | {a.level} | {a.definition}" for a in engine.activities)
        levels = "; ".join(v["label"] for v in engine.levels.values())
        return PROMPT.format(schedule=sched, levels=levels, title=req.get("title", ""),
                             asset_type=req.get("asset_type", ""), description=req.get("description", ""),
                             components="; ".join(req.get("components") or []) or "n/a",
                             client_data=bool(req.get("client_data")), employee_data=bool(req.get("employee_data")),
                             pii=bool(req.get("pii")))

    def classify(self, req: dict, engine) -> dict | None:
        prompt = self._prompt(req, engine)
        try:
            if self.provider == "ollama":
                r = httpx.post(f"{self.ollama_url}/api/generate", timeout=90,
                               json={"model": self.model, "prompt": prompt, "stream": False, "format": "json",
                                     "options": {"temperature": 0}})
                r.raise_for_status()
                text = r.json().get("response", "")
            elif self.provider == "anthropic":
                r = httpx.post("https://api.anthropic.com/v1/messages", timeout=90,
                               headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                                        "content-type": "application/json"},
                               json={"model": self.model, "max_tokens": 800, "temperature": 0,
                                     "messages": [{"role": "user", "content": prompt}]})
                r.raise_for_status()
                text = "".join(b.get("text", "") for b in r.json().get("content", []))
            else:
                return None
            m = re.search(r"\{.*\}", text, re.S)
            data = json.loads(m.group(0) if m else text)
            data["activity_ids"] = [str(x).strip() for x in data.get("activity_ids", [])]
            data["provider"], data["model"] = self.provider, self.model
            return data
        except Exception as exc:  # never block a determination on the LLM
            return {"error": f"{type(exc).__name__}: {exc}"[:300], "provider": self.provider, "model": self.model}
