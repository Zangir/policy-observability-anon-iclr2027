"""Render R/C/K arms for the frozen cohort and build the decision-screen call schedule.

ZERO model calls. Reuses shipped decision_screen/render.py render() verbatim. Each packet
yields arms R (original key order), C (canonical/sorted), K (candidate-first); only unique
renderings are sent, each at repetitions 0 and 1, per model family.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]  # decision_invariance/ repo root (portable)
DSW = REPO / "lib"
sys.path.insert(0, str(DSW))
from decision_screen.render import render, sha as rsha, strict_json  # shipped, verbatim

OUT = REPO / "results/decision_invariance"
MODELS = ["claude-haiku", "claude-sonnet", "codex"]  # family 1 (haiku primary, sonnet robustness), family 2 (codex)


def main():
    manifest = json.loads((OUT / "cohort_manifest.json").read_text())
    rend_dir = OUT / "renderings"
    rend_dir.mkdir(exist_ok=True)
    schedule = []
    arm_stats = {"distinct_RCK": 0, "R_eq_C": 0, "R_eq_K": 0, "C_eq_K": 0}
    packet_arm_map = {}
    for entry in manifest["packets"]:
        pid = entry["packet_id"]
        packet = strict_json((OUT / "packets" / f"{pid}.json").read_bytes())
        arms = render(packet)  # {'R':bytes,'C':bytes,'K':bytes}
        digests = {a: rsha(b) for a, b in arms.items()}
        if len({digests["R"], digests["C"], digests["K"]}) == 3:
            arm_stats["distinct_RCK"] += 1
        arm_stats["R_eq_C"] += digests["R"] == digests["C"]
        arm_stats["R_eq_K"] += digests["R"] == digests["K"]
        arm_stats["C_eq_K"] += digests["C"] == digests["K"]
        packet_arm_map[pid] = digests
        unique = {}
        for arm, raw in arms.items():
            d = digests[arm]
            if d not in unique:
                (rend_dir / f"{pid}_{d}.json").write_bytes(raw)
                unique[d] = {"rendering_sha256": d, "bytes": len(raw),
                             "arms": [a for a in ("R", "C", "K") if digests[a] == d]}
        for model in MODELS:
            for d, info in unique.items():
                for rep in (0, 1):
                    schedule.append({
                        "packet_id": pid, "source_task": entry["source_task"],
                        "episode_id": entry["episode_id"], "action_effect": entry["action_effect"],
                        "tool_name": entry["tool_name"], "cohort": entry["cohort"],
                        "rendering_sha256": d, "rendering_arms": info["arms"],
                        "rendering_path": str((rend_dir / f"{pid}_{d}.json").relative_to(REPO)),
                        "model": model, "repetition": rep,
                        "item_id": rsha(f"{pid}:{d}:{model}:{rep}".encode()),
                    })
    if len({c["item_id"] for c in schedule}) != len(schedule):
        raise SystemExit("duplicate item_id")
    from collections import Counter
    by_model = Counter(c["model"] for c in schedule)
    sched = {"schema_version": 1, "models": MODELS, "arm_stats": arm_stats,
             "n_packets": len(manifest["packets"]),
             "planned_calls_total": len(schedule),
             "planned_calls_per_model": dict(by_model),
             "arm_map": packet_arm_map, "items": schedule}
    (OUT / "schedule.json").write_text(json.dumps(sched, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"arm_stats": arm_stats, "n_packets": len(manifest["packets"]),
                      "planned_calls_total": len(schedule),
                      "planned_calls_per_model": dict(by_model)}, indent=2))


if __name__ == "__main__":
    main()
