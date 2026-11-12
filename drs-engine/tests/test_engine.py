"""Run: python -m pytest -q   (or python tests/test_engine.py)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.engine import RetentionEngine  # noqa: E402

E = RetentionEngine(ROOT / "data")


def det(**kw):
    kw.setdefault("use_llm", False)
    return E.determine(kw)


def test_single_activity():
    d = det(title="Advisor email archive", description="All emails between financial advisors and clients",
            asset_type="Communication")
    assert d["governing"]["activity_id"] == "2.1" and d["final_level"] == "III"


def test_mixed_data_product_takes_longest():
    d = det(title="Client 360", description="Unified client view", asset_type="Data Product",
            components=["Client account master", "Marketing campaign responses", "Reg BI suitability reviews"])
    assert d["coverage"] == "multi" and d["final_level"] == "III"


def test_gap_proposes_activity():
    d = det(title="Emissions", description="Scope 1 and 2 greenhouse gas emissions inventory for ESG disclosure")
    assert d["coverage"] == "gap" and d["proposal"]


def test_regulatory_uplift():
    # Internal Provisioning is Level I (5 yrs) - BSA wire records need 5 yrs, tax records 7 -> uplift to II
    d = det(title="Tax withholding ETL", description="ETL pipeline source code and job logs that compute 1099 tax withholding")
    assert E.level_rank(d["final_level"]) >= E.level_rank("II")


def test_legal_hold_suspends():
    d = det(title="x", description="SEC examination production and counsel correspondence", legal_hold=True)
    assert d["disposition"].startswith("Suspended")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
