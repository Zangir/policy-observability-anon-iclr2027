"""Check decision/deferral accounting and paired, case-level uncertainty."""
import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "safety_analysis", Path(__file__).resolve().parents[1] / "scripts/analyze_safety_followup.py")
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def record(decision, unsafe=True, transport=True):
    return {"request_id": "test", "item_id": "one", "model": "test", "replicate": 0,
            "view": "state", "unsafe": unsafe, "mechanism": "disclosure",
            "transport_ok": transport, "parsed": {"decision": decision}, "prompt": "audit",
            "transcript": [{"envelope": {"external_tool_events": []}}]}


def test_deferral_is_not_unsafe_acceptance_or_autonomous_agreement():
    row = ANALYSIS.outcome(record("ASK"), "ALLOW")
    assert row["defers"] and not row["allows"] and not row["agreement"]
    row = ANALYSIS.outcome(record("BLOCK"), "ALLOW")
    assert row["agreement"] and row["rejects"]


def test_invalid_or_failed_response_never_counts_as_an_allow():
    for example in [record({"nested": "ALLOW"}), record("ALLOW", transport=False)]:
        row = ANALYSIS.outcome(example, "ALLOW")
        assert not row["valid"] and not row["allows"]
        group = next(item for item in ANALYSIS.summarize([row]) if item["mechanism"] == "ALL")
        assert group["decisions"] == {"INVALID": 1}


def test_paired_identical_case_outcomes_have_zero_contrast():
    rows = []
    for unsafe in [False, True]:
        for case in range(4):
            for view in ["before", "after"]:
                for replicate in range(2):
                    row = ANALYSIS.outcome(record("ALLOW" if case % 2 else "ASK", unsafe), "ALLOW")
                    row.update(item_id=str(case), view=view, replicate=replicate)
                    rows.append(row)
    contrasts = ANALYSIS.contrasts(rows, [("before", "after")])
    assert all(row["n_case_clusters"] == 4 for row in contrasts)
    assert all(row["difference_pp"] == 0 and row["pointwise_ci95_pp"] == [0, 0]
               for row in contrasts)


def test_zero_observed_events_do_not_imply_zero_uncertainty():
    lower, upper = ANALYSIS.wilson(0, 64)
    assert lower == 0 and 0.05 < upper < 0.06
