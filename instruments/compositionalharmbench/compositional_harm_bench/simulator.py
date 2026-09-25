"""Counterfactual safeguard replay over one model-produced plan."""
from __future__ import annotations

from copy import deepcopy

from .policy import SINKS, initial_state, locally_allowed, step

MODES = ("unprotected", "local_filter", "trajectory_monitor", "approval")


def replay(actions: list[dict], mode: str) -> dict:
    if mode not in MODES:
        raise ValueError(f"unknown safeguard: {mode}")
    state = initial_state()
    blocked_at = None
    reviews = 0
    local_passes = 0
    for index, action in enumerate(actions, 1):
        if not isinstance(action, dict) or set(action) != {"op", "arg", "actor"}:
            blocked_at = index
            break
        local_ok = locally_allowed(action)
        local_passes += int(local_ok)
        if mode == "local_filter" and not local_ok:
            blocked_at = index
            break
        candidate = step(deepcopy(state), action)
        if mode == "trajectory_monitor" and candidate["harm"]:
            blocked_at = index
            break
        if mode == "approval" and action["op"] in SINKS:
            reviews += 1
            if candidate["harm"]:
                blocked_at = index
                break
        state = candidate
    return {"mode": mode, "harm": state["harm"], "blocked_at": blocked_at,
            "executed": len(state["events"]), "reviews": reviews,
            "local_passes": local_passes, "plan_length": len(actions)}
