"""Invariance analysis: excess disagreement of candidate-first (K) vs canonical (C),
secondary R vs C, against the repeated-input (within-arm) baseline.

Reuses the shipped pair_statistics() verbatim:
  cross_disagreement  = mean over 4 cross pairs of 1[decision_a != decision_b]
  within_disagreement = mean of the two within-arm repeat disagreements
  excess_disagreement = cross - within
Descriptive, finite-cohort; item-bootstrap 95% CIs over packets. No population inference.
"""
from __future__ import annotations
import json, sys, statistics, hashlib, random
from collections import defaultdict, Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]  # decision_invariance/ repo root (portable)
sys.path.insert(0, str(REPO / "lib"))
from decision_screen.analyze import pair_statistics  # shipped, verbatim
from decision_screen.render import strict_json

OUT = REPO / "results/decision_invariance"
DECISIONS = ("ALLOW", "BLOCK", "ASK")
CONTRASTS = {"K-C": ("K", "C"), "R-C": ("R", "C")}


def load_decisions(model):
    """packet_id -> {(arm, rep): decision or None}. Uses arm_map to assign each rendering to arms."""
    sched = json.loads((OUT / "schedule.json").read_text())
    arm_map = sched["arm_map"]  # packet_id -> {R:sha, C:sha, K:sha}
    cells = defaultdict(dict)
    meta_by_pkt = {}
    for it in sched["items"]:
        if it["model"] != model:
            continue
        pid = it["packet_id"]
        meta_by_pkt[pid] = {"source_task": it["source_task"], "action_effect": it["action_effect"],
                            "tool_name": it["tool_name"], "episode_id": it["episode_id"]}
        run = OUT / "calls" / model / it["item_id"]
        decision = None
        mp = run / "metadata.json"
        if mp.exists():
            m = json.loads(mp.read_text())
            if m.get("status") == "completed":
                decision = m.get("decision")
        # this rendering may serve several arms (only if collapsed); here arms are distinct
        for arm in it["rendering_arms"]:
            cells[pid][(arm, it["repetition"])] = decision
    return cells, meta_by_pkt, arm_map


def analyze_model(model):
    cells, meta, _ = load_decisions(model)
    per_packet = {"K-C": [], "R-C": []}
    packet_recs = []
    for pid, cd in cells.items():
        rec = {"packet_id": pid, **meta[pid], "arms_present": sorted({a for a, _ in cd})}
        for contrast, (a, b) in CONTRASTS.items():
            aa = [cd.get((a, 0)), cd.get((a, 1))]
            bb = [cd.get((b, 0)), cd.get((b, 1))]
            valid = all(x in DECISIONS for x in aa + bb)
            entry = {"contrast": contrast, "complete_valid": valid,
                     "arm_decisions": {f"{a}0": aa[0], f"{a}1": aa[1], f"{b}0": bb[0], f"{b}1": bb[1]}}
            if valid:
                entry.update(pair_statistics(aa, bb))
                per_packet[contrast].append({"packet_id": pid, "source_task": meta[pid]["source_task"],
                                             "action_effect": meta[pid]["action_effect"], **pair_statistics(aa, bb)})
            rec.setdefault("contrasts", {})[contrast] = entry
        packet_recs.append(rec)
    # aggregate + bootstrap
    def agg(vals, key):
        return statistics.mean([v[key] for v in vals]) if vals else None

    def bootstrap(vals, key, n=5000, seed=20260925):
        if not vals:
            return None
        rng = random.Random(seed)
        xs = [v[key] for v in vals]
        means = []
        for _ in range(n):
            samp = [xs[rng.randrange(len(xs))] for _ in xs]
            means.append(sum(samp) / len(samp))
        means.sort()
        return [round(means[int(0.025 * n)], 6), round(means[int(0.975 * n) - 1], 6)]

    summary = {"model": model, "contrasts": {}}
    for contrast in CONTRASTS:
        vals = per_packet[contrast]
        tasks = sorted({v["source_task"] for v in vals}, key=lambda x: int(x)) if vals else []
        task_macro = {}
        for k in ("cross_disagreement", "within_disagreement", "excess_disagreement"):
            tm = [statistics.mean([v[k] for v in vals if v["source_task"] == t]) for t in tasks]
            task_macro[k] = statistics.mean(tm) if tm else None
        summary["contrasts"][contrast] = {
            "complete_valid_packets": len(vals),
            "cross_disagreement_packet_weighted": agg(vals, "cross_disagreement"),
            "within_disagreement_packet_weighted": agg(vals, "within_disagreement"),
            "excess_disagreement_packet_weighted": agg(vals, "excess_disagreement"),
            "excess_disagreement_ci95_item_bootstrap": bootstrap(vals, "excess_disagreement"),
            "cross_disagreement_task_macro": task_macro["cross_disagreement"],
            "within_disagreement_task_macro": task_macro["within_disagreement"],
            "excess_disagreement_task_macro": task_macro["excess_disagreement"],
            "packets_with_any_cross_disagreement": sum(v["cross_disagreement"] > 0 for v in vals),
            "packets_with_positive_excess": sum(v["excess_disagreement"] > 0 for v in vals),
        }
    # decision distribution per arm
    dist = defaultdict(Counter)
    for pid, cd in cells.items():
        for (arm, rep), dec in cd.items():
            dist[arm][dec if dec in DECISIONS else "NO_VALID_DECISION"] += 1
    summary["decision_distribution_by_arm"] = {a: dict(c) for a, c in sorted(dist.items())}
    coverage = Counter()
    for pid, cd in cells.items():
        for (arm, rep), dec in cd.items():
            coverage["valid" if dec in DECISIONS else "invalid"] += 1
    summary["cell_coverage"] = dict(coverage)
    return summary, packet_recs


def main():
    models = [m for m in ("claude-haiku", "claude-sonnet", "codex")
              if (OUT / f"run_summary_{m}.json").exists()]
    all_summ = {}
    for model in models:
        summ, recs = analyze_model(model)
        all_summ[model] = summ
        (OUT / f"invariance_packets_{model}.json").write_text(json.dumps(recs, indent=2) + "\n")
    result = {"schema_version": 1, "cohort_manifest_sha256":
              hashlib.sha256((OUT / "cohort_manifest.json").read_bytes()).hexdigest(),
              "models_analyzed": models, "by_model": all_summ,
              "interpretation": "Finite-cohort descriptive serialization sensitivity vs repeated-input "
              "noise; no population inference, ranking, permission gold, or prevented historical action."}
    (OUT / "invariance_results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({m: {c: {"excess_pw": all_summ[m]["contrasts"][c]["excess_disagreement_packet_weighted"],
                              "excess_ci": all_summ[m]["contrasts"][c]["excess_disagreement_ci95_item_bootstrap"],
                              "valid_packets": all_summ[m]["contrasts"][c]["complete_valid_packets"]}
                          for c in CONTRASTS} for m in models}, indent=2))


if __name__ == "__main__":
    main()
