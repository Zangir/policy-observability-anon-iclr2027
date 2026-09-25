"""Behavioral invariants for the external policy contract and its representation."""
import copy
import json

import pytest

from authentigrant.policy_observability import (
    policy_twins, reference_decision, render_policy,
)


@pytest.mark.parametrize("tool,arguments,expected", [
    ("read", {"path": "/home/user/report"}, "allow"),
    ("read", {"path": "/home/other/report"}, "deny"),
    ("read", {}, "deny"),
    ("write", {"path": "/home/user/report"}, "deny"),
    ("transfer", {}, "require_approval"),
])
def test_named_and_argument_decisions(tool, arguments, expected):
    policy = {"authorized_tools": ["read"], "require_approval_tools": ["transfer"],
              "authority_constraints": {"read": {"allowed_path_prefix": "/home/user/"}}}
    assert reference_decision(tool, arguments, policy) == expected


def test_literal_semantics_are_not_silently_replaced_by_hostname_matching():
    policy = {"authorized_tools": ["get"], "authority_constraints": {
        "get": {"allowed_domain": "approved.example"}}}
    assert reference_decision("get", {"url": "https://other.invalid/?q=approved.example"}, policy) == "allow"


def test_authorized_name_precedes_approval_list_in_source_contract():
    policy = {"authorized_tools": ["transfer"], "require_approval_tools": ["transfer"]}
    assert reference_decision("transfer", {}, policy) == "allow"


def test_history_uses_successful_predecessors_and_preserves_unrelated_calls():
    policy = {"authorized_tools": ["read", "send", "summarize"],
              "chain_blocked_after": {"read": ["send"]}}
    assert reference_decision("send", {}, policy, []) == "allow"
    assert reference_decision("send", {}, policy, [{"tool_name": "read"}]) == "deny"
    assert reference_decision("summarize", {}, policy, [{"tool_name": "read"}]) == "allow"


def test_twins_cover_effective_rules_without_mutating_source():
    policy = {"id": "fixture", "task": "Read and then send", "authorized_tools": ["read", "send"],
              "authority_constraints": {"read": {"allowed_path_prefix": "/home/user/"}},
              "chain_blocked_after": {"read": ["send", "unavailable"]}}
    original = copy.deepcopy(policy)
    twins = policy_twins(policy)
    assert len(twins) == 2
    assert policy == original
    for pair in twins:
        decisions = [reference_decision(pair["tool"], pair["arguments"], variant, pair["history"])
                     for variant in [pair["original"], pair["changed"]]]
        assert set(decisions) == {"allow", "deny"}
        assert pair["original"]["task"] == pair["changed"]["task"]
        assert pair["original"]["authorized_tools"] == pair["changed"]["authorized_tools"]


def test_serialized_policy_retains_decision_and_does_not_alias_history():
    policy = {"authorized_tools": ["read", "send"], "chain_blocked_after": {"read": ["send"]}}
    history = [{"tool_name": "read", "arguments": {"path": "/report"}}]
    packet = render_policy(policy, history)
    decoded = json.loads(packet)
    history.clear()
    policy["chain_blocked_after"].clear()
    assert reference_decision("send", {}, decoded["policy"], decoded["successful_calls"]) == "deny"
