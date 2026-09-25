"""Audit complete primary-source tables; cross-suite differences remain descriptive."""
from itertools import combinations
import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAMES = {"GPT-5.5": "GPT-5.5", "Gemini 3.1 Pro": "Gemini 3.1 Pro",
               "DeepSeek-V4-Pro": "DeepSeek-V4-Pro", "MiniMax-M3": "MiniMax-M3",
               "MiniMax M3": "MiniMax-M3", "Qwen3.7-Plus": "Qwen3.7-Plus",
               "GLM-5.2": "GLM-5.2", "Kimi K2.6": "Kimi K2.6",
               "Claude Opus 4.7": "Claude Opus 4.7"}
ACT_MODELS = {"zjuicsr/gpt-5.5": "GPT-5.5", "deepseek/deepseek-v4-pro": "DeepSeek-V4-Pro",
              "minimax/MiniMax-M3": "MiniMax-M3", "taisure/qwen3.7-plus": "Qwen3.7-Plus",
              "taisure/glm-5.2": "GLM-5.2", "taisure/kimi-k2.6": "Kimi K2.6"}
HARNESS = {"openclaw": "OpenClaw", "hermes": "Hermes", "claudecode": "Claude Code"}


def table_rows(path, caption_id):
    soup = BeautifulSoup(path.read_text(), "html.parser")
    caption = soup.find(id=caption_id)
    assert caption is not None
    table = caption.find_previous("table")
    return [[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            for row in table.find_all("tr")]


def main():
    inputs = ROOT / "results/external_inputs"
    plan = json.loads((inputs / "CROSS_BENCHMARK_AMENDMENT.json").read_text())
    for name, expected in plan["sources_sha256"].items():
        assert hashlib.sha256((inputs / (name + "_primary.html")).read_bytes()).hexdigest() == expected
    agents = []
    harness = None
    for cells in table_rows(inputs / "agents4d_primary.html", "A5.T14")[1:]:
        harness = cells[0] or harness
        counts = dict(zip(["unsafe", "defense", "exposed_safe", "unconfirmed_safe", "inconclusive", "complete"],
                          [int(value) for value in cells[2:8]]))
        n = sum(value for name, value in counts.items() if name != "complete")
        assert n == 328 and 0 <= counts["complete"] <= n
        u, d, e, i = [counts[name] for name in ["unsafe", "defense", "exposed_safe", "inconclusive"]]
        recomputed = [100 * u / n, 100 * u / (u + d + e), 100 * (d + e) / (n - i), 100 * counts["complete"] / n]
        reported = [float(value) for value in cells[8:12]]
        assert all(abs(a - b) <= .00500001 for a, b in zip(recomputed, reported)), cells
        agents.append({"harness": harness, "model": MODEL_NAMES[cells[1]], "counts": counts,
                       "n": n, "asr": u / n, "utility": counts["complete"] / n,
                       "asr_inconclusive_bounds": [u / n, (u + i) / n],
                       "reported_metric_percentages": reported})
    assert len(agents) == 20
    risk = []
    for cells in table_rows(inputs / "harnessrisk_primary.html", "S4.T2")[1:]:
        if len(cells) == 1:
            harness = cells[0]
            continue
        values = [[float(x) for x in cell.split()[:2]] for cell in cells[1:]]
        risk.append({"harness": harness, "model": MODEL_NAMES[cells[0]],
                     "asr": values[0][0] / 100, "utility": values[1][0] / 100,
                     "reported_mean_sd_percentages": dict(zip(["asr", "utility", "persistence", "detection"], values))})
    assert len(risk) == 14
    act = json.loads((ROOT / "results/actbench_rank_audit.json").read_text())
    act_rows = [{"harness": HARNESS[row["backend"]], "model": ACT_MODELS[row["model"]],
                 "asr": row["asr"], "utility": row["task_pass"]}
                for row in act["profile_rows"] if row["context"] == "ALL"
                and row["backend"] in HARNESS and row["model"] in ACT_MODELS]
    sources = {"ActBench": act_rows, "AgentS4D": agents, "HarnessRisk": risk}
    comparisons = []
    for first, second in combinations(sources, 2):
        panels = [{(row["harness"], row["model"]): row for row in sources[name]} for name in [first, second]]
        common = sorted(set(panels[0]) & set(panels[1]))
        for left, right in combinations(common, 2):
            if left[0] != right[0] and left[1] != right[1]:
                continue
            gaps = [panel[left]["asr"] - panel[right]["asr"] for panel in panels]
            comparisons.append({"first_source": first, "second_source": second,
                                "left": list(left), "right": list(right),
                                "comparison_type": "models_within_harness" if left[0] == right[0] else "harnesses_within_model",
                                "asr_gaps_pp": [100 * value for value in gaps],
                                "observed_strict_reversal": gaps[0] * gaps[1] < -1e-12})
    total = {key: sum(row["counts"][key] for row in agents) for key in agents[0]["counts"]}
    report = {"agents4d": agents, "harnessrisk": risk, "actbench_shared_nominal_configs": act_rows,
              "agents4d_counts_sum": total, "n_agents4d_metrics_reproduced": 80,
              "cross_source_comparisons": comparisons,
              "n_cross_source_comparisons": len(comparisons),
              "n_observed_reversals": sum(row["observed_strict_reversal"] for row in comparisons),
              "source_hashes": plan["sources_sha256"],
              "scope": "Adaptive complete-table comparison of identical nominal version names. Models may have different providers/routes; harness versions, tasks, judges, budgets, dates and filtering differ. Reversals describe recorded suite-specific orderings, not controlled causal effects or population-significance claims. AgentS4D and HarnessRisk rows are reported source results, not reexecuted trajectories. Source SD is not a confidence interval. Inconclusive bounds cover all possible binary labels for released unknown counts only."}
    (ROOT / "results/reported_panel_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print("All80AgentS4Dmetrics reproduced;", len(comparisons), "complete comparable source gaps;",
          report["n_observed_reversals"], "descriptive reversals")


if __name__ == "__main__":
    main()
