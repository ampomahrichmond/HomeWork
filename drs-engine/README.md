# Retention Schedule Determination Engine

A localhost tool for the Data Retention & Disposition (DRD) program. A data owner or product team describes a data asset, and the engine maps it to the General Retention Schedule, checks regulatory minimums, handles mixed data products, and proposes a schedule when the current one has no matching business activity. You can download each result as a PDF, Excel or JSON issuance.

## Quick start

```bash
./run.sh          # macOS / Linux
run.bat           # Windows
```
Then open **http://localhost:8050**. The first run creates a `.venv` and installs the dependencies (Python 3.10+).

Manual alternative:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8050
```

## What it does

| Screen | Purpose |
|---|---|
| **Assess** | Enter the title, description, asset type, components, owner and data flags. Returns the retention level, period, trigger event, governing activity, confidence score, rationale, component breakdown, regulatory checks and engine ranking. Reviewers can **Approve**, **Override** or **Reject**. Downloads: **PDF / Excel / JSON**. |
| **Register** | Every issuance (Draft → Approved / Override / Rejected), with search and filters (incl. *Needs review*). Excel export of the full register. **Batch upload** via CSV (template provided). |
| **Schedule** | The master schedule (levels, categories, activities, definitions, trigger events), DRD-approved extensions, and the regulatory knowledge base. Excel export. |
| **Insights** | Volume, confidence, level and coverage distribution, schedule gaps found, approved extensions and engine status. |

## How a determination is made

1. **Understanding the text.** Each business activity is scored on three signals:
   - Keywords and phrases from a curated vocabulary for that activity (`data/schedule.json`).
   - TF-IDF similarity on words and character n-grams. The character n-grams cope with jargon and typos.
   - Nearest-neighbour similarity to labelled examples: the seed scenarios plus every reviewer decision.

   Asset type and the client, associate and PII flags add small priors.
2. **Breaking down mixed assets.** For a data product, each listed component is classified separately. If no components are listed, the engine splits the description into its source fragments.
3. **Precedence.** A commingled asset takes the longest retention of its components (I < II < III < IV < V < VI). The output notes that segregated components can keep their own schedules.
4. **Regulatory floor check.** `data/regulatory_knowledge.json` lists minimums from SEC 17a-4, FINRA 4511/4513, Advisers Act 204-2, BSA/CIP/SAR, IRS, ERISA, FLSA, EEOC, I-9, OSHA, SOX, Reg E and Reg B, plus Canadian FINTRAC and CIRO. If the schedule level falls short of a floor that matches the asset, the level is raised and the reason is shown. Event-based floors (e.g. "6 years after account closing") are only met by event-based levels or by Level VI. Privacy minimization is recorded as a *ceiling*.
5. **Coverage.**
   - *Covered*: strong match.
   - *Covered – multiple activities*: the asset spans more than one activity.
   - *Inferred*: moderate match, so review is required.
   - *Not covered*: the engine proposes a **new business activity** with a category, level and trigger, based on the nearest activity, the data flags and the regulatory floors.
6. **Learning loop.** Each approval or override is stored as a training example and the model retrains straight away. When you approve a gap with **"Add to schedule"**, a DRD-approved extension (e.g. `4.X1`) is created, and similar future requests are covered by it.
7. **Optional AI second opinion.** This sends the whole schedule plus the asset to an LLM and blends its answer in. Agreement raises confidence; disagreement flags the issuance for review. The final decision is always made by the deterministic engine.

Other factors that are handled: **legal hold** suspends disposition; a **copy or derived** asset gets a note that it must not outlive the record copy; **PII** prompts disposal on time; jurisdiction can be **US** and/or **Canada**.

## AI second opinion (optional)

Copy `.env.example` to `.env`:

- **Local and private (recommended):** install [Ollama](https://ollama.com), run `ollama pull llama3.1:8b`, then set `DRS_LLM_PROVIDER=ollama`. Descriptions never leave the machine.
- **Anthropic API:** set `DRS_LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. Only use this if data-handling policy allows asset descriptions to leave the firm.

The engine works fully without an LLM.

## Customising

| File | Change |
|---|---|
| `data/schedule.json` | Levels, categories, activities, definitions, trigger events, and keywords (the most effective tuning lever). **Definitions for categories 8–10 are drafts.** Replace them with the official page-2 text. |
| `data/regulatory_knowledge.json` | Add, edit or retire regulatory minimums. Legal/Compliance must validate every entry. |
| `data/seed_examples.json` | Labelled scenarios. Add your real historical determinations here to warm-start the learner. |
| `app/engine.py` | Thresholds `HIGH`, `LOW` and `COMPONENT_MIN`, asset-type priors, and signal weights. |

Restart after editing the JSON files. To reset everything, delete `data/drs.db`.

## API

`POST /api/assess` · `GET /api/issuances` · `GET /api/issuances/{id}` · `POST /api/issuances/{id}/review` · `GET /api/issuances/{id}/export?fmt=pdf|xlsx|json` · `GET /api/register.xlsx` · `POST /api/batch` (CSV) · `GET /api/schedule` · `GET /api/schedule.xlsx` · `GET /api/knowledge` · `GET /api/stats`. Interactive docs are at **/docs**.

## Tests

```bash
python tests/test_engine.py
```

## Important

Determinations are decision support. Regulatory references are a curated starting point, not legal advice. Issuances should be approved by DRD, and Legal/Compliance should validate them where flagged.
