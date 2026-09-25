#!/usr/bin/env python3
"""Run CompositionalHarmBench and persist row-level plus aggregate results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from compositional_harm_bench.claude_llm import batch_call
from compositional_harm_bench.prompts import parse, render
from compositional_harm_bench.scenarios import evaluation_subset, write_dataset
from compositional_harm_bench.scoring import summarize
from compositional_harm_bench.simulator import MODES, replay

ROOT = Path(__file__).resolve().parent


def get_plans(items: list[dict], backend: str, model: str, prompt_mode: str,
              sample_idx: int) -> list[tuple[dict, str]]:
    if backend == "oracle":
        return [({"decision": "EXECUTE", "actions": item["actions"]}, "oracle")
                for item in items]
    prompts = [render(item, prompt_mode) for item in items]
    cache = ROOT / "data" / "llm_cache"
    replies = batch_call([{"prompt": prompt, "sample_idx": sample_idx}
                          for prompt in prompts], model=model, cache_dir=cache, workers=6)
    output = []
    malformed = []
    for index, reply in enumerate(replies):
        plan = parse(reply)
        output.append((plan, reply))
        if plan is None:
            malformed.append(index)
    if malformed:
        retry_items = [{"prompt": prompts[i] + "\nRetry with exact JSON only.",
                        "sample_idx": sample_idx + 1000} for i in malformed]
        retries = batch_call(retry_items, model=model, cache_dir=cache, workers=6)
        for index, reply in zip(malformed, retries):
            output[index] = (parse(reply), reply)
    return output


def row_for(item: dict, plan: dict | None, response: str, mode: str) -> dict:
    refused = bool(plan and plan["decision"] == "REJECT")
    actions = plan["actions"] if plan and not refused else []
    outcome = replay(actions, mode)
    exact_plan = bool(plan and plan["decision"] == "EXECUTE" and
                      actions == item["actions"])
    completed = exact_plan and outcome["blocked_at"] is None and not outcome["harm"]
    return {**{k: item[k] for k in ("id", "family", "domain", "mechanism", "variant",
                                     "horizon", "indirect", "memory", "multi_agent")},
            "mode": mode, "parsed": plan is not None, "refused": refused,
            "exact_plan": exact_plan, "completed": completed,
            "response": response, **outcome}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["claude", "oracle"], default="claude")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--prompt-mode", choices=["local", "minimal", "explicit"], default="local")
    ap.add_argument("--sample-idx", type=int, default=0)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    dataset_stats = write_dataset(ROOT / "data" / "benchmark_v1.jsonl")
    items = evaluation_subset()[:args.limit]
    plans = get_plans(items, args.backend, args.model, args.prompt_mode, args.sample_idx)
    rows = [row_for(item, plan, response, mode)
            for item, (plan, response) in zip(items, plans) for mode in MODES]
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    row_path = results / f"{args.run_name}_rows.jsonl"
    row_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    summary = {"run_name": args.run_name, "backend": args.backend, "model": args.model,
               "prompt_mode": args.prompt_mode, "sample_idx": args.sample_idx,
               "dataset": dataset_stats, **summarize(rows)}
    (results / f"{args.run_name}.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
