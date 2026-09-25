"""Execute canonical tasks through four external control loops."""
from __future__ import annotations

from .claude_llm import batch_call
from .prompts import loop_plan, one_shot, parse_loop, parse_plan, planner, validator
from .semantics import evaluate, normalize_actions

SCAFFOLDS = ("one_shot", "react", "planner_validator", "ledger")


def _calls(prompts: list[str], model: str, cache, sample_idx: int) -> list[str]:
    return batch_call([{"prompt": prompt, "sample_idx": sample_idx}
                       for prompt in prompts], model=model, cache_dir=cache, workers=6)


def _retry(prompts, replies, parser, model, cache, sample_idx):
    bad = [i for i, reply in enumerate(replies) if parser(reply) is None]
    if bad:
        retried = _calls([prompts[i] + "\nRetry with exact JSON only." for i in bad],
                         model, cache, sample_idx + 1000)
        for i, reply in zip(bad, retried):
            replies[i] = reply
    return replies


def _record(item, actions, responses, parsed, calls, candidate=None):
    result = evaluate(item, actions, parsed)
    candidate_actions = normalize_actions(candidate or [])
    return {"id": item["id"], "family": item["family"], "variant": item["variant"],
            "domain": item["domain"], "mechanism": item["mechanism"],
            "parsed": parsed, "actions": actions, "responses": responses,
            "model_calls": calls, "response_chars": sum(map(len, responses)),
            "planner_attempted_harm": any(a.get("op") == item["forbidden_op"]
                                          for a in candidate_actions), **result}


def run_one_shot(items, backend, model, cache, sample_idx):
    if backend == "oracle":
        return [_record(item, item["safe_actions"], ["oracle"], True, 0) for item in items]
    prompts = [one_shot(item) for item in items]
    replies = _retry(prompts, _calls(prompts, model, cache, sample_idx), parse_plan,
                     model, cache, sample_idx)
    rows = []
    for item, reply in zip(items, replies):
        plan = parse_plan(reply)
        actions = normalize_actions(plan["actions"]) if plan and plan["decision"] == "EXECUTE" else []
        rows.append(_record(item, actions, [reply], plan is not None, 1))
    return rows


def run_loop(items, backend, model, cache, sample_idx, ledger=False):
    if backend == "oracle":
        return [_record(item, item["safe_actions"], ["oracle"], True, 0) for item in items]
    prompts = [loop_plan(item, ledger=ledger) for item in items]
    replies = _retry(prompts, _calls(prompts, model, cache, sample_idx), parse_loop,
                     model, cache, sample_idx)
    rows = []
    for item, reply in zip(items, replies):
        plan = parse_loop(reply)
        turns = plan["turns"] if plan and plan["decision"] == "EXECUTE" else []
        actions = normalize_actions([turn["action"] for turn in turns])
        rows.append(_record(item, actions, [reply], plan is not None, 1))
    return rows


def run_planner_validator(items, backend, model, cache, sample_idx):
    if backend == "oracle":
        return [_record(item, item["safe_actions"], ["oracle"], True, 0,
                        item["safe_actions"]) for item in items]
    prompts = [planner(item) for item in items]
    replies = _retry(prompts, _calls(prompts, model, cache, sample_idx), parse_plan,
                     model, cache, sample_idx)
    plans = [parse_plan(reply) for reply in replies]
    valid = [i for i, plan in enumerate(plans)
             if plan and plan["decision"] == "EXECUTE"]
    validation_prompts = [validator(items[i], normalize_actions(plans[i]["actions"]))
                          for i in valid]
    validations = _retry(validation_prompts,
                         _calls(validation_prompts, model, cache, sample_idx + 1),
                         parse_plan, model, cache, sample_idx + 1) if valid else []
    by_index = dict(zip(valid, validations))
    rows = []
    for i, (item, first_reply, plan) in enumerate(zip(items, replies, plans)):
        candidate = normalize_actions(plan["actions"]) if plan else []
        if i in by_index:
            second_reply = by_index[i]
            final = parse_plan(second_reply)
            actions = normalize_actions(final["actions"]) if final and final["decision"] == "EXECUTE" else []
            rows.append(_record(item, actions, [first_reply, second_reply],
                                plan is not None and final is not None, 2, candidate))
        else:
            rows.append(_record(item, [], [first_reply], plan is not None, 1, candidate))
    return rows


def run(items, scaffold, backend, model, cache, sample_idx=0):
    if scaffold == "one_shot":
        return run_one_shot(items, backend, model, cache, sample_idx)
    if scaffold == "react":
        return run_loop(items, backend, model, cache, sample_idx, ledger=False)
    if scaffold == "ledger":
        return run_loop(items, backend, model, cache, sample_idx, ledger=True)
    if scaffold == "planner_validator":
        return run_planner_validator(items, backend, model, cache, sample_idx)
    raise ValueError(f"unknown scaffold: {scaffold}")
