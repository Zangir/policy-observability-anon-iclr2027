from compositional_harm_bench.policy import locally_allowed
from compositional_harm_bench.prompts import parse
from compositional_harm_bench.scenarios import build_benchmark, evaluation_subset
from compositional_harm_bench.simulator import replay


def test_shape_and_pairing():
    rows = build_benchmark()
    assert len(rows) == 1920
    assert len({row["id"] for row in rows}) == 1920
    for family in range(640):
        assert {r["variant"] for r in rows if r["family"] == family} == {
            "clean", "compositional", "atomic"}


def test_evaluation_slice():
    rows = evaluation_subset()
    assert len(rows) == 60
    assert len({(row["domain"], row["mechanism"]) for row in rows}) == 20


def test_gold_local_policy_contract():
    for row in build_benchmark():
        allowed = [locally_allowed(action) for action in row["actions"]]
        assert sum(not value for value in allowed) == (row["variant"] == "atomic")


def test_gold_final_state_oracle():
    for row in build_benchmark():
        harm = replay(row["actions"], "unprotected")["harm"]
        assert harm == (row["variant"] != "clean")


def test_local_filter_separates_atomic_not_composition():
    for row in build_benchmark():
        result = replay(row["actions"], "local_filter")
        if row["variant"] == "atomic":
            assert result["blocked_at"] is not None and not result["harm"]
        elif row["variant"] == "compositional":
            assert result["blocked_at"] is None and result["harm"]


def test_trajectory_controls_block_harm_preserve_clean():
    for row in build_benchmark():
        for mode in ("trajectory_monitor", "approval"):
            result = replay(row["actions"], mode)
            assert not result["harm"]
            assert (result["blocked_at"] is None) == (row["variant"] == "clean")


def test_strict_parser():
    assert parse('{"decision":"REJECT","actions":[]}')["decision"] == "REJECT"
    assert parse("not json") is None
    assert parse('{"decision":"REJECT","actions":[1]}') is None
