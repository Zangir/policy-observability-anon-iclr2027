import pytest

from scripts.audit_scaffold_outcomes import SCAFFOLDS, simultaneous_gap_bands


def test_opposite_stable_gaps_and_incomplete_grid():
    rows = [{"item_id": str(i), "model": model, "condition": scaffold, "replicate": 0,
             "correct": int((model == "sonnet") == (k < 2))}
            for i in range(4) for k, scaffold in enumerate(SCAFFOLDS) for model in ["haiku", "sonnet"]]
    result = simultaneous_gap_bands(rows, draws=100)
    assert result["radius"] == 0
    assert sum(r["strict_reversal"] for r in result["comparisons"]) == 4
    with pytest.raises(ValueError, match="Incomplete"):
        simultaneous_gap_bands(rows[:-1], draws=100)


def test_family_uncertainty_is_retained_jointly():
    rows = [{"item_id": str(i), "model": model, "condition": scaffold, "replicate": 0,
             "correct": int((model == "sonnet") == (i < 2))}
            for i in range(4) for scaffold in SCAFFOLDS for model in ["haiku", "sonnet"]]
    result = simultaneous_gap_bands(rows, draws=1000)
    assert result["radius"] > 0
    assert all(v["simultaneous_ci95"][0] < 0 < v["simultaneous_ci95"][1] for v in result["per_scaffold"].values())
    assert not any(r["strict_reversal"] for r in result["comparisons"])
