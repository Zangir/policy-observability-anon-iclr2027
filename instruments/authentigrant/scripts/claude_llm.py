#!/usr/bin/env python3
"""Cached wrapper around the local Claude CLI, vendored from pipeline tools."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TIMEOUT_S = 60
MAX_WORKERS = 6
_CANDIDATES = ("~/.local/bin/claude", "/usr/local/bin/claude", "/opt/homebrew/bin/claude")


def find_claude() -> str:
    hit = shutil.which("claude")
    if hit:
        return hit
    for candidate in _CANDIDATES:
        path = Path(candidate).expanduser()
        if path.exists():
            return str(path)
    raise FileNotFoundError("claude CLI not found")


def _environment() -> dict:
    env = {**os.environ}
    directory = str(Path(find_claude()).parent)
    if directory not in env.get("PATH", "").split(":"):
        env["PATH"] = f"{directory}:{env.get('PATH', '')}"
    return env


def _cache_key(model: str, prompt: str, sample_idx: int) -> str:
    return hashlib.sha256(f"{model}\0{prompt}\0{sample_idx}".encode()).hexdigest()


def _invoke(prompt: str, model: str) -> str:
    try:
        result = subprocess.run(
            [find_claude(), "-p", "--strict-mcp-config", "--model", model, prompt],
            capture_output=True, text=True, timeout=TIMEOUT_S, env=_environment(),
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def claude_call(prompt: str, model: str, cache_dir: str | Path, sample_idx: int) -> str:
    path = Path(cache_dir) / f"{_cache_key(model, prompt, sample_idx)}.json"
    if path.exists():
        return json.loads(path.read_text())["response"]
    response = _invoke(prompt, model) or _invoke(prompt, model)
    if response:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"model": model, "sample_idx": sample_idx, "response": response}))
    return response


def batch_call(items: list[dict], model: str, cache_dir: str | Path, workers: int = MAX_WORKERS) -> list[str]:
    workers = max(1, min(workers, MAX_WORKERS))
    def one(item: dict) -> str:
        return claude_call(item["prompt"], model, cache_dir, int(item.get("sample_idx", 0)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, items))
