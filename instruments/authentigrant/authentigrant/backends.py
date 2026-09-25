"""Claude and deterministic benchmark backends."""
from __future__ import annotations

import sys
from pathlib import Path

from .policy import oracle_decision
from .prompts import render_prompt

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def run_rows(rows: list[dict], method: str, sample_idx: int, workers: int = 6, prompt_mode: str = "principles") -> list[str]:
    if method == "oracle":
        return [f'{{"decision":"{oracle_decision(row)}","basis":["deterministic policy"]}}' for row in rows]
    if method == "always_execute":
        return ['{"decision":"EXECUTE","basis":["unconditional baseline"]}' for _ in rows]
    if method == "always_reject":
        return ['{"decision":"REJECT","basis":["unconditional baseline"]}' for _ in rows]
    if method not in {"haiku", "sonnet"}:
        raise ValueError(f"unknown method: {method}")
    from claude_llm import batch_call
    prompts = [{"prompt": render_prompt(row, prompt_mode), "sample_idx": sample_idx} for row in rows]
    cache = Path(__file__).resolve().parents[1] / "data" / "llm_cache"
    return batch_call(prompts, model=method, cache_dir=cache, workers=workers)
