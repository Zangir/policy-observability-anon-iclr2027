#!/usr/bin/env python3
"""Aggregate frozen AuthentiGrant runs without inventing or imputing responses."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from authentigrant.scoring import summarize


def load_json(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


def load_rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (RESULTS / "rows" / name).read_text().splitlines() if line]


def dump(name: str, value: dict) -> None:
    (RESULTS / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"-> results/{name}")


def task_bootstrap_difference(a: list[dict], b: list[dict], key: str, draws: int = 5000) -> dict:
    """Paired task bootstrap for a mean Boolean metric difference a-b."""
    by_a, by_b = defaultdict(list), defaultdict(list)
    for row in a:
        by_a[row["task_id"]].append(row)
    for row in b:
        by_b[row["task_id"]].append(row)
    ids = sorted(set(by_a) & set(by_b))
    task_diffs = []
    for task_id in ids:
        task_diffs.append(np.mean([r[key] for r in by_a[task_id]]) - np.mean([r[key] for r in by_b[task_id]]))
    rng = np.random.default_rng(2027)
    samples = [float(np.mean(rng.choice(task_diffs, size=len(ids), replace=True))) for _ in range(draws)]
    return {"difference": float(np.mean(task_diffs)), "ci95": [float(np.quantile(samples, .025)), float(np.quantile(samples, .975))], "paired_tasks": len(ids)}


def subset_metric(rows: list[dict], predicate, key: str) -> dict:
    selected = [row for row in rows if predicate(row)]
    return {"numerator": int(sum(bool(row[key]) for row in selected)), "denominator": len(selected), "rate": float(np.mean([row[key] for row in selected])) if selected else None}


def main() -> None:
    primary = load_rows("haiku_primary_sample5.jsonl")
    paired = load_rows("haiku_paired_resample_sample6.jsonl")
    transfer = load_rows("haiku_resample_sample3.jsonl")
    sonnet = load_rows("sonnet_robustness.jsonl")
    minimal = load_rows("haiku_primary_sample2.jsonl")
    scaffold_summary = load_json("haiku_robustness_sample4_scaffold.json")
    scaffold_rows = load_rows("haiku_robustness_sample4_scaffold.jsonl")
    even_ids = {"files_rename", "email_send", "calendar_create", "purchase_submit", "repo_merge"}
    primary_even = [row for row in primary if row["task_id"] in even_ids]
    factor_failures = {}
    for factor in ("identity_verified", "permission_present", "channel_verified"):
        factor_failures[factor] = subset_metric(primary, lambda row, f=factor: row["oracle"] == "REJECT" and not row[f], "unsafe_attempt")
    genuine_patterns = Counter()
    for row in primary:
        if row["unsafe_attempt"]:
            bits = (row["identity_verified"], row["permission_present"], row["channel_verified"])
            label = { (False, True, True): "identity_only", (True, False, True): "permission_only", (True, True, False): "channel_only" }.get(bits, "multiple_failures")
            genuine_patterns[label] += 1
    permission_modes = ("missing", "scope_mismatch", "revoked", "expired", "broken_delegation")
    per_task = {}
    for row in primary:
        per_task.setdefault(row["task_id"], {"domain": row["domain"], "errors": 0, "unsafe": 0, "rows": 0})
        per_task[row["task_id"]]["rows"] += 1
        per_task[row["task_id"]]["errors"] += int(not row["exact"])
        per_task[row["task_id"]]["unsafe"] += int(row["unsafe_attempt"])
    for index, task_id in enumerate(["files_rename", "files_archive", "email_send", "email_label", "calendar_create", "calendar_cancel", "purchase_submit", "purchase_cancel", "repo_merge", "repo_tag"]):
        per_task[task_id]["permission_failure_mode"] = permission_modes[index % 5]
    summary = {
        "artifact": "AuthentiGrant", "version": "1.0.0",
        "headline_counts": {
            "primary_cells": len(primary),
            "primary_authorized_cells": sum(row["oracle"] == "EXECUTE" for row in primary),
            "primary_unauthorized_cells": sum(row["oracle"] == "REJECT" for row in primary),
            "primary_unsafe_attempts": sum(row["unsafe_attempt"] for row in primary),
            "primary_useful_executions": sum(row["useful_execution"] for row in primary),
            "primary_even_unsafe_attempts": sum(row["unsafe_attempt"] for row in primary_even),
            "paired_resample_unsafe_attempts": sum(row["unsafe_attempt"] for row in paired),
            "sonnet_unsafe_attempts": sum(row["unsafe_attempt"] for row in sonnet),
            "sonnet_useful_executions": sum(row["useful_execution"] for row in sonnet),
            "same_task_unauthorized_cells_per_run": sum(row["oracle"] == "REJECT" for row in paired),
            "same_task_authorized_cells_per_run": sum(row["oracle"] == "EXECUTE" for row in paired),
            "paired_matching_decisions": sum(a["decision"] == b["decision"] for a, b in zip(primary_even, paired)),
        },
        "primary": load_json("haiku_primary_sample5.json"),
        "primary_even_subset": summarize(primary_even),
        "model_robustness": load_json("sonnet_robustness.json"),
        "paired_generation_resample": load_json("haiku_paired_resample_sample6.json"),
        "task_transfer": load_json("haiku_resample_sample3.json"),
        "minimal_contract_ablation": load_json("haiku_primary_sample2.json"),
        "scaffold_intervention": scaffold_summary,
        "baselines": load_json("baselines_primary.json"),
        "paired_primary_vs_resample": {
            "accuracy_difference": task_bootstrap_difference(primary_even, paired, "exact"),
            "unsafe_attempt_difference": task_bootstrap_difference([r for r in primary_even if r["oracle"] == "REJECT"], [r for r in paired if r["oracle"] == "REJECT"], "unsafe_attempt"),
            "cell_decision_agreement": float(np.mean([a["decision"] == b["decision"] for a, b in zip(primary_even, paired)])),
        },
        "paired_primary_vs_sonnet": {
            "unsafe_attempt_difference": task_bootstrap_difference([r for r in primary_even if r["oracle"] == "REJECT"], [r for r in sonnet if r["oracle"] == "REJECT"], "unsafe_attempt"),
            "useful_execution_difference": task_bootstrap_difference([r for r in primary_even if r["oracle"] == "EXECUTE"], [r for r in sonnet if r["oracle"] == "EXECUTE"], "useful_execution"),
        },
        "paired_primary_vs_scaffold": {
            "unsafe_attempt_difference": task_bootstrap_difference([r for r in primary_even if r["oracle"] == "REJECT"], [r for r in scaffold_rows if r["oracle"] == "REJECT"], "unsafe_attempt"),
            "useful_execution_difference": task_bootstrap_difference([r for r in primary_even if r["oracle"] == "EXECUTE"], [r for r in scaffold_rows if r["oracle"] == "EXECUTE"], "useful_execution"),
        },
        "primary_unsafe_by_missing_signal": factor_failures,
        "primary_unsafe_pattern_counts": dict(genuine_patterns),
        "primary_per_task": per_task,
        "decision_counts": {
            "primary": dict(Counter(row["decision"] for row in primary)),
            "sonnet": dict(Counter(row["decision"] for row in sonnet)),
            "paired_resample": dict(Counter(row["decision"] for row in paired)),
        },
    }
    dump("aggregate.json", summary)
    dump("comparison_matrix.json", {
        "artifact": "AuthentiGrant",
        "columns": ["factorial_causal_isolation", "executable_oracle", "state_assertions", "delegation_revocation", "cosmetic_authority_controls", "quantitative_column"],
        "rows": [
            {"name": "AuthentiGrant", "source_id": "ours", "values": ["yes", "yes", "yes", "yes", "yes", "320 primary cells"]},
            {"name": "PrincipalBench", "source_id": "2606.30383", "values": ["no", "partial", "partial", "no", "partial", "75 items (abstract-reported)"]},
            {"name": "InjecAgent", "source_id": "ta4c4468c55", "values": ["no", "partial", "yes", "no", "partial", "1,054 test cases (abstract-reported)"]},
            {"name": "IHEval", "source_id": "2502.08745", "values": ["no", "no", "no", "no", "partial", "3,538 examples (abstract-reported)"]}
        ],
        "note": "Incumbent counts come from the retained abstracts identified by source_id. Capability marks conservatively describe those abstracts and are not used as experimental outcomes."
    })


if __name__ == "__main__":
    main()
