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


LOCAL_TEXT_FILE_WRITE_TOOL_NAME = "local-text-file-write"
TEXT_FILE_WRITER_ACTION = "text-file-writer.write"


@dataclass
class TextFileWriteResult(LocalToolExecutionResult):
    pass


class LocalTextFileWriteHandler(LocalToolHandler):
    name = LOCAL_TEXT_FILE_WRITE_TOOL_NAME

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        path = str(request.request_payload.get("path", "")).strip()
        if not path:
            return LocalToolExecutionOutcome(
                action="file-write-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "InvalidRequest",
                    "message": "Missing path.",
                },
            )
        content = str(request.request_payload.get("content", ""))
        append = bool(request.request_payload.get("append", False))
        create_dirs = bool(request.request_payload.get("create_dirs", True))
        encoding = str(request.request_payload.get("encoding", "utf-8")).strip() or "utf-8"

        target_path = Path(path)
        if not target_path.is_absolute():
            base_dir = Path(request.cwd or ".")
            target_path = (base_dir / target_path).resolve()
        else:
            target_path = target_path.resolve()

        if create_dirs:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        if append and target_path.exists():
            existing = target_path.read_text(encoding=encoding)
            target_path.write_text(existing + content, encoding=encoding)
        else:
            target_path.write_text(content, encoding=encoding)

        return LocalToolExecutionOutcome(
            action="file-written",
            terminal_state="completed",
            success=True,
            result_ref=f"file:{target_path}",
            output_payload={
                "path": str(target_path),
                "bytes_written": len(content.encode(encoding)),
                "characters_written": len(content),
                "append": append,
                "encoding": encoding,
            },
        )


class LocalTextFileWriter:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime = LocalToolRuntime(base_dir=self._base_dir)
        self._handler = LocalTextFileWriteHandler()

    def write_text(
        self,
        *,
        path: str,
        content: str,
        workspace_id: str = "default",
        cwd: Optional[str] = None,
        append: bool = False,
        create_dirs: bool = True,
        encoding: str = "utf-8",
    ) -> TextFileWriteResult:
        resolved_cwd = str(Path(cwd or self._base_dir).resolve())
        resolved_path = Path(path)
        if not resolved_path.is_absolute():
            resolved_path = (Path(resolved_cwd) / resolved_path).resolve()
        else:
            resolved_path = resolved_path.resolve()

        request = LocalToolRequest(
            tool_name=self._handler.name,
            action_name=TEXT_FILE_WRITER_ACTION,
            workspace_id=workspace_id,
            summary=f"写入文件：{resolved_path}",
            request_payload={
                "path": str(resolved_path),
                "content": content,
                "append": append,
                "create_dirs": create_dirs,
                "encoding": encoding,
            },
            write_paths=[str(resolved_path)],
            cwd=resolved_cwd,
            blocked_action="file-write-blocked",
            resume_from=TEXT_FILE_WRITER_ACTION,
        )
        result = self._runtime.execute_tool(request, handler=self._handler)
        return TextFileWriteResult(
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
