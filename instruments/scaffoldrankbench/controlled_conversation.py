"""Real two-turn CLI sessions with immutable randomized manifests and transcripts."""
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from controlled_runner import FLAGS, digest, object_response


def run_conversations(requests, out_dir, followup, models=("haiku", "sonnet"), repeats=2,
                      seed=202709, workers=3, timeout=60):
    import random
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    binary = shutil.which("claude") or str(Path("~/.local/bin/claude").expanduser())
    version = subprocess.check_output([binary, "--version"], text=True).strip()
    flags = [x for x in FLAGS if x != "--no-session-persistence"]
    jobs = [{**r, "model": model, "replicate": k} for r in requests for model in models for k in range(repeats)]
    random.Random(seed).shuffle(jobs)
    for order, job in enumerate(jobs):
        job["order"] = order
        job["request_id"] = digest(job)
    # Include the actual follow-up construction source, not merely its name.
    import inspect
    manifest = {"schema": "controlled-conversation-v1", "jobs": jobs, "flags": flags,
                "cli_version": version, "workers": workers, "timeout": timeout, "seed": seed,
                "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "followup_source": inspect.getsource(followup),
                "interaction": "first CLI call with session-id; second CLI call resumes that exact session in the same temporary cwd",
                "limitation": "provider-side policy and serving configuration are unobservable; no retry of ambiguous failed session turns"}
    path = out_dir / "manifest.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("Manifest changed: choose a fresh output directory")
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_hash = digest(manifest)
    records_dir = out_dir / "responses"
    records_dir.mkdir(exist_ok=True)

    def one(job):
        dest = records_dir / (job["request_id"] + ".json")
        if dest.exists():
            saved = json.loads(dest.read_text())
            if saved["manifest_sha256"] != manifest_hash:
                raise ValueError("Response manifest mismatch")
            return saved
        session = str(uuid.uuid4())
        transcript = []
        with tempfile.TemporaryDirectory(prefix="controlled-dialogue-") as cwd:
            prompt = job["prompt"]
            for turn in range(2):
                session_args = ["--session-id", session] if turn == 0 else ["--resume", session]
                schema_args = ["--json-schema", json.dumps(job["response_schema"])] if "response_schema" in job else []
                start = time.monotonic()
                envelope = {}
                try:
                    proc = subprocess.run([binary, *flags, *session_args, *schema_args, "--model", job["model"]],
                                          input=prompt, cwd=cwd, text=True, capture_output=True, timeout=timeout)
                    try:
                        envelope = json.loads(proc.stdout)
                    except ValueError:
                        pass
                    code, error = proc.returncode, proc.stderr
                except subprocess.TimeoutExpired:
                    code, error = None, "timeout"
                ok = code == 0 and not envelope.get("is_error", True)
                raw = envelope.get("result", "")
                parsed = envelope.get("structured_output", object_response(raw)) if ok else None
                transcript.append({"turn": turn, "user": prompt, "raw": raw, "parsed": parsed,
                                   "transport_ok": ok, "exit_code": code, "stderr": error,
                                   "elapsed_seconds": time.monotonic() - start, "envelope": envelope})
                if not ok:
                    break
                if turn == 0:
                    prompt = followup(job, parsed)
                    if prompt is None:
                        break
        result = {**job, "manifest_sha256": manifest_hash, "transcript": transcript,
                  "parsed": transcript[-1]["parsed"], "first_parsed": transcript[0]["parsed"],
                  "completed_turns": len(transcript), "transport_ok": all(t["transport_ok"] for t in transcript),
                  "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        dest.write_text(json.dumps(result, indent=2) + "\n")
        return result

    records = []
    with ThreadPoolExecutor(max_workers=min(6, max(1, workers))) as pool:
        for future in as_completed([pool.submit(one, job) for job in jobs]):
            records.append(future.result())
            if len(records) % 12 == 0 or len(records) == len(jobs):
                print(f"Completed {len(records)}/{len(jobs)} conversations", flush=True)
    return sorted(records, key=lambda r: r["order"])
