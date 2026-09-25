"""Explicitly adaptive source-context and annotation-conflict sensitivities."""
from collections import Counter
import json
from pathlib import Path
from analyze_safety_followup import contrasts, summarize

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = json.loads((ROOT / "results/external_inputs/atbench-test.json").read_text())
    data = json.loads((ROOT / "results/atbench_observation_v1.json").read_text())
    by_id = {row["id"]: row for row in source}
    user_counts = {row["id"]: sum(message["role"] == "user" for block in row["contents"] for message in block)
                   for row in source}
    selected = sorted({row["source_id"] for row in data["rows"]})
    subsets = {"single_user_message": {key for key in selected if user_counts[key] == 1},
               "multiple_user_messages": {key for key in selected if user_counts[key] > 1},
               "exclude_annotation_conflict_781": set(selected) - {781}}
    assert subsets["single_user_message"] | subsets["multiple_user_messages"] == set(selected)
    assert by_id[781]["label"] == 1
    assert "successfully defended" in by_id[781]["reason"] and "prevented harm" in by_id[781]["reason"]
    reports = {}
    for name, ids in subsets.items():
        rows = [row for row in data["rows"] if row["source_id"] in ids]
        reports[name] = {"ids": sorted(ids), "n_source_records": len(ids),
                         "source_label_counts": dict(Counter(by_id[key]["label"] for key in ids)),
                         "groups": summarize(rows),
                         "contrasts": contrasts(rows, [("action_log", "full")])}
    report = {"adaptive": True, "primary_results_unchanged": True,
              "selected_user_message_counts": {str(key): user_counts[key] for key in selected},
              "subsets": reports, "annotation_conflict": {
                  "source_id": 781, "source_label": by_id[781]["label"],
                  "source_reason": by_id[781]["reason"],
                  "status": "Internal label/explanation contradiction; no replacement label assigned."},
              "scope": "Post-outcome interpretation checks. Multiple-user views change access to later instructions as well as environment feedback and thoughts. One discovered annotation contradiction is not a full source-error census. These pointwise sensitivities supplement, never replace, the frozen primary analysis."}
    (ROOT / "results/followup_interpretation_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    for name, subset in reports.items():
        print(name, subset["source_label_counts"])
        for row in subset["contrasts"]:
            if row["measure"] == "allows":
                print(row["model"], row["unsafe"], row["difference_pp"], row["pointwise_ci95_pp"])


if __name__ == "__main__":
    main()
