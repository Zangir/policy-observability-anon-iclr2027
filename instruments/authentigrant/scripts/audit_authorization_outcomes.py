"""Separate authorized utility, unsafe proposals, transport and enforced effects."""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controlled_runner import paired_contrasts, summarize


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--study", default="review_controls_v1"); args = parser.parse_args()
    data = json.loads((ROOT / "results" / (args.study + ".json")).read_text())
    counts, patterns, failures = defaultdict(Counter), defaultdict(Counter), []
    authorized, unauthorized, pattern_rows = [], [], []
    for row in data["rows"]:
        raw = json.loads((ROOT / "results" / args.study / "responses" / (row["request_id"] + ".json")).read_text())
        key = row["model"] + "/" + row["condition"]
        c = counts[key]
        gold = raw["gold"]
        c["n"] += 1
        c["correct"] += int(row["correct"])
        c["n_authorized" if gold else "n_unauthorized"] += 1
        c["authorized_execution"] += int(gold and row["correct"])
        c["unsafe_proposal"] += int(row["unsafe_proposal"])
        c["unauthorized_write"] += int(row["unauthorized_write"])
        c["transport_failure"] += int(not raw["transport_ok"])
        c["returned_malformed"] += int(raw["transport_ok"] and not row["parse_ok"])
        patterns[key + "/" + row["pattern"]]["n"] += 1
        patterns[key + "/" + row["pattern"]]["correct"] += int(row["correct"])
        (authorized if gold else unauthorized).append(row)
        # Secondary sensitivity: share a cluster across scope labels of one pattern.
        # Replicate names remain unique within that larger cluster.
        pattern_rows.append({**row, "item_id": row["pattern"],
                             "replicate": row["domain"] + "/" + str(row["replicate"])})
        if not row["correct"]:
            failures.append({**row, "authorized": gold, "prediction": raw["parsed"],
                             "transport_ok": raw["transport_ok"]})
    pairs = [("caution_neutral", "ledger_neutral"), ("caution_claim", "ledger_claim"),
             ("caution_neutral", "caution_claim"), ("ledger_neutral", "ledger_claim")]
    result = {"scope": "Post-plan decomposition and pattern-cluster sensitivity. Primary scores and planned item-cluster intervals remain unchanged. Ten fixed patterns are not a sample of real organizations.",
              "counts": dict(counts), "patterns": dict(patterns), "failures": failures,
              "authorized_summary": summarize(authorized, ("correct", "parse_ok")),
              "unauthorized_summary": summarize(unauthorized, ("unsafe_proposal", "parse_ok", "unauthorized_write")),
              "pattern_cluster_contrasts": paired_contrasts(pattern_rows, pairs)}
    (ROOT / "results" / (args.study + "_review_authorization_audit.json")).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
