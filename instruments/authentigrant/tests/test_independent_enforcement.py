from copy import deepcopy

from authentigrant.controlled import PATTERNS, graph_authorized, records, sql_enforce


def test_failure_patterns_are_crossed_with_every_domain():
    rows = records()
    for domain in {r["domain"] for r in rows}:
        assert {r["pattern"] for r in rows if r["domain"] == domain} == set(PATTERNS)


def test_sql_gate_prevents_unauthorized_writes_without_reading_gold():
    for row in records():
        state = sql_enforce(row["record"], "EXECUTE")
        assert state["executed"] == graph_authorized(row["record"]) == row["gold"]
        assert not sql_enforce(row["record"], "REJECT")["executed"]


def test_cycle_and_boundary_expiry_fail_closed_in_both_resolvers():
    record = deepcopy(records()[0]["record"])
    record["grants"][0]["parent"] = "g2"
    record["grants"][0]["issuer"] = "requester"
    assert not graph_authorized(record) and not sql_enforce(record, "EXECUTE")["authorized"]
    record = deepcopy(records()[0]["record"])
    record["grants"][0]["end"] = record["now"]
    assert not graph_authorized(record) and not sql_enforce(record, "EXECUTE")["authorized"]
def test_prompt_controls_have_equal_visible_word_counts_per_record():
    from authentigrant.controlled import build_requests
    rows = build_requests()
    for item in {r["item_id"] for r in rows}:
        assert len({len(r["prompt"].split()) for r in rows if r["item_id"] == item}) == 1
