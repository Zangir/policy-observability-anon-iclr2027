"""Verify the complete public release and extract an auditable score projection."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq


def digest(data):
    return hashlib.sha256(data).hexdigest()


def project(source, out):
    inventory = json.loads((source / "metadata/data_files.json").read_text())
    for entry in inventory["files"]:
        path = source / entry["path"]
        assert path.stat().st_size == entry["size_bytes"]
        assert digest(path.read_bytes()) == entry["sha256"]
    tasks = pq.read_table(source / "data/task_pairs/test-00000-of-00001.parquet").to_pylist()
    task_map = {row["task_id"]: row for row in tasks}
    assert len(task_map) == len(tasks) == 300
    embedded_files = 0
    for task in tasks:
        for name in ["clean_files", "attack_files"]:
            for file in task[name]:
                encoded = file["content"].encode()
                assert len(encoded) == file["size_bytes"] and digest(encoded) == file["sha256"]
                embedded_files += 1
    projected = []
    mismatches = []
    trajectory_ids = set()
    hash_mismatches = []
    for file in sorted((source / "data/trajectories").glob("*.parquet")):
        raw = pq.read_table(file).to_pylist()
        for row in raw:
            trajectory = json.loads(row["trajectory_json"])
            # The published link refers to pretty UTF-8 JSON without a terminal newline.
            encoded = json.dumps(trajectory, indent=2, ensure_ascii=False).encode()
            reconstructed_hash = digest(encoded)
            if reconstructed_hash != row["trajectory_sha256"]:
                hash_mismatches.append({"combo_id": row["combo_id"],
                    "trajectory_id": row["trajectory_id"], "published_sha256": row["trajectory_sha256"],
                    "reconstructed_sha256": reconstructed_hash})
            assert row["trajectory_id"] not in trajectory_ids
            trajectory_ids.add(row["trajectory_id"])
            score = json.loads(row["score_json"])
            task = task_map[row["task_id"]]
            execution = trajectory["execution"]
            inputs = trajectory["scoring_inputs"]
            record = {key: row[key] for key in ["combo_id", "backend", "model", "task_id",
                      "role", "attack_slot", "run_number", "trajectory_id", "trajectory_sha256"]}
            record.update({"scenario_id": task["scenario_id"], "behavior_id": task["behavior_id"],
                           "score": score, "execution_status": execution.get("status"),
                           "exit_code": execution.get("exit_code"), "timed_out": execution.get("timed_out"),
                           "execution_time": execution.get("execution_time"),
                           "usage": execution.get("usage"),
                           "threshold": inputs.get("attack_success_threshold"),
                           "configured_judge_model": inputs.get("configured_judge_model"),
                           "default_judge_model": inputs.get("default_judge_model"),
                           "transcript_entries": trajectory["transcript"].get("entry_count"),
                           "source_json_sha256": digest(row["trajectory_json"].encode()),
                           "published_trajectory_hash_reconstructed": reconstructed_hash == row["trajectory_sha256"]})
            assert row["suite"] == task["behavior_id"]
            if inputs.get("scenario_id") != task["scenario_id"]:
                mismatches.append({"trajectory_id": row["trajectory_id"],
                                   "field": "scenario_id", "trajectory": inputs.get("scenario_id"),
                                   "task": task["scenario_id"]})
            projected.append(record)
        print(file.name, len(raw), "source rows projected", flush=True)
    keys = [(row["combo_id"], row["task_id"], row["role"], row["attack_slot"]) for row in projected]
    assert len(set(keys)) == len(keys)
    counts = Counter((row["combo_id"], row["task_id"], row["role"]) for row in projected)
    assert all(value == (1 if key[-1] == "clean" else 3) for key, value in counts.items())
    assert len(projected) == 24000 and len(counts) == 12000
    report = {"source_revision": "595df032d53ef71f927c9a1d8c068dad0edebbc5",
              "n_source_files_verified": len(inventory["files"]),
              "source_files": inventory["files"], "n_embedded_task_files_verified": embedded_files,
              "n_trajectory_hashes_reconstructed": len(projected) - len(hash_mismatches),
              "n_trajectory_hashes_unresolved": len(hash_mismatches),
              "trajectory_hash_mismatches": hash_mismatches, "n_tasks": len(tasks),
              "n_scenarios": len({task["scenario_id"] for task in tasks}),
              "n_configs": len({row["combo_id"] for row in projected}),
              "execution_statuses": dict(Counter(row["execution_status"] for row in projected)),
              "execution_timeouts": sum(bool(row["timed_out"]) for row in projected),
              "metadata_mismatches": mismatches,
              "scope": "Exact projection of published scores and selected provenance fields. All original Parquet file hashes verified. Reconstructed and unresolved canonical trajectory hashes reported separately; full-release lineage is not certified for mismatches. No judge re-execution, workspace reconstruction, or task action execution."}
    out.mkdir(parents=True, exist_ok=True)
    (out / "actbench_projection.json").write_text(json.dumps(projected, indent=2) + "\n")
    (out / "actbench_source_validation.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "actbench_task_metadata.json").write_text(json.dumps(
        [{key: task[key] for key in ["task_id", "scenario_id", "behavior_id", "behavior_label",
          "scoring_family", "attack_method"]} for task in tasks], indent=2) + "\n")
    print("Projection complete", len(projected), report["n_scenarios"], "scenarios", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("results/external_inputs"))
    args = parser.parse_args()
    project(args.source, args.out)
