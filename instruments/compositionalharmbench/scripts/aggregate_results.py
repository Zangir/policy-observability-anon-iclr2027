#!/usr/bin/env python3
"""Aggregate persisted benchmark runs into paper-ready JSON facts."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from compositional_harm_bench.policy import locally_allowed
from compositional_harm_bench.scenarios import build_benchmark
from compositional_harm_bench.simulator import replay

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def load(name: str) -> dict:
    return json.loads((RESULTS / f"{name}.json").read_text())


def rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (RESULTS / f"{name}_rows.jsonl").read_text().splitlines()]


def comp_attempts(records: list[dict]) -> dict[str, bool]:
    return {r["id"]: r["harm"] for r in records
            if r["mode"] == "unprotected" and r["variant"] == "compositional"}


def factor_rates(records: list[dict]) -> dict:
    comp = [r for r in records if r["mode"] == "unprotected" and
            r["variant"] == "compositional"]
    output = {}
    for key in ("mechanism", "domain", "horizon", "indirect", "memory", "multi_agent"):
        grouped = defaultdict(list)
        for row in comp:
            grouped[str(row[key]).lower()].append(row["harm"])
        output[key] = {value: round(100 * sum(flags) / len(flags), 3)
                       for value, flags in sorted(grouped.items())}
    return output


def main() -> None:
    primary, resample = load("haiku_primary"), load("haiku_resample")
    sonnet, explicit = load("sonnet_primary"), load("haiku_explicit")
    primary_rows, resample_rows = rows("haiku_primary"), rows("haiku_resample")
    first, second = comp_attempts(primary_rows), comp_attempts(resample_rows)
    agreement = 100 * sum(first[key] == second[key] for key in first) / len(first)
    accepted_both = sum(first[key] and second[key] for key in first)
    clean_primary = [r for r in primary_rows if r["mode"] == "approval" and
                     r["variant"] == "clean"]
    aggregate = {
        "headline": {
            "accepted_compositional": int(primary["composition_attempt_rate"] * 20 / 100),
            "compositional_total": 20,
            "local_harm_rate": primary["by_mode"]["local_filter"]["compositional_harm_rate"],
            "local_harm_ci95": primary["by_mode"]["local_filter"]["compositional_harm_ci95"],
            "trajectory_harm_rate": primary["by_mode"]["trajectory_monitor"]["compositional_harm_rate"],
            "clean_utility_local": primary["by_mode"]["local_filter"]["clean_utility"],
            "clean_utility_trajectory": primary["by_mode"]["trajectory_monitor"]["clean_utility"],
            "harm_reduction_pp": round(primary["by_mode"]["local_filter"]["compositional_harm_rate"] - primary["by_mode"]["trajectory_monitor"]["compositional_harm_rate"], 3),
        },
        "runs": {"haiku_primary": primary, "haiku_resample": resample,
                 "sonnet_primary": sonnet, "haiku_explicit": explicit},
        "replication": {"primary_rate": primary["composition_attempt_rate"],
                        "resample_rate": resample["composition_attempt_rate"],
                        "item_agreement": round(agreement, 3),
                        "accepted_in_both": accepted_both},
        "approval": {"mean_reviews_per_clean_item": round(sum(r["reviews"] for r in clean_primary) / len(clean_primary), 3),
                     "harm_rate": primary["by_mode"]["approval"]["compositional_harm_rate"]},
        "diagnostics": factor_rates(primary_rows),
    }
    (RESULTS / "aggregate.json").write_text(json.dumps(aggregate, indent=2) + "\n")
    dataset = primary["dataset"] | {"evaluation_items": primary["items"],
                                    "domains": 5, "mechanisms": 4,
                                    "horizons": [2, 4, 6, 8]}
    (RESULTS / "dataset_stats.json").write_text(json.dumps(dataset, indent=2) + "\n")
    benchmark = build_benchmark()
    variants = {name: [row for row in benchmark if row["variant"] == name]
                for name in ("clean", "compositional", "atomic")}
    oracle = {
        "clean_safe": sum(not replay(row["actions"], "unprotected")["harm"]
                          for row in variants["clean"]),
        "compositional_locally_allowed": sum(all(locally_allowed(action)
            for action in row["actions"]) for row in variants["compositional"]),
        "compositional_harm_unprotected": sum(replay(row["actions"], "unprotected")["harm"]
            for row in variants["compositional"]),
        "compositional_harm_local_filter": sum(replay(row["actions"], "local_filter")["harm"]
            for row in variants["compositional"]),
        "atomic_blocked_local_filter": sum(replay(row["actions"], "local_filter")["blocked_at"]
            is not None for row in variants["atomic"]),
        "all_harms_blocked_trajectory": sum(replay(row["actions"], "trajectory_monitor")["blocked_at"]
            is not None for name in ("compositional", "atomic") for row in variants[name]),
        "per_variant": 640,
    }
    (RESULTS / "oracle_full.json").write_text(json.dumps(oracle, indent=2) + "\n")
    print(json.dumps(aggregate["headline"], indent=2))


if __name__ == "__main__":
    main()
