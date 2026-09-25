"""Reanalyze the full pinned public score panel without new model or judge calls."""
from collections import Counter
import json
from pathlib import Path

import numpy as np
from scaffold_rank_bench.external_ranking import task_scores, profiles, pairwise, factorial_bounds

ROOT = Path(__file__).resolve().parent


def main():
    directory = ROOT / "results/external_inputs"
    rows = json.loads((directory / "actbench_projection.json").read_text())
    metadata = {row["task_id"]: row for row in json.loads((directory / "actbench_task_metadata.json").read_text())}
    configs, tasks, values = task_scores(rows)
    config_metadata = {row["combo_id"]: {key: row[key] for key in ["model", "backend"]} for row in rows}
    estimates, draws, scenarios, families = profiles(values, tasks, metadata)
    print("Scenario bootstrap complete", len(scenarios), flush=True)
    panels = {"models_on_openclaw": [i for i, config in enumerate(configs) if config_metadata[config]["backend"] == "openclaw"],
              "harnesses_with_deepseek": [i for i, config in enumerate(configs) if config_metadata[config]["model"] == "deepseek/deepseek-v4-pro"]}
    comparisons = {}
    reversals = []
    for name, indices in panels.items():
        panel = pairwise(configs, indices, estimates, draws, families)
        comparisons[name] = panel
        grouped = {}
        for row in panel["comparisons"]:
            grouped.setdefault((row["left"], row["right"], row["measure"]), []).append(row)
        for key, group in grouped.items():
            risk_groups = [row for row in group if row["context"] in families]
            positive = [row["context"] for row in risk_groups if row["difference_pp"] > 1e-10]
            negative = [row["context"] for row in risk_groups if row["difference_pp"] < -1e-10]
            certain_positive = [row["context"] for row in risk_groups if row["simultaneous_ci95_pp"][0] > 0]
            certain_negative = [row["context"] for row in risk_groups if row["simultaneous_ci95_pp"][1] < 0]
            if positive and negative:
                reversals.append({"panel": name, "left": key[0], "right": key[1], "measure": key[2],
                                  "positive_families": positive, "negative_families": negative,
                                  "simultaneous_positive": certain_positive, "simultaneous_negative": certain_negative,
                                  "simultaneously_resolved_reversal": bool(certain_positive and certain_negative)})
        print(name, len(indices), "configs", panel["n_comparisons"], "contrasts", flush=True)
    profile_rows = []
    for context in estimates:
        for i, config in enumerate(configs):
            profile_rows.append({"context": context, "combo_id": config, **config_metadata[config],
                                 "safety": float(estimates[context][i, 0]),
                                 "asr": float(1 - estimates[context][i, 0]),
                                 "task_pass": float(estimates[context][i, 1]),
                                 "balanced": float(estimates[context][i, 2]),
                                 "continuous_balanced": float(estimates[context][i, 3]),
                                 "pointwise_ci95": np.percentile(draws[context][:, i], [2.5, 97.5], axis=0).tolist()})
    selections = []
    for name, indices in panels.items():
        for context in estimates:
            safety_order = sorted(indices, key=lambda i: (-estimates[context][i, 0], configs[i]))
            balanced_order = sorted(indices, key=lambda i: (-estimates[context][i, 2], configs[i]))
            pareto = [i for i in indices if not any(
                np.all(estimates[context][j, :2] >= estimates[context][i, :2] - 1e-12)
                and np.any(estimates[context][j, :2] > estimates[context][i, :2] + 1e-12)
                for j in indices if j != i)]
            selections.append({"panel": name, "context": context,
                               "safety_order": [configs[i] for i in safety_order],
                               "balanced_order": [configs[i] for i in balanced_order],
                               "pareto_configs": [configs[i] for i in pareto],
                               "ordering_note": "Ties are broken by configuration ID only for display, not evidence of superiority."})
    report = {"n_rows": len(rows), "n_tasks": len(tasks), "n_scenarios": len(scenarios),
              "n_configs": len(configs), "n_behavior_families": len(families),
              "n_attack_rows": sum(row["role"] == "attack" for row in rows),
              "n_clean_rows": sum(row["role"] == "clean" for row in rows),
              "role_counts": dict(Counter(row["role"] for row in rows)),
              "family_task_counts": dict(Counter(metadata[task]["behavior_id"] for task in tasks)),
              "thresholds": dict(Counter(row["threshold"] for row in rows)),
              "profile_rows": profile_rows, "pairwise_panels": comparisons,
              "risk_family_reversals": reversals, "selections": selections,
              "factorial": factorial_bounds(configs, config_metadata, estimates["ALL"]),
              "analysis": {"bootstrap": 5000, "seed": 20270913, "cluster": "scenario_id",
                           "simultaneous_scope": "Within each panel, all pairwise safety and balanced-score gaps across ALL,15families,equal-family and15leave-one-family-out contexts. Maximum absolute bootstrap deviation gives common symmetric95band.",
                           "estimand": "Observed task-average safety and clean utility. Risk-family reweighting is not a harness intervention. Balanced score is one explicitly declared tradeoff, not the unique security objective.",
                           "provenance": "Saved author scores reanalyzed here; all source Parquet hashes verified, original trajectory hashes unresolved for two configurations. No new execution or judge labels."}}
    (ROOT / "results/actbench_rank_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    for row in profile_rows:
        if row["context"] == "ALL":
            print(row["combo_id"], "ASR", round(100 * row["asr"], 3), "utility", round(100 * row["task_pass"], 3), "balanced", round(100 * row["balanced"], 3))
    print("Risk reversals", len(reversals), "simultaneous", sum(row["simultaneously_resolved_reversal"] for row in reversals), flush=True)


if __name__ == "__main__":
    main()
