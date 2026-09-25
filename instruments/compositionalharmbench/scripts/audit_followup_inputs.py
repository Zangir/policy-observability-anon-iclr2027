"""Reconstruct selection, verify frozen inputs and test annotation exclusion exhaustively."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compositional_harm_bench.followup import binding_requests, external_requests


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    directory = ROOT / "results/external_inputs"
    selection = json.loads((directory / "ATBENCH_SELECTION.json").read_text())
    source = directory / "atbench-test.json"
    assert digest(source) == selection["source_sha256"]
    rows = json.loads(source.read_text())
    assert len({row["id"] for row in rows}) == len(rows)
    chosen = []
    for label in [0, 1]:
        candidates = sorted((row for row in rows if row["label"] == label),
                            key=lambda row: hashlib.sha256(
                                f"{selection['seed']}:{row['id']}".encode()).hexdigest())
        chosen.extend(row["id"] for row in candidates[:64])
    assert sorted(chosen) == selection["ids"]
    hashes = json.loads((directory / "PRECALL_CODE_HASHES.json").read_text())
    assert all(digest(ROOT / name) == value for name, value in hashes.items())
    external = external_requests(rows, selection)
    for study, requests in [("binding_repair_v1", binding_requests()),
                            ("atbench_observation_v1", external)]:
        frozen = json.loads((ROOT / "results" / study / "frozen_requests.json").read_text())
        assert frozen["requests"] == requests
        encoded = json.dumps(requests, sort_keys=True, ensure_ascii=False).encode()
        assert hashlib.sha256(encoded).hexdigest() == frozen["requests_sha256"]
    # All source rows, not just the selected study subset. Alter every annotation;
    # exact equality of all three prompts must remain true.
    all_ids = {"ids": [row["id"] for row in rows]}
    original = external_requests(rows, all_ids)
    altered = copy.deepcopy(rows)
    for row in altered:
        row["label"] = 1 - row["label"]
        for key in ["risk_source", "failure_mode", "reason", "real_world_harm"]:
            row[key] = "REPLACED_ANNOTATION_FOR_INPUT_AUDIT"
    changed = external_requests(altered, all_ids)
    assert [row["prompt"] for row in original] == [row["prompt"] for row in changed]
    messages = [message for row in rows for block in row["contents"] for message in block]
    actions = [message["action"] for message in messages
               if message["role"] == "agent" and message.get("action")
               and not message["action"].lstrip().startswith("Complete")]
    for action in actions:
        json.loads(action)
    selected_rows = [row for row in rows if row["id"] in chosen]
    counts = Counter(row["failure_mode"] for row in selected_rows)
    report = {"all_passed": True, "source_sha256": digest(source),
              "source_rows": len(rows), "source_labels": dict(Counter(row["label"] for row in rows)),
              "source_messages": len(messages), "nonterminal_json_actions": len(actions),
              "annotation_invariant_prompts": len(original), "selected_rows": len(chosen),
              "selected_labels": dict(Counter(row["label"] for row in selected_rows)),
              "selected_failure_modes": dict(sorted(counts.items())),
              "frozen_code_files_verified": len(hashes),
              "frozen_design_rows_verified": len(external) + len(binding_requests()),
              "selected_last_action_fallbacks": sum(row["last_action_fallback"]
                                                    for row in external if row["view"] == "last_action"),
              "scope": "Exact input reconstruction and structural audit. Annotation exclusion does not prove that natural trajectory evidence cannot reveal its safety label. No source task is executed."}
    (ROOT / "results/followup_input_validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
