#!/usr/bin/env python3
"""Battle-tested wrapper around the local `claude` CLI (the only LLM API here).

Encodes every hard-earned rule:
  - the binary is a SYMLINK named `claude`; use the symlink's dir on PATH, never resolve
  - --strict-mcp-config (skips user MCP servers; much faster startup)
  - disk cache keyed by sha256(model + prompt + sample_idx) — sample_idx exists so
    INTENDED resamples are never collapsed into one cached response
  - NEVER cache empty/failed responses; one retry; 60 s timeout; pool <= 6

CLI:
  python tools/claude_llm.py --model haiku --prompt "Reply with only: 42"
  python tools/claude_llm.py --model haiku --batch prompts.jsonl --out responses.jsonl \
      [--cache-dir data/llm_cache] [--workers 6] [--sample-idx 0]
  # prompts.jsonl lines: {"prompt": "...", "sample_idx": 0}   (sample_idx optional)

Importable: from tools.claude_llm import claude_call, batch_call
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TIMEOUT_S = 60          # p95 of healthy calls < 30 s; hangers just waste worker slots
MAX_WORKERS = 6         # account-wide saturation multiplies latency ~10x
_CANDIDATES = ("~/.local/bin/claude", "/usr/local/bin/claude", "/opt/homebrew/bin/claude")


def find_claude() -> str:
    import shutil
    hit = shutil.which("claude")
    if hit:
        return hit
    for c in _CANDIDATES:
        p = Path(c).expanduser()
        if p.exists():
            return str(p)
    raise FileNotFoundError("claude CLI not found — install/authenticate it first")


def _env() -> dict:
    env = {**os.environ}
    bin_dir = str(Path(find_claude()).parent)   # symlink's dir — NEVER resolve()
    if bin_dir not in env.get("PATH", "").split(":"):
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    return env


def _key(model: str, prompt: str, sample_idx: int) -> str:
    return hashlib.sha256(f"{model}\x00{prompt}\x00{sample_idx}".encode()).hexdigest()


def _invoke(prompt: str, model: str) -> str:
    try:
        r = subprocess.run(
            [find_claude(), "-p", "--strict-mcp-config", "--model", model, prompt],
            capture_output=True, text=True, timeout=TIMEOUT_S, env=_env(),
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def claude_call(prompt: str, model: str = "haiku", cache_dir: str | Path = "data/llm_cache",
                sample_idx: int = 0) -> str:
    """Cached single call. Empty string means failure (never cached)."""
    path = Path(cache_dir) / f"{_key(model, prompt, sample_idx)}.json"
    if path.exists():
        return json.loads(path.read_text())["response"]
    response = _invoke(prompt, model) or _invoke(prompt, model)   # one retry
    if response:  # cache successes only — a cached failure is a permanent data hole
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"model": model, "prompt": prompt,
                                    "sample_idx": sample_idx, "response": response}))
    return response


def batch_call(items: list[dict], model: str = "haiku",
               cache_dir: str | Path = "data/llm_cache", workers: int = MAX_WORKERS) -> list[str]:
    """items: [{"prompt": str, "sample_idx": int?}]; returns responses in order."""
    workers = max(1, min(workers, MAX_WORKERS))
    def one(it: dict) -> str:
        return claude_call(it["prompt"], model, cache_dir, int(it.get("sample_idx", 0)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, items))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="haiku", choices=["haiku", "sonnet", "opus"])
    ap.add_argument("--prompt")
    ap.add_argument("--batch", help="JSONL file of {prompt, sample_idx?}")
    ap.add_argument("--out", help="JSONL output (with --batch)")
    ap.add_argument("--cache-dir", default="data/llm_cache")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--sample-idx", type=int, default=0)
    a = ap.parse_args()
    if a.prompt:
        resp = claude_call(a.prompt, a.model, a.cache_dir, a.sample_idx)
        print(resp if resp else "", end="\n")
        sys.exit(0 if resp else 1)
    if a.batch:
        items = [json.loads(l) for l in open(a.batch) if l.strip()]
        responses = batch_call(items, a.model, a.cache_dir, a.workers)
        out = a.out or a.batch + ".out.jsonl"
        with open(out, "w") as f:
            for it, r in zip(items, responses):
                f.write(json.dumps({**it, "response": r}) + "\n")
        n_ok = sum(1 for r in responses if r)
        print(f"{n_ok}/{len(items)} answered → {out}")
        sys.exit(0 if n_ok else 1)
    ap.error("need --prompt or --batch")


if __name__ == "__main__":
    main()
