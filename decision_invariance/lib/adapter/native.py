"""Thin generation replacement for pinned tau2 LLMAgent and UserSimulator.

The injected transport has ``generate(role, payload) -> proposal``. No execution,
retry, evaluator access, task loading, or tool-result fabrication occurs here.
An accepted proposal is an interface-valid message, not an authorization label.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from jsonschema import Draft202012Validator
from tau2.agent.base import is_valid_agent_history_message
from tau2.agent.llm_agent import LLMAgent, LLMAgentState
from tau2.data_model.message import (
    AssistantMessage, MultiToolMessage, ToolCall, ToolMessage, UserMessage,
)
from tau2.user.base import UserState, is_valid_user_history_message
from tau2.user.user_simulator import UserSimulator
from tau2.utils.llm_utils import to_litellm_messages


class GenerationTransport(Protocol):
    def generate(self, role: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ProposalError(ValueError):
    """Malformed proposal; caller retains raw transport output and records failure."""


def _append_input(message, state, *, actor: bool) -> None:
    items = message.tool_messages if isinstance(message, MultiToolMessage) else [message]
    valid = is_valid_agent_history_message if actor else is_valid_user_history_message
    for item in items:
        if not valid(item):
            raise ProposalError("Input contains a message outside this participant's view")
        if actor and isinstance(item, AssistantMessage):
            raise ProposalError("Actor generation input must be user or actor-tool response")
        if not actor and isinstance(item, UserMessage):
            raise ProposalError("User generation input must be actor or user-tool response")
    state.messages.extend(items)


def _known_call_ids(messages) -> set[str]:
    return {
        call.id
        for message in messages
        for call in (getattr(message, "tool_calls", None) or [])
    }


def _proposal_message(proposal, *, tools, messages, actor: bool):
    if not isinstance(proposal, dict) or set(proposal) != {"content", "tool_calls"}:
        raise ProposalError("Proposal must contain exactly content and tool_calls")
    content, calls = proposal["content"], proposal["tool_calls"]
    if content is not None and not isinstance(content, str):
        raise ProposalError("content must be a string or null")
    if not isinstance(calls, list):
        raise ProposalError("tool_calls must be a list")
    has_text = isinstance(content, str) and bool(content.strip())
    if has_text == bool(calls):
        raise ProposalError("Exactly one of nonempty text or tool calls is required")
    known = {tool.name: tool for tool in (tools or [])}
    seen = _known_call_ids(messages)
    requestor = "assistant" if actor else "user"
    native_calls = []
    for call in calls:
        if not isinstance(call, dict) or set(call) != {"id", "name", "arguments"}:
            raise ProposalError("Tool call must contain exactly id, name, arguments")
        if not isinstance(call["id"], str) or not call["id"].strip():
            raise ProposalError("Tool call ID must be a nonempty string")
        if call["id"] in seen:
            raise ProposalError("Duplicate tool call ID in current or prior proposal")
        seen.add(call["id"])
        if not isinstance(call["name"], str) or call["name"] not in known:
            raise ProposalError("Unknown tool")
        if not isinstance(call["arguments"], dict):
            raise ProposalError("Tool arguments must be a JSON object")
        schema = known[call["name"]].openai_schema["function"]["parameters"]
        errors = list(Draft202012Validator(schema).iter_errors(call["arguments"]))
        # Native Tool forwards keyword arguments to the Python function; reject
        # unexpected keywords here instead of allowing pydantic to discard them.
        extra = set(call["arguments"]) - set(schema.get("properties", {}))
        if errors or extra:
            raise ProposalError("Tool arguments do not satisfy the native tool signature")
        native_calls.append(ToolCall(**deepcopy(call), requestor=requestor))
    cls = AssistantMessage if actor else UserMessage
    # No provider usage/cost/checkpoint identity is invented by this adapter.
    result = cls(role=requestor, content=content, tool_calls=native_calls or None)
    result.validate()
    return result


def _payload(participant, messages) -> dict[str, Any]:
    return {
        "messages": to_litellm_messages(messages),
        "tools": [tool.openai_schema for tool in (participant.tools or [])],
        "requested_model": participant.llm,
        "requested_settings": deepcopy(participant.llm_args),
    }


class CodexLLMAgent(LLMAgent):
    def __init__(self, tools, domain_policy, llm=None, llm_args=None, *, transport):
        super().__init__(tools=tools, domain_policy=domain_policy, llm=llm, llm_args=llm_args)
        self.transport = transport

    def generate_next_message(self, message, state: LLMAgentState):
        _append_input(message, state, actor=True)
        proposal = self.transport.generate("actor", _payload(self, state.system_messages + state.messages))
        response = _proposal_message(proposal, tools=self.tools, messages=state.messages, actor=True)
        state.messages.append(response)
        return response, state


class CodexUserSimulator(UserSimulator):
    def __init__(self, tools=None, instructions=None, llm=None, llm_args=None, *, transport):
        super().__init__(tools=tools, instructions=instructions, llm=llm, llm_args=llm_args)
        self.transport = transport

    def _generate_next_message(self, message, state: UserState):
        _append_input(message, state, actor=False)
        proposal = self.transport.generate("user_simulator", _payload(self, state.system_messages + state.flip_roles()))
        response = _proposal_message(proposal, tools=self.tools, messages=state.messages, actor=False)
        state.messages.append(response)
        return response, state


def register_adapters(actor_transport, user_transport, *, registry=None):
    """Bind explicit transports to constructors accepted by native Registry.

    Call in the future launcher process before constructing native components.
    No global default transport and no automatic inference fallback exist.
    """
    if registry is None:
        from tau2.registry import registry

    class BoundCodexLLMAgent(CodexLLMAgent):
        def __init__(self, tools, domain_policy, llm=None, llm_args=None):
            super().__init__(tools, domain_policy, llm, llm_args, transport=actor_transport)

    class BoundCodexUserSimulator(CodexUserSimulator):
        def __init__(self, tools=None, instructions=None, llm=None, llm_args=None):
            super().__init__(tools, instructions, llm, llm_args, transport=user_transport)

    registry.register_agent(BoundCodexLLMAgent, "codex_cli_agent")
    registry.register_user(BoundCodexUserSimulator, "codex_cli_user")
    return {"agent": "codex_cli_agent", "user": "codex_cli_user"}
