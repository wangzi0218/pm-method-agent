from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pm_method_agent.tool_runtime import (
    LocalToolExecutionOutcome,
    LocalToolExecutionResult,
    LocalToolHandler,
    LocalToolRequest,
    LocalToolRuntime,
)


LOCAL_TEXT_FILE_READ_TOOL_NAME = "local-text-file-read"
TEXT_FILE_READER_ACTION = "text-file-reader.read"


@dataclass
class TextFileReadResult(LocalToolExecutionResult):
    pass


class LocalTextFileReadHandler(LocalToolHandler):
    name = LOCAL_TEXT_FILE_READ_TOOL_NAME

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        path = str(request.request_payload.get("path", "")).strip()
        if not path:
            return LocalToolExecutionOutcome(
                action="file-read-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "InvalidRequest",
                    "message": "Missing path.",
                },
            )

        encoding = str(request.request_payload.get("encoding", "utf-8")).strip() or "utf-8"
        max_characters = int(request.request_payload.get("max_characters", 20000))

        target_path = Path(path)
        if not target_path.is_absolute():
            base_dir = Path(request.cwd or ".")
            target_path = (base_dir / target_path).resolve()
        else:
            target_path = target_path.resolve()

        if not target_path.exists():
            return LocalToolExecutionOutcome(
                action="file-read-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "FileNotFoundError",
                    "message": f"File not found: {target_path}",
                },
            )

        content = target_path.read_text(encoding=encoding)
        truncated = False
        if max_characters >= 0 and len(content) > max_characters:
            content = content[:max_characters]
            truncated = True

        return LocalToolExecutionOutcome(
            action="file-read",
            terminal_state="completed",
            success=True,
            result_ref=f"file:{target_path}",
            output_payload={
                "path": str(target_path),
                "content": content,
                "encoding": encoding,
                "characters_read": len(content),
                "truncated": truncated,
                "max_characters": max_characters,
            },
        )


class LocalTextFileReader:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime = LocalToolRuntime(base_dir=self._base_dir)
        self._handler = LocalTextFileReadHandler()

    def read_text(
        self,
        *,
        path: str,
        workspace_id: str = "default",
        cwd: Optional[str] = None,
        encoding: str = "utf-8",
        max_characters: int = 20000,
        approval_id: str = "",
    ) -> TextFileReadResult:
        resolved_cwd = str(Path(cwd or self._base_dir).resolve())
        resolved_path = Path(path)
        if not resolved_path.is_absolute():
            resolved_path = (Path(resolved_cwd) / resolved_path).resolve()
        else:
            resolved_path = resolved_path.resolve()

        request = LocalToolRequest(
            tool_name=self._handler.name,
            action_name=TEXT_FILE_READER_ACTION,
            workspace_id=workspace_id,
            summary=f"读取文件：{resolved_path}",
            request_payload={
                "path": str(resolved_path),
                "encoding": encoding,
                "max_characters": max_characters,
            },
            read_paths=[str(resolved_path)],
            cwd=resolved_cwd,
            blocked_action="file-read-blocked",
            resume_from=TEXT_FILE_READER_ACTION,
            approval_id=approval_id,
        )
        result = self._runtime.execute_tool(request, handler=self._handler)
        return TextFileReadResult(
            allowed=result.allowed,
            tool_name=result.tool_name,
            action=result.action,
            command_args=list(result.command_args),
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            cwd=result.cwd,
            output_payload=dict(result.output_payload),
            runtime_session=result.runtime_session,
            reason=result.reason,
            terminal_state=result.terminal_state,
            violation_kind=result.violation_kind,
        )
