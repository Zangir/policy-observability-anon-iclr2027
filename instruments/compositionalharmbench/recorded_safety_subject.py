"""Recorded OpenAI CLI benchmark subjects; no review or coding is delegated.

This is a separate provider/interface study, not interchangeable with Claude
responses. Host skill/policy/environment context remains and is archived.
"""
import datetime as dt
import hashlib
import inspect
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

from controlled_runner import digest, object_response, paired_contrasts, summarize

SYSTEM = "Answer the supplied task. Return only the requested output."
MODELS = ("gpt-5.6-luna", "gpt-5.6-sol")
DISABLED = ["shell_tool", "unified_exec", "apps", "plugins", "remote_plugin", "hooks",
            "multi_agent", "multi_agent_v2", "memories", "browser_use", "browser_use_external",
            "computer_use", "image_generation", "view_image", "goals", "sleep_tool",
            "code_mode_host", "workspace_dependencies", "skill_mcp_dependency_install", "skill_search"]
FLAGS = ["--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--json",
         "-c", 'model_reasoning_effort="low"', "-c", 'web_search="disabled"',
         "-c", "project_doc_max_bytes=0", "-c", 'approval_policy="never"',
         "-c", 'sandbox_mode="read-only"']
for feature in DISABLED:
    FLAGS += ["--disable", feature]
FLAGS += ["--enable", "skip_host_skill_discovery"]


def decode_events(stdout, returncode):
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    finished = [e for e in events if e.get("type") == "turn.completed"]
    failed = any(e.get("type") in {"turn.failed", "error"} for e in events)
    messages = [e["item"]["text"] for e in events if e.get("type") == "item.completed"
                and e.get("item", {}).get("type") == "agent_message"]
    session = next((e["thread_id"] for e in events if e.get("type") == "thread.started"), None)
    # Startup warning items are retained but are not failed model turns.
    external = [e for e in events if e.get("item", {}).get("type") in
                {"command_execution", "mcp_tool_call", "web_search", "file_change"}]
    ok = returncode == 0 and bool(finished) and not failed and not external
    raw = messages[-1] if messages else ""
    return {"events": events, "session_id": session, "transport_ok": ok,
            "raw": raw, "parsed": object_response(raw) if ok else None,
            "usage": finished[-1].get("usage", {}) if finished else {},
            "external_tool_events": external}


def run_requests(requests, out_dir, models=MODELS, repeats=2, seed=202709,
                 workers=3, timeout=180):
    return _run(requests, out_dir, models, repeats, seed, workers, timeout, None)


def run_conversations(requests, out_dir, followup, models=MODELS, repeats=2,
                      seed=202709, workers=3, timeout=180):
    return _run(requests, out_dir, models, repeats, seed, workers, timeout, followup)


def _run(requests, out_dir, models, repeats, seed, workers, timeout, followup):
    if not set(models) <= set(MODELS):
        raise ValueError("Model names must identify the actual locked OpenAI subjects")
    binary = shutil.which("codex")
    auth = Path.home() / ".codex/auth.json"
    if not binary or not auth.exists():
        raise RuntimeError("The official CLI's existing file login is unavailable")
    out = Path(out_dir);out.mkdir(parents=True, exist_ok=True)
    jobs = [{**r, "model": model, "replicate": rep} for r in requests for model in models for rep in range(repeats)]
    random.Random(seed).shuffle(jobs)
    for i, job in enumerate(jobs):
        job["order"] = i;job["request_id"] = digest(job)
    manifest = {"schema": "openai-cli-study-v1", "provider": "openai", "models": list(models),
                "cli_version": subprocess.check_output([binary, "--version"], text=True).strip(),
                "flags": FLAGS, "system_instructions": SYSTEM, "reasoning_effort": "low",
                "workers": workers, "timeout": timeout, "seed": seed, "jobs": jobs,
                "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "analysis_helper_sha256": hashlib.sha256(Path(inspect.getfile(summarize)).read_bytes()).hexdigest(),
                "quota_policy": "bounded scheduling stops on explicit provider quota/usage-limit errors; preserves in-flight records; no selective replacement",
                "followup_source": inspect.getsource(followup) if followup else None,
                "retry_policy": "no automatic retry; incomplete or invalid turns are retained",
                "context_scope": "empty temporary working directory; existing application home/auth unchanged; user config/rules and external tool features disabled; only the subject session UUID is used to collect its saved host rollout; provider-managed instructions unobservable",
                "comparison_scope": "a separately labeled CLI configuration; not equal hidden compute or a pure provider/model contrast with Claude"}
    manifest_path = out / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise ValueError("Immutable study manifest differs; choose a new study name")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_hash = digest(manifest)
    responses = out / "responses";responses.mkdir(exist_ok=True)

    def one(job):
        dest = responses / (job["request_id"] + ".json")
        if dest.exists():
            saved = json.loads(dest.read_text())
            if saved["manifest_sha256"] != manifest_hash:
                raise ValueError("Saved response belongs to another manifest")
            return saved
        transcript = []
        with tempfile.TemporaryDirectory(prefix="recorded-openai-study-") as tmp:
            scratch = Path(tmp)
            cwd = scratch / "empty";cwd.mkdir()
            (scratch / "instructions.txt").write_text(SYSTEM)
            schema = scratch / "schema.json"
            schema.write_text(json.dumps(job.get("response_schema", {"type": "object"})))
            flags = [*FLAGS, "--model", job["model"], "--output-schema", str(schema),
                     "-c", f'model_instructions_file="{scratch}/instructions.txt"']
            env = dict(os.environ)
            prompt, session = job["prompt"], None
            for turn in range(2 if followup else 1):
                command = [binary, "exec", *(["resume"] if turn else []), *flags,
                           *([session] if turn else []), "-"]
                start = time.monotonic()
                try:
                    proc = subprocess.run(command, input=prompt, cwd=cwd, env=env,
                                          capture_output=True, text=True, timeout=timeout)
                    code, stdout, error = proc.returncode, proc.stdout, proc.stderr
                except subprocess.TimeoutExpired as exc:
                    code, error = None, "timeout"
                    stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
                envelope = decode_events(stdout, code)
                if turn == 0:
                    session = envelope["session_id"]
                elif envelope["session_id"] != session:
                    envelope["transport_ok"] = False
                    error += " resumed session identifier mismatch"
                record = {"turn": turn, "user": prompt, "raw": envelope["raw"], "parsed": envelope["parsed"],
                          "transport_ok": envelope["transport_ok"], "exit_code": code, "stderr": error,
                          "elapsed_seconds": time.monotonic()-start, "envelope": envelope,
                          "stdout_jsonl": stdout, "command": [x.replace(str(scratch), "<TEMP>") for x in command]}
                transcript.append(record)
                if not record["transport_ok"]:
                    break
                if followup and turn == 0:
                    prompt = followup(job, record["parsed"])
                    if prompt is None:
                        break
                    if not session:
                        raise RuntimeError("Cannot resume without an actual session identifier")
            rollouts = [f.read_text() for f in sorted((Path.home() / ".codex/sessions").rglob("*" + str(session) + "*.jsonl"))] if session else []
        result = {**job, "manifest_sha256": manifest_hash, "transcript": transcript,
                  "first_parsed": transcript[0]["parsed"], "parsed": transcript[-1]["parsed"],
                  "raw": transcript[-1]["raw"], "completed_turns": len(transcript),
                  "transport_ok": all(t["transport_ok"] for t in transcript),
                  "provider": "openai", "requested_model": job["model"], "rollout_jsonl": rollouts,
                  "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        if not followup:
            result["attempts"] = [{**transcript[0], "attempt": 0}]
        dest.write_text(json.dumps(result, indent=2) + "\n")
        return result

    records = []
    jobs_iter = iter(jobs)
    stopped = False
    with ThreadPoolExecutor(max_workers=min(6, max(1, workers))) as pool:
        pending = {pool.submit(one, j) for j in [next(jobs_iter, None) for _ in range(min(6, max(1, workers)))] if j is not None}
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                response = future.result()
                records.append(response)
                for turn in response["transcript"]:
                    errors = [e for e in turn["envelope"]["events"] if e.get("type") in {"error", "turn.failed"}]
                    message = json.dumps(errors).lower()
                    if not turn["transport_ok"] and any(x in message for x in
                        ("usage limit", "quota", "rate limit", "rate_limit", "too many requests", "insufficient_quota")):
                        stopped = True
                if not stopped:
                    job = next(jobs_iter, None)
                    if job is not None:
                        pending.add(pool.submit(one, job))
            if len(records) % 12 == 0 or not pending:
                print(f"Saved {len(records)}/{len(jobs)} OpenAI study records", flush=True)
    if stopped:
        (out / "COLLECTION_PAUSED.json").write_text(json.dumps({"reason": "explicit provider quota or rate-limit error", "saved": len(records), "planned": len(jobs), "time": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2) + "\n")
        raise RuntimeError("Provider quota circuit breaker stopped collection; preserve partial records")
    return sorted(records, key=lambda r: r["order"])
