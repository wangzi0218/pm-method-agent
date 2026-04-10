from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class ToolDescriptor:
    tool_name: str
    kind: str
    summary: str
    execution_scope: str
    input_schema: Dict[str, object] = field(default_factory=dict)
    supports_read_paths: bool = False
    supports_write_paths: bool = False
    supports_command_args: bool = False
    default_timeout_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "kind": self.kind,
            "summary": self.summary,
            "execution_scope": self.execution_scope,
            "input_schema": dict(self.input_schema),
            "supports_read_paths": self.supports_read_paths,
            "supports_write_paths": self.supports_write_paths,
            "supports_command_args": self.supports_command_args,
            "default_timeout_seconds": self.default_timeout_seconds,
        }
