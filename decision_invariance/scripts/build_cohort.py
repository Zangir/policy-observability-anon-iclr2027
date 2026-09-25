"""Deterministic decision-screen cohort from tau2-bench-verified shipped retail trajectories.

ZERO model calls. Extracts interface-valid tool-call proposals as frozen packets in the
exact schema consumed by the shipped decision_screen/render.py, reconstructing the
agent-visible system prompt byte-faithfully from tau2. See logs/deviations.md D1.

Frozen rule (criterion): from the pinned retail results file, take the 3 retail task_ids
selected by a seeded shuffle (SEED) of the sorted task_ids present; extract every
interface-valid typed tool-call proposal across all trials of those tasks; deduplicate by
the sha256 of the projected packet (identical history+candidate collapse); no selection
uses rewards, labels, or outcomes.
"""
from __future__ import annotations
import hashlib, json, os, random, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]  # decision_invariance/ repo root (portable)
TAU2 = Path(os.environ.get("TAU2_ROOT", str(REPO / "upstream/tau2-bench-verified")))
DSW = REPO / "lib"
sys.path.insert(0, str(DSW))
# tau2 is expected on the active environment (pip install -e $TAU2_ROOT); src added below as fallback
sys.path.insert(0, str(TAU2 / "src"))

from decision_screen.render import render, sha as rsha, effect, project  # shipped, verbatim

SEED = 2026091901
RESULTS = TAU2 / "data/tau2/results/final/gpt-4.1-2025-04-14_retail_default_gpt-4.1-2025-04-14_4trials.json"
CONTEXT_COMPLETENESS = ("Exact actor payload messages and tools; only requested_model and "
    "requested_settings omitted. No future outcome or private evaluator/user instructions added.")
OUT = REPO / "results/decision_invariance"


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    return sha_bytes(Path(p).read_bytes())


def build_system_prompt(policy: str) -> str:
    from tau2.agent.llm_agent import LLMAgent
    from tau2.domains.retail.environment import get_environment
    env = get_environment()
    agent = LLMAgent(tools=env.get_tools(), domain_policy=policy)
    return agent.system_prompt


def project_message(m: dict) -> dict:
    """tau2 message -> {role, content, [tool_calls], [tool_call_id]} (render-allowed keys only)."""
    role = m["role"]
    if role == "tool":
        return {"role": "tool", "content": m.get("content"), "tool_call_id": m.get("id")}
    out = {"role": role, "content": m.get("content")}
    tcs = m.get("tool_calls")
    if tcs:
        out["tool_calls"] = [{"id": c["id"], "name": c["name"], "arguments": c.get("arguments") or {}}
                             for c in tcs]
    return out


def main():
    if OUT.exists():
        raise SystemExit("cohort output exists; preserve and version (delete to rebuild)")
    data = json.loads(RESULTS.read_text())
    policy = (TAU2 / "data/tau2/domains/retail/policy.md").read_text()
    system_prompt = build_system_prompt(policy)
    tool_schemas = json.loads((REPO / "results/retail_tool_schemas.json").read_text())
    tool_names = {s["function"]["name"] for s in tool_schemas}
    policy_sha = sha_bytes(policy.encode())

    sims = data["simulations"]
    task_ids = sorted({str(s["task_id"]) for s in sims}, key=lambda x: int(x))
    shuffled = list(task_ids)
    random.Random(SEED).shuffle(shuffled)
    chosen_tasks = sorted(shuffled[:3], key=lambda x: int(x))

    packets = []
    seen = set()
    for s in sims:
        task = str(s["task_id"])
        if task not in chosen_tasks:
            continue
        episode = f"{task}::trial{s.get('trial')}::{s.get('id')}"
        history = [{"role": "system", "content": system_prompt}]
        for m in s["messages"]:
            role = m.get("role")
            tcs = m.get("tool_calls") if role == "assistant" else None
            if role == "assistant" and tcs:
                group_size = len(tcs)
                for gi, call in enumerate(tcs):
                    if call["name"] not in tool_names:
                        continue
                    packet_body = {
                        "group_index": gi, "group_size": group_size,
                        "policy_text": policy, "tool_schemas": tool_schemas,
                        "actor_visible_messages": [dict(x) for x in history],
                        "candidate": {"id": call["id"], "name": call["name"],
                                      "arguments": call.get("arguments") or {}},
                        "context_completeness": CONTEXT_COMPLETENESS,
                    }
                    full = dict(packet_body)
                    full.update(packet_version=1, packet_id="", proposal_group_id="",
                                policy_sha256=policy_sha, proposal_status="interface_valid",
                                decision=None)
                    project(full)  # shipped validator: raises on any schema violation
                    body_sha = sha_bytes(json.dumps(packet_body, ensure_ascii=False,
                                                    sort_keys=True).encode())
                    if body_sha in seen:
                        continue
                    seen.add(body_sha)
                    pid = body_sha[:32]
                    full["packet_id"] = pid
                    full["proposal_group_id"] = sha_bytes((episode + str(m.get("turn_idx"))).encode())[:32]
                    packets.append({"packet_id": pid, "cohort": "v2", "source_task": task,
                                    "episode_id": episode,
                                    "action_effect": effect(call["name"]),
                                    "tool_name": call["name"], "body_sha256": body_sha,
                                    "packet": full})
            # advance history with the projected message (all roles)
            history.append(project_message(m))

    # persist
    OUT.mkdir(parents=True)
    (OUT / "packets").mkdir()
    manifest = {"schema_version": 1, "seed": SEED,
                "results_file": str(RESULTS.relative_to(TAU2)),
                "results_sha256": sha_file(RESULTS),
                "tau2_head": "864350a8971a8f8ee9e7b8472e2edc380a806b0c",
                "retail_policy_sha256": policy_sha,
                "system_prompt_sha256": sha_bytes(system_prompt.encode()),
                "system_prompt_len": len(system_prompt),
                "tool_schemas_sha256": sha_file(REPO / "results/retail_tool_schemas.json"),
                "n_tools": len(tool_schemas),
                "chosen_tasks": chosen_tasks, "candidate_task_ids": task_ids,
                "n_packets_typed": len(packets),
                "effects": {}, "packets": []}
    from collections import Counter
    manifest["effects"] = dict(Counter(p["action_effect"] for p in packets))
    for p in packets:
        # Preserve NATURAL (non-alphabetical) key order on disk so the R arm (original
        # order) differs from the C arm (canonical/sorted). Dedup used sorted-key hashing.
        raw = json.dumps(p["packet"], ensure_ascii=False, indent=2).encode()
        (OUT / "packets" / f"{p['packet_id']}.json").write_bytes(raw)
        manifest["packets"].append({k: p[k] for k in
            ("packet_id", "cohort", "source_task", "episode_id", "action_effect",
             "tool_name", "body_sha256")})
    (OUT / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"chosen_tasks": chosen_tasks, "n_packets_typed": len(packets),
                      "effects": manifest["effects"],
                      "by_task": dict(Counter(p["source_task"] for p in packets))}, indent=2))


if __name__ == "__main__":
    main()
