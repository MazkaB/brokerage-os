"""Base types for all BOS tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    """Uniform return shape for every tool call."""

    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    tools_used: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "tools_used": self.tools_used,
            "citations": self.citations,
        }
