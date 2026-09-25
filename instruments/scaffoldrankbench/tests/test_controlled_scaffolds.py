from scaffold_rank_bench.controlled import SCAFFOLDS, authorize, build_requests, execute_decision, followup


def test_scaffolds_have_identical_authorization_facts_without_gold_labels():
    rows = build_requests()
    for item in {r["item_id"] for r in rows}:
        group = [r for r in rows if r["item_id"] == item]
        assert {r["condition"] for r in group} == set(SCAFFOLDS)
        assert all(r["context"] == group[0]["context"] for r in group)
        assert all("authorization_valid" not in r["prompt"] for r in group)
        assert all(authorize(r["context"]["trusted_records"]) == r["gold"] for r in group)


def test_observation_returns_actual_records_without_a_derived_verdict():
    row = next(r for r in build_requests() if r["condition"] == "observe")
    text = followup(row, {"decision": "REJECT", "inspect": True})
    assert '"tool": "inspect"' in text and '"record":' in text
    assert '"authorized":' not in text


def test_final_decision_is_applied_without_a_perfect_guard_hiding_errors():
    row = next(r for r in build_requests() if not r["gold"])
    record = row["context"]["trusted_records"]
    state = execute_decision(record, "EXECUTE")
    assert state["final_value"] == "after" and state["unauthorized_write"]
    assert execute_decision(record, "REJECT")["final_value"] == "before"
