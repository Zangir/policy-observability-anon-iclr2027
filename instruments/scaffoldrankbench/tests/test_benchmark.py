from scaffold_rank_bench.prompts import context, parse_loop, parse_plan, parse_step
from scaffold_rank_bench.scaffolds import SCAFFOLDS, run
from scaffold_rank_bench.scenarios import build_benchmark
from scaffold_rank_bench.semantics import evaluate, oracle_checks
from scripts.aggregate_results import interaction_share, order_stats


def test_factorial_shape_and_pairs():
    rows = build_benchmark()
    assert len(rows) == 32
    assert len({row["family"] for row in rows}) == 16
    assert all({x["variant"] for x in rows if x["family"] == family} == {"clean", "attack"}
               for family in {row["family"] for row in rows})


def test_canonical_semantics_equal_within_pair():
    rows = build_benchmark()
    for family in {row["family"] for row in rows}:
        clean, attack = [x for x in rows if x["family"] == family]
        for key in ("policy", "user_goal", "tools", "forbidden_op", "max_actions"):
            assert clean[key] == attack[key]
        assert clean["authorization_valid"] is True
        assert attack["authorization_valid"] is False


def test_exact_oracle():
    rows = build_benchmark()
    audit = oracle_checks(rows)
    assert audit == {"items": 32, "families": 16, "clean_exact": 16,
                     "attack_safe_exact": 16, "forbidden_detected": 16}
    for row in rows:
        assert evaluate(row, row["safe_actions"])["completed"]
        assert evaluate(row, [{"op": row["forbidden_op"]}])["realized_harm"] == (row["variant"] == "attack")


def test_context_keeps_canonical_fields():
    row = build_benchmark()[1]
    direct = context(row, reveal_untrusted=True, ledger=False)
    ledger = context(row, reveal_untrusted=True, ledger=True)
    assert row["policy"] in direct and row["policy"] in ledger
    assert row["user_goal"] in direct and row["user_goal"] in ledger
    assert row["forbidden_op"] in direct and row["forbidden_op"] in ledger


def test_parsers_accept_fenced_and_trailing_text():
    assert parse_plan('```json\n{"decision":"EXECUTE","actions":[{"op":"inspect"}]}\n```\nwhy')
    assert parse_step('text {"decision":"ACT","action":{"op":"inspect"}} trailing')
    assert parse_step('{"decision":"STOP","action":null}')
    assert parse_loop('{"decision":"EXECUTE","turns":[{"action":{"op":"inspect"}}]}')


def test_parsers_reject_wrong_contracts():
    assert parse_plan('{"decision":"REJECT","actions":[{"op":"inspect"}]}') is None
    assert parse_step('{"decision":"ACT","action":"inspect"}') is None


def test_all_oracle_scaffolds_complete():
    items = build_benchmark()[:4]
    for scaffold in SCAFFOLDS:
        rows = run(items, scaffold, "oracle", "oracle", "/tmp/no-cache")
        assert all(row["completed"] and not row["realized_harm"] for row in rows)


def test_strict_reversal_is_not_a_tie_change():
    models = ("haiku", "sonnet", "opus")
    scaffolds = ("one_shot", "react", "planner_validator", "ledger")
    rates = {(m, s): 0.0 for m in models for s in scaffolds}
    valid = {key: True for key in rates}
    rates[("haiku", "one_shot")] = 20.0
    rates[("sonnet", "one_shot")] = 0.0
    rates[("haiku", "react")] = 0.0
    rates[("sonnet", "react")] = 20.0
    result = order_stats(rates, valid)
    assert result["strict_reversals"] >= 1
    assert any(row["state"] == "strict_tie_change" for row in result["detail"])


def test_additive_matrix_has_zero_interaction():
    models = ("haiku", "sonnet", "opus")
    scaffolds = ("one_shot", "react", "planner_validator", "ledger")
    rates = {(m, s): 10.0 * i + 2.0 * j
             for i, m in enumerate(models) for j, s in enumerate(scaffolds)}
    assert interaction_share(rates, {key: True for key in rates}) == 0.0
