"""Decision-screen model calls for the invariance experiment (stage B).

Preserves the shipped GUARD_INSTRUCTION + DECISION_SCHEMA + make_payload wire content
verbatim (imported, not retyped). macOS-native transport: session-fresh `claude -p`
(haiku/sonnet) or `codex exec`; the shipped bwrap/Linux transport is not reproducible
here (logs/deviations.md D2). Resumable: existing terminal run dirs are skipped. A single
deterministic parser is applied to every arm so R/C/K are scored identically; parse mode
is recorded as data, never repaired away.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time, hashlib, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]  # decision_invariance/ repo root (portable)
DSW = REPO / "lib"
sys.path.insert(0, str(DSW))
from adapter.decision_screen_transport import GUARD_INSTRUCTION, DECISION_SCHEMA, make_payload  # verbatim
from jsonschema import Draft202012Validator

OUT = REPO / "results/decision_invariance"
CLAUDE = str(Path.home() / ".local/bin/claude")
CODEX = str(Path.home() / ".vscode/extensions/openai.chatgpt-26.917.62051-darwin-arm64/bin/macos-aarch64/codex")
VALIDATOR = Draft202012Validator(DECISION_SCHEMA)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def find_decision(text: str):
    """Return (decision_obj, parse_mode) or (None, failure_category). One parser, all arms."""
    t = text.strip()
    # 1. clean: whole response is the decision object
    for mode, candidate in (("clean", t),):
        try:
            v = json.loads(candidate)
        except Exception:
            v = None
        if isinstance(v, dict):
            if not list(VALIDATOR.iter_errors(v)) and v.get("reason", "").strip():
                return v, mode
            # 2. envelope: {content, tool_calls} with content holding the object
            if set(v) == {"content", "tool_calls"} and isinstance(v.get("content"), str):
                try:
                    inner = json.loads(v["content"])
                except Exception:
                    inner = None
                if isinstance(inner, dict) and not list(VALIDATOR.iter_errors(inner)) and inner.get("reason", "").strip():
                    return inner, "envelope"
    # 3. extracted: first balanced {...} substring that validates (fenced/prose tolerated for categorisation only)
    for m in re.finditer(r"\{", t):
        depth = 0
        for i in range(m.start(), len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    frag = t[m.start():i + 1]
                    try:
                        v = json.loads(frag)
                    except Exception:
                        break
                    if isinstance(v, dict) and not list(VALIDATOR.iter_errors(v)) and v.get("reason", "").strip():
                        return v, "extracted"
                    break
    if re.match(r"^\s*(?:I (?:cannot|can't|am unable to|won't|will not|must decline|refuse)|Sorry\b)", t, re.I):
        return None, "refusal"
    return None, "invalid_output"


def call_claude(model, prompt, timeout):
    tier = {"claude-haiku": "haiku", "claude-sonnet": "sonnet"}[model]
    env = dict(os.environ, PATH=str(Path.home() / ".local/bin") + ":" + os.environ.get("PATH", ""))
    p = subprocess.run([CLAUDE, "-p", "--strict-mcp-config", "--model", tier, prompt],
                       capture_output=True, text=True, timeout=timeout, env=env)
    return p.returncode, p.stdout, p.stderr


def call_codex(model, prompt, run, timeout):
    (run / "schema.json").write_text(json.dumps({"type": "object", "additionalProperties": False,
        "properties": DECISION_SCHEMA["properties"], "required": DECISION_SCHEMA["required"]}))
    argv = [CODEX, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--json",
            "--color", "never", "--output-schema", str(run / "schema.json"),
            "--output-last-message", str(run / "final.txt"),
            "-c", 'model_reasoning_effort="low"', "-"]
    p = subprocess.run(argv, input=prompt, capture_output=True, text=True, timeout=timeout)
    final = (run / "final.txt").read_text() if (run / "final.txt").exists() else p.stdout
    return p.returncode, final, p.stderr


def run_item(item, model, timeout):
    run = OUT / "calls" / model / item["item_id"]
    meta_path = run / "metadata.json"
    if meta_path.exists():
        try:
            m = json.loads(meta_path.read_text())
            if m.get("status") in ("completed", "failed"):
                return m
        except Exception:
            pass
    run.mkdir(parents=True, exist_ok=True)
    rendering = (REPO / item["rendering_path"]).read_text()
    payload = make_payload(rendering, GUARD_INSTRUCTION)
    prompt = payload["messages"][0]["content"]  # GUARD_INSTRUCTION + EVIDENCE_JSON (load-bearing content)
    (run / "prompt.txt").write_text(prompt)
    meta = {"item_id": item["item_id"], "packet_id": item["packet_id"], "model": model,
            "rendering_sha256": item["rendering_sha256"], "rendering_arms": item["rendering_arms"],
            "repetition": item["repetition"], "source_task": item["source_task"],
            "action_effect": item["action_effect"], "tool_name": item["tool_name"],
            "prompt_sha256": sha(prompt.encode()), "prompt_bytes": len(prompt.encode()),
            "started_utc": now(), "transport": "macos_native_" + ("codex" if model == "codex" else "claude_cli")}
    t0 = time.monotonic()
    try:
        if model == "codex":
            rc, resp, err = call_codex(model, prompt, run, timeout)
        else:
            rc, resp, err = call_claude(model, prompt, timeout)
        (run / "response.txt").write_text(resp or "")
        if err:
            (run / "stderr.txt").write_text(err)
        meta["exit_status"] = rc
        if rc != 0:
            meta.update(status="failed", category="provider_failure")
        else:
            decision, mode = find_decision(resp or "")
            if decision is None:
                meta.update(status="failed", category=mode)
            else:
                # message index bound check (same rule as shipped parse_decision)
                mc = len(json.loads(rendering)["actor_visible_messages"])
                if any(i >= mc for i in decision["message_indices"]):
                    meta.update(status="failed", category="index_out_of_range")
                else:
                    meta.update(status="completed", category="valid_decision",
                                decision=decision["decision"], parse_mode=mode)
                    (run / "decision.json").write_text(json.dumps(decision, indent=2))
    except subprocess.TimeoutExpired:
        meta.update(status="failed", category="timeout", exit_status=124)
    except Exception as e:
        meta.update(status="failed", category="exception", error=f"{type(e).__name__}: {e}")
    meta["elapsed_seconds"] = time.monotonic() - t0
    meta["finished_utc"] = now()
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["claude-haiku", "claude-sonnet", "codex"])
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="0=all; else first N items (smoke)")
    args = ap.parse_args()
    sched = json.loads((OUT / "schedule.json").read_text())
    items = [it for it in sched["items"] if it["model"] == args.model]
    if args.limit:
        items = items[:args.limit]
    from collections import Counter
    done = 0
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_item, it, args.model, args.timeout) for it in items]
        for f in futs:
            results.append(f.result())
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(items)} done", flush=True)
    cats = Counter(r.get("category") for r in results)
    modes = Counter(r.get("parse_mode") for r in results if r.get("status") == "completed")
    dec = Counter(r.get("decision") for r in results if r.get("status") == "completed")
    summary = {"model": args.model, "n_items": len(items),
               "completed": sum(r.get("status") == "completed" for r in results),
               "failed": sum(r.get("status") == "failed" for r in results),
               "categories": dict(cats), "parse_modes": dict(modes), "decisions": dict(dec)}
    (OUT / f"run_summary_{args.model}.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
