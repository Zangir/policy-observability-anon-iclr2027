"""Deterministic integrity checks for the benchmark and scorer."""
import json
import unittest

from authentigrant.policy import envelope, oracle_decision, simulate
from authentigrant.scenarios import FACTOR_NAMES, TASKS, build_rows, validate_grid
from authentigrant.scoring import parse_response, score_rows, summarize


class AuthentiGrantTests(unittest.TestCase):
    def test_complete_grid(self):
        rows = build_rows()
        validate_grid(rows)
        self.assertEqual(len(rows), len(TASKS) * (2 ** len(FACTOR_NAMES)))

    def test_oracle_authorization_count(self):
        rows = build_rows([0])
        self.assertEqual(sum(oracle_decision(row) == "EXECUTE" for row in rows), 4)

    def test_identity_evidence(self):
        valid, invalid = build_rows([0])[-1], build_rows([0])[15]
        self.assertEqual(envelope(valid)["certificate"]["signature_check"], "VALID")
        self.assertNotEqual(envelope(invalid)["certificate"]["subject"], invalid["task"]["principal"])

    def test_forbidden_transition_is_blocked(self):
        row = build_rows([0])[0]
        result = simulate(row, "EXECUTE")
        self.assertTrue(result["blocked_unsafe"])
        self.assertEqual(result["final_value"], row["task"]["before"])

    def test_parser(self):
        self.assertEqual(parse_response('```json\n{"decision":"reject","basis":[]}\n```')[0], "REJECT")
        self.assertIsNone(parse_response("maybe")[0])

    def test_oracle_scores_perfectly(self):
        rows = build_rows([0, 1])
        responses = [json.dumps({"decision": oracle_decision(row), "basis": []}) for row in rows]
        scored = score_rows(rows, responses)
        report = summarize(scored, draws=20)
        self.assertEqual(report["oracle_decision_accuracy"], 1.0)
        self.assertEqual(report["unsafe_execution_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
