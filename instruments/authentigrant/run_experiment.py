#!/usr/bin/env python3
"""Run AuthentiGrant models or deterministic baselines on a frozen partition."""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from authentigrant.backends import run_rows
from authentigrant.scenarios import FACTOR_NAMES, TASKS, build_rows, validate_grid
from authentigrant.scoring import score_rows, summarize


PARTITIONS = {
    "primary": list(range(10)),
    "robustness": [0, 2, 4, 6, 8],
    "resample": [1, 3, 5, 7, 9],
    "paired_resample": [0, 2, 4, 6, 8],
    "pilot": [0, 8],
}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"-> {path}")


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    print(f"-> {path}")


def run_one(method: str, partition: str, sample_idx: int, smoke: bool, workers: int, prompt_mode: str) -> tuple[dict, list[dict]]:
    indices = [0] if smoke else PARTITIONS[partition]
    rows = build_rows(indices)
    validate_grid(rows)
    started = time.time()
    responses = run_rows(rows, method, sample_idx, workers, prompt_mode)
    scored = score_rows(rows, responses)
    metrics = summarize(scored, draws=200 if smoke else 2000)
    metrics.update({
        "artifact": "AuthentiGrant", "version": "1.0.0", "method": method,
        "partition": "smoke" if smoke else partition, "sample_idx": sample_idx,
        "prompt_mode": prompt_mode,
        "runtime_seconds": round(time.time() - started, 3),
    })
    return metrics, scored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=["haiku", "sonnet", "oracle", "always_execute", "always_reject", "baselines"], default="oracle")
    parser.add_argument("--partition", choices=sorted(PARTITIONS), default="primary")
    parser.add_argument("--sample-idx", type=int, default=0)
    parser.add_argument("--prompt-mode", choices=["minimal", "principles", "scaffold"], default="principles")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()
    random.seed(args.seed)
    out = Path(args.out)
    stats = {
        "artifact": "AuthentiGrant", "version": "1.0.0", "base_tasks": len(TASKS),
        "domains": len({task.domain for task in TASKS}), "factor_count": len(FACTOR_NAMES),
        "factorial_cells_per_task": 32, "full_rows": len(TASKS) * 32,
        "oracle_authorized_rows": sum(row["identity_verified"] and row["permission_present"] and row["channel_verified"] for row in build_rows()),
    }
    write_json(out / "benchmark_stats.json", stats)
    methods = ["oracle", "always_execute", "always_reject"] if args.method == "baselines" else [args.method]
    combined = {}
    for method in methods:
        metrics, rows = run_one(method, args.partition, args.sample_idx, args.smoke, args.workers, args.prompt_mode)
        combined[method] = metrics
        label = "smoke" if args.smoke else f"{method}_{args.partition}"
        if args.sample_idx:
            label += f"_sample{args.sample_idx}"
        if args.prompt_mode != "principles":
            label += f"_{args.prompt_mode}"
        write_json(out / f"{label}.json", metrics)
        write_rows(out / "rows" / f"{label}.jsonl", rows)
    if args.method == "baselines":
        write_json(out / f"baselines_{args.partition}.json", {"artifact": "AuthentiGrant", "methods": combined})


if __name__ == "__main__":
    main()
