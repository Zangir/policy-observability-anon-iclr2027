"""Recorded, isolated Claude invocations for the scientific revision studies.

Vendored next to each study entry point; no project-private imports are required.
Historical provider outputs are deliberately never reused by this runner.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SYSTEM = "Answer the supplied task. Return only the requested output."
FLAGS = ["-p", "--safe-mode", "--strict-mcp-config", "--tools", "",
         "--disable-slash-commands", "--no-session-persistence",
         "--system-prompt", SYSTEM, "--output-format", "json"]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def object_response(raw):
    """Allow a surrounding code fence, but never repair or infer an answer."""
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


def run_requests(requests, out_dir, models=("haiku", "sonnet"), repeats=2, seed=202709,
                 workers=3, timeout=60):
    """Run an immutable, randomized manifest; save every attempt and provider envelope.

    A completed manifest is reused only byte-for-byte. Transport failures receive
    one retry, retained in the record. Valid refusals and malformed answers are data
    and are not retried. Resuming an interrupted run preserves completed requests.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    binary = shutil.which("claude") or str(Path("~/.local/bin/claude").expanduser())
    version = subprocess.check_output([binary, "--version"], text=True).strip()
    jobs = [{**request, "model": model, "replicate": replicate}
            for request in requests for model in models for replicate in range(repeats)]
    random.Random(seed).shuffle(jobs)
    for i, job in enumerate(jobs):
        job["order"] = i
        job["request_id"] = digest(job)
    manifest = {"schema": "controlled-cli-v1", "cli_version": version,
                "flags": FLAGS, "seed": seed, "workers": workers, "timeout": timeout,
                "jobs": jobs, "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "isolation": "fresh temporary cwd per request; safe mode; explicit system; tools disabled",
                "limitation": "provider-side policy and serving configuration are not observable"}
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("Run manifest changed: use a new output directory; never merge studies")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_hash = digest(manifest)
    records_dir = out_dir / "responses"
    records_dir.mkdir(exist_ok=True)

    def one(job):
        path = records_dir / (job["request_id"] + ".json")
        if path.exists():
            saved = json.loads(path.read_text())
            if saved["manifest_sha256"] != manifest_hash:
                raise ValueError("Cached response manifest mismatch")
            return saved
        attempts = []
        for attempt in range(2):
            started = time.monotonic()
            envelope = {}
            with tempfile.TemporaryDirectory(prefix="controlled-study-") as cwd:
                try:
                    schema_flags = (["--json-schema", json.dumps(job["response_schema"])]
                                    if "response_schema" in job else [])
                    proc = subprocess.run([binary, *FLAGS, *schema_flags, "--model", job["model"]],
                                          input=job["prompt"], cwd=cwd, text=True,
                                          capture_output=True, timeout=timeout)
                    try:
                        envelope = json.loads(proc.stdout)
                    except ValueError:
                        pass
                    error = proc.stderr
                    code = proc.returncode
                except subprocess.TimeoutExpired:
                    error, code = "timeout", None
            ok = code == 0 and not envelope.get("is_error", True)
            attempts.append({"attempt": attempt, "exit_code": code,
                             "elapsed_seconds": time.monotonic() - started,
                             "transport_ok": ok, "stderr": error,
                             "envelope": envelope})
            if ok:
                break
        raw = envelope.get("result", "") if ok else ""
        parsed = envelope.get("structured_output", object_response(raw)) if ok else None
        record = {**job, "manifest_sha256": manifest_hash, "attempts": attempts,
                  "transport_ok": ok, "raw": raw, "parsed": parsed,
                  "resolved_models": sorted(envelope.get("modelUsage", {})),
                  "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        path.write_text(json.dumps(record, indent=2) + "\n")
        return record

    records = []
    with ThreadPoolExecutor(max_workers=min(6, max(1, workers))) as pool:
        futures = [pool.submit(one, job) for job in jobs]
        for future in as_completed(futures):
            records.append(future.result())
            if len(records) % 12 == 0 or len(records) == len(jobs):
                print(f"Completed {len(records)}/{len(jobs)} requests", flush=True)
    return sorted(records, key=lambda row: row["order"])


def summarize(rows, metrics=("correct",), seed=202710, draws=5000):
    """Item-cluster bootstrap keeps all repeats together; no pooling model families."""
    import numpy as np
    result = {}
    for model in sorted({r["model"] for r in rows}):
        result[model] = {}
        for condition in sorted({r["condition"] for r in rows}):
            part = [r for r in rows if r["model"] == model and r["condition"] == condition]
            ids = sorted({r["item_id"] for r in part})
            stats = {"n_responses": len(part), "n_items": len(ids)}
            for metric in metrics:
                values = np.array([np.mean([float(r[metric]) for r in part if r["item_id"] == i]) for i in ids])
                rng = np.random.default_rng(seed)
                estimates = values[rng.integers(0, len(ids), (draws, len(ids)))].mean(axis=1)
                stats[metric] = {"mean": float(values.mean()), "ci95": np.quantile(estimates, [.025, .975]).tolist()}
            result[model][condition] = stats
    return result


def paired_contrasts(rows, conditions, metric="correct", draws=5000, seed=202710):
    import numpy as np
    result = {}
    for model in sorted({r["model"] for r in rows}):
        result[model] = {}
        for before, after in conditions:
            lookup = {(r["item_id"], r["replicate"], r["condition"]): float(r[metric])
                      for r in rows if r["model"] == model}
            ids = sorted({key[0] for key in lookup})
            values = []
            for item in ids:
                reps = sorted({key[1] for key in lookup if key[0] == item})
                values.append(np.mean([lookup[item, k, after] - lookup[item, k, before] for k in reps]))
            values = np.array(values)
            rng = np.random.default_rng(seed)
            samples = values[rng.integers(0, len(ids), (draws, len(ids)))].mean(axis=1)
            result[model][f"{after}-minus-{before}"] = {
                "metric": metric, "n_items": len(ids), "difference": float(values.mean()),
                "ci95": np.quantile(samples, [.025, .975]).tolist()}
    return result
