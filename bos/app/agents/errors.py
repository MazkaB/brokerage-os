"""Agent-layer exceptions."""
from __future__ import annotations


class AgentError(Exception):
    """Base error for any agent-layer failure."""


class LLMUnavailable(AgentError):
    """The LLM call failed (quota, auth, network). Callers must fall back."""
