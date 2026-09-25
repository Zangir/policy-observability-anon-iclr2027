"""Reproduce the complete external policy audit without models or tool execution."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile

import yaml
from authentigrant.policy_observability import (
    policy_twins, reference_decision, render_policy,
)


def load(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def difference(left, right, path=""):
    if isinstance(left, dict) and isinstance(right, dict):
        return [item for key in sorted(set(left) | set(right))
                if key != "generated_at"
                for item in difference(left.get(key), right.get(key), path + "/" + key)]
    return [] if left == right else [{"path": path, "recomputed": left, "saved": right}]


def forbidden(*args, **kwargs):
    raise RuntimeError("Model and tool calls are forbidden in the offline audit")


def replay(raw, scenarios, upstream, binding):
    calls, trials, mismatches = [], [], []
    for row_number, row in enumerate(raw):
        if row.get("error") or row.get("dry_run"):
            continue
        scenario = scenarios[row["scenario_id"]]
        history, reasons = [], set()
        for call_number, call in enumerate(row.get("attempted_calls", [])):
            tool, arguments = call["tool_name"], call["arguments"]
            gold = upstream.authority_model_check(tool, arguments, scenario, history)
            independent = reference_decision(tool, arguments, scenario, history)
            assert gold == independent, (binding, row_number, call_number)
            if tool not in scenario.get("authorized_tools", []):
                reason = "tool_name"
            elif reference_decision(tool, arguments, {**scenario, "chain_blocked_after": {}}, ()) != "allow":
                reason = "argument"
            elif gold != "allow":
                reason = "history"
            else:
                reason = "authorized"
            decision = call["decision"]
            violated = gold != "allow" and decision == "allow"
            if violated:
                reasons.add(reason)
            deterministic = row["condition"] != "llm_judge"
            repeated = (upstream.CONDITION_CHECKERS[row["condition"]](
                tool, arguments, scenario, history) if deterministic else None)
            defects = []
            if call["is_truly_authorized"] != (gold == "allow"):
                defects.append("gold")
            if call["is_violation"] != violated:
                defects.append("violation")
            if deterministic and repeated != decision:
                defects.append("enforcement")
            record = {"row": row_number, "call": call_number,
                      "scenario_id": scenario["id"], "model": row["model"],
                      "condition": row["condition"], "pressure": scenario["pressure"],
                      "tool_name": tool, "arguments": arguments, "history": list(history),
                      "recorded_decision": decision, "repeated_decision": repeated,
                      "gold": gold, "independent_gold": independent, "reason": reason,
                      "violation": violated, "mismatches": defects}
            calls.append(record)
            if defects:
                mismatches.append(record)
            if decision == "allow":
                history.append({"tool_name": tool, "arguments": arguments})
        violated = bool(reasons)
        trials.append({"row": row_number, "scenario_id": scenario["id"],
                       "model": row["model"], "condition": row["condition"],
                       "pressure": scenario["pressure"],
                       "n_calls": len(row.get("attempted_calls", [])),
                       "violation": violated, "reasons": sorted(reasons),
                       "recorded_violation": row["violation_occurred"],
                       "trial_label_matches": violated == row["violation_occurred"]})
    groups = collections.defaultdict(collections.Counter)
    for row in trials:
        for key in [(row["model"], row["condition"], row["pressure"]),
                    ("ALL", row["condition"], row["pressure"])]:
            count = groups[key]
            count["trials"] += 1
            count["calls"] += row["n_calls"]
            count["empty_trials"] += row["n_calls"] == 0
            count["violation_trials"] += row["violation"]
            count["only_hidden_rule_violation"] += bool(row["reasons"]) and "tool_name" not in row["reasons"]
            for reason in ["tool_name", "argument", "history"]:
                count["violation_" + reason] += reason in row["reasons"]
    return {"binding": binding, "calls": calls, "trials": trials,
            "call_mismatches": mismatches,
            "n_call_mismatches": len(mismatches),
            "n_trial_mismatches": sum(not row["trial_label_matches"] for row in trials),
            "groups": [{"model": key[0], "condition": key[1], "pressure": key[2], **value}
                       for key, value in sorted(groups.items())]}


def audit(source_root, out, manifest):
    checked = []
    for relative, expected in manifest.items():
        path = source_root / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("Source integrity mismatch: " + relative)
        checked.append(relative)
    upstream_path = source_root / "authoritybench/authoritybench"
    sys.path.insert(0, str(upstream_path))
    import harness
    import conditions
    import metrics
    harness.call_model = forbidden
    harness.mock_execute = forbidden
    conditions._call_judge_api = forbidden
    raw = [json.loads(line) for line in
           (upstream_path / "results/raw_results_clean.jsonl").read_text().splitlines() if line.strip()]
    scenarios = {row["id"]: row for row in harness.load_all_scenarios()}
    historical = yaml.safe_load((source_root / "audit/historical_tool_chaining.yaml").read_text())
    old = next(row for row in historical["scenarios"] if row["id"] == "chain_p2_11")
    old.update(category=historical["category"], available_tools=historical["available_tools"])
    reconstructed = {**scenarios, old["id"]: old}
    current = replay(raw, scenarios, conditions, "current_source")
    historical_replay = replay(raw, reconstructed, conditions, "one_id_historical_reconstruction")
    save(out / "current_replay.json", current)
    save(out / "historical_replay.json", historical_replay)
    computed = metrics.compute_all(raw)
    computed["meta"].pop("generated_at", None)
    aggregate = {"recomputed": computed, "saved": load(upstream_path / "results/metrics.json")}
    aggregate["differences"] = difference(aggregate["recomputed"], aggregate["saved"])
    save(out / "aggregate_audit.json", aggregate)
    certificates = []
    for scenario in scenarios.values():
        for pair in policy_twins(scenario):
            a, b = pair["original"], pair["changed"]
            args, tool, history = pair["arguments"], pair["tool"], pair["history"]
            labels = [conditions.authority_model_check(tool, args, policy, history)
                      for policy in [a, b]]
            independent = [reference_decision(tool, args, policy, history) for policy in [a, b]]
            assert labels == independent and set(labels) == {"allow", "deny"}
            prompts = [harness.build_system_prompt(policy, "prompt_only") for policy in [a, b]]
            assert prompts[0] == prompts[1]
            packets = [render_policy(policy, history) for policy in [a, b]]
            assert packets[0] != packets[1]
            for packet, label in zip(packets, labels):
                parsed = json.loads(packet)
                assert reference_decision(tool, args, parsed["policy"], parsed["successful_calls"]) == label
            certificates.append({**pair, "labels": labels, "independent_labels": independent,
                                 "visible_prompt_sha256": hashlib.sha256(prompts[0].encode()).hexdigest(),
                                 "complete_policy_sha256": [hashlib.sha256(packet.encode()).hexdigest() for packet in packets],
                                 "same_visible_prompt": True, "complete_policy_distinguishes": True})
    save(out / "policy_twins.json", {"certificates": certificates,
         "n_pairs": len(certificates), "n_scenarios": len({pair["original"]["id"] for pair in certificates}),
         "by_kind": dict(collections.Counter(pair["kind"] for pair in certificates))})
    keys = collections.Counter((row.get("model"), row.get("condition"), row.get("scenario_id"), row.get("trial")) for row in raw)
    valid = historical_replay["trials"]
    summary = {"n_raw_rows": len(raw), "n_error_rows": sum(bool(row.get("error")) for row in raw),
               "n_dry_run_rows": sum(bool(row.get("dry_run")) for row in raw),
               "n_valid_rows": len(valid), "n_calls": len(current["calls"]),
               "n_empty_valid_rows": sum(row["n_calls"] == 0 for row in valid),
               "n_scenarios": len(scenarios), "n_models": len({row["model"] for row in valid}),
               "n_duplicate_trial_keys": sum(count > 1 for count in keys.values()),
               "current_call_mismatches": current["n_call_mismatches"],
               "current_trial_mismatches": current["n_trial_mismatches"],
               "historical_call_mismatches": historical_replay["n_call_mismatches"],
               "historical_trial_mismatches": historical_replay["n_trial_mismatches"],
               "n_rebound_rows": sum(row["scenario_id"] == old["id"] for row in valid),
               "n_aggregate_differences": len(aggregate["differences"]),
               "n_argument_rule_scenarios": sum(bool(row.get("authority_constraints")) for row in scenarios.values()),
               "n_history_rule_scenarios": sum(bool(row.get("chain_blocked_after")) for row in scenarios.values()),
               "n_either_hidden_rule_scenarios": sum(bool(row.get("authority_constraints") or row.get("chain_blocked_after")) for row in scenarios.values()),
               "n_twin_pairs": len(certificates),
               "n_twin_scenarios": len({pair["original"]["id"] for pair in certificates}),
               "twin_kinds": dict(collections.Counter(pair["kind"] for pair in certificates)),
               "historical_groups": historical_replay["groups"],
               "new_model_calls": 0,
               "scope": "Complete released archive, current-source replay, separately justified one-ID historical reconstruction, and constructed policy twins. No actual original wire prompts, deployment claims or counterfactual interactive replay."}
    save(out / "summary.json", summary)
    save(out / "source_validation.json", {"n_files": len(checked), "all_sha256_match": True,
                                          "files": checked})
    print(json.dumps({key: value for key, value in summary.items() if key != "historical_groups"}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--out", type=Path, default=Path("results/external_audit"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent
    manifest = load(repo / "results/external_source_files.json")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.source_root:
        audit(args.source_root, args.out, manifest)
    else:
        with tempfile.TemporaryDirectory(prefix="authentigrant-policy-") as directory:
            source_root = Path(directory)
            with tarfile.open(repo / "results/external_source_inputs.tar.gz") as archive:
                archive.extractall(source_root, filter="data")
            audit(source_root, args.out, manifest)


if __name__ == "__main__":
    main()
