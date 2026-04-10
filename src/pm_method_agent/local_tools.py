from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from pm_method_agent.command_executor import LOCAL_COMMAND_TOOL_NAME, LocalCommandExecutor
from pm_method_agent.text_file_tool import LOCAL_TEXT_FILE_WRITE_TOOL_NAME, LocalTextFileWriter


@dataclass(frozen=True)
class LocalToolDescriptor:
    tool_name: str
    kind: str
    summary: str

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "kind": self.kind,
            "summary": self.summary,
        }


LOCAL_TOOL_DESCRIPTORS = [
    LocalToolDescriptor(
        tool_name=LOCAL_COMMAND_TOOL_NAME,
        kind="command",
        summary="执行本地命令，并经过 hook、策略和执行账本。",
    ),
    LocalToolDescriptor(
        tool_name=LOCAL_TEXT_FILE_WRITE_TOOL_NAME,
        kind="file-write",
        summary="写入本地文本文件，并经过写入路径策略与执行账本。",
    ),
]


class LocalToolRegistry:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._command_executor = LocalCommandExecutor(base_dir=base_dir)
        self._text_file_writer = LocalTextFileWriter(base_dir=base_dir)

    def list_tools(self) -> List[dict]:
        return [item.to_dict() for item in LOCAL_TOOL_DESCRIPTORS]

    def execute(self, *, tool_name: str, payload: Dict[str, object]) -> object:
        if tool_name == LOCAL_COMMAND_TOOL_NAME:
            return self._command_executor.execute(
                command_args=_ensure_string_list(payload.get("command_args")),
                workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                cwd=_optional_string(payload.get("cwd")),
                write_paths=_ensure_string_list(payload.get("write_paths")),
                timeout_seconds=_ensure_float(payload.get("timeout_seconds"), default=15.0),
            )
        if tool_name == LOCAL_TEXT_FILE_WRITE_TOOL_NAME:
            return self._text_file_writer.write_text(
                path=_required_string(payload.get("path"), field_name="path"),
                content=_required_string(payload.get("content"), field_name="content"),
                workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                cwd=_optional_string(payload.get("cwd")),
                append=bool(payload.get("append", False)),
                create_dirs=bool(payload.get("create_dirs", True)),
                encoding=_optional_string(payload.get("encoding")) or "utf-8",
            )
        raise ValueError(f"Unsupported local tool: {tool_name or 'unknown'}")


def _ensure_string_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _required_string(value: object, *, field_name: str) -> str:
    rendered = _optional_string(value)
    if not rendered:
        raise ValueError(f"Missing {field_name}.")
    return rendered


def _ensure_float(value: object, *, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)
