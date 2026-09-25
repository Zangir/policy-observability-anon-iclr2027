#!/usr/bin/env python3
"""Run one ScaffoldRankBench model-scaffold cell."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scaffold_rank_bench.scaffolds import SCAFFOLDS, run
from scaffold_rank_bench.scenarios import build_benchmark, write_dataset
from scaffold_rank_bench.scoring import summarize
from scaffold_rank_bench.semantics import oracle_checks

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["claude", "oracle"], default="claude")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--scaffold", choices=SCAFFOLDS, required=True)
    ap.add_argument("--sample-idx", type=int, default=0)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--families", type=int, help="take this many complete family pairs")
    args = ap.parse_args()
    stats = write_dataset(ROOT / "data" / "benchmark_v1.jsonl")
    items = build_benchmark()
    if args.families is not None:
        keep = {row["family"] for row in items[:2 * args.families]}
        items = [row for row in items if row["family"] in keep]
    if args.limit is not None:
        items = items[:args.limit]
    rows = run(items, args.scaffold, args.backend, args.model,
               ROOT / "data" / "llm_cache", args.sample_idx)
    for row in rows:
        row.update({"backend": args.backend, "model": args.model,
                    "scaffold": args.scaffold, "sample_idx": args.sample_idx})
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    (results / f"{args.run_name}_rows.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    summary = {"run_name": args.run_name, "backend": args.backend,
               "model": args.model, "scaffold": args.scaffold,
               "sample_idx": args.sample_idx, "dataset": stats,
               "oracle": oracle_checks(build_benchmark()), **summarize(rows)}
    (results / f"{args.run_name}.json").write_text(json.dumps(summary, indent=2) + "\n")
    (results / "dataset_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
