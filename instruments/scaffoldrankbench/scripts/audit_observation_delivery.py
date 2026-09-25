"""Audit the observation callback and inspect metadata without changing scores."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "results/review_openai_v1.json"
    data = json.loads(source.read_text())
    counts = defaultdict(Counter)
    exceptions = []
    for row in data["detail"]:
        raw = json.loads((ROOT / "results/review_openai_v1/responses" /
                          (row["request_id"] + ".json")).read_text())
        first, final = raw.get("first_parsed") or {}, raw.get("parsed") or {}
        c = counts[row["model"] + "/" + row["condition"]]
        c["n"] += 1
        c["first_inspect_true"] += int(first.get("inspect") is True)
        c["final_inspect_false"] += int(final.get("inspect") is False)
        transcript = raw.get("transcript", [])
        delivered = False
        if len(transcript) > 1:
            envelope = json.loads(transcript[1]["user"].split("\n", 1)[0])
            delivered = envelope.get("tool") == "inspect"
            if delivered:
                assert envelope["record"] == raw["context"]["trusted_records"]
                assert envelope["state_changed"] is False
        c["same_record_delivered"] += int(delivered)
        if ((row["condition"] == "observe" and not delivered)
                or final.get("inspect") is not False):
            exceptions.append({"request_id": row["request_id"],
                               "condition": row["condition"], "model": row["model"],
                               "first_inspect": first.get("inspect"),
                               "final_inspect": final.get("inspect"),
                               "observation_delivered": delivered})
    report = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "scope": "Post-plan callback audit. Primary scoring uses a completed final decision; inspect is procedural metadata, not an additional correctness requirement.",
              "counts": dict(counts), "exceptions": exceptions}
    (ROOT / "results/review_openai_observation_audit.json").write_text(
        json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["counts"], indent=2))


if __name__ == "__main__":
    main()
