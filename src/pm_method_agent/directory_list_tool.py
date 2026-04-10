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


LOCAL_DIRECTORY_LIST_TOOL_NAME = "local-directory-list"
DIRECTORY_LISTER_ACTION = "directory-lister.list"


@dataclass
class DirectoryListResult(LocalToolExecutionResult):
    pass


class LocalDirectoryListHandler(LocalToolHandler):
    name = LOCAL_DIRECTORY_LIST_TOOL_NAME

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        path = str(request.request_payload.get("path", "")).strip()
        if not path:
            return LocalToolExecutionOutcome(
                action="directory-list-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "InvalidRequest",
                    "message": "Missing path.",
                },
            )

        include_hidden = bool(request.request_payload.get("include_hidden", False))
        recursive = bool(request.request_payload.get("recursive", False))
        max_entries = int(request.request_payload.get("max_entries", 200))

        target_path = Path(path)
        if not target_path.is_absolute():
            base_dir = Path(request.cwd or ".")
            target_path = (base_dir / target_path).resolve()
        else:
            target_path = target_path.resolve()

        if not target_path.exists():
            return LocalToolExecutionOutcome(
                action="directory-list-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "FileNotFoundError",
                    "message": f"Directory not found: {target_path}",
                },
            )

        if not target_path.is_dir():
            return LocalToolExecutionOutcome(
                action="directory-list-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "NotADirectoryError",
                    "message": f"Not a directory: {target_path}",
                },
            )

        entries: list[dict[str, object]] = []
        truncated = False

        candidates = (
            sorted(target_path.rglob("*"), key=lambda item: str(item.relative_to(target_path)))
            if recursive
            else sorted(target_path.iterdir(), key=lambda item: item.name)
        )
        for item in candidates:
            relative_name = str(item.relative_to(target_path))
            if not include_hidden and any(part.startswith(".") for part in Path(relative_name).parts):
                continue
            if max_entries >= 0 and len(entries) >= max_entries:
                truncated = True
                break
            entry_type = "directory" if item.is_dir() else "file"
            entries.append(
                {
                    "name": item.name,
                    "relative_path": relative_name,
                    "path": str(item),
                    "entry_type": entry_type,
                }
            )

        return LocalToolExecutionOutcome(
            action="directory-listed",
            terminal_state="completed",
            success=True,
            result_ref=f"directory:{target_path}",
            output_payload={
                "path": str(target_path),
                "entries": entries,
                "recursive": recursive,
                "include_hidden": include_hidden,
                "truncated": truncated,
                "max_entries": max_entries,
                "entry_count": len(entries),
            },
        )


class LocalDirectoryLister:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime = LocalToolRuntime(base_dir=self._base_dir)
        self._handler = LocalDirectoryListHandler()

    def list_directory(
        self,
        *,
        path: str,
        workspace_id: str = "default",
        cwd: Optional[str] = None,
        recursive: bool = False,
        include_hidden: bool = False,
        max_entries: int = 200,
        approval_id: str = "",
    ) -> DirectoryListResult:
        resolved_cwd = str(Path(cwd or self._base_dir).resolve())
        resolved_path = Path(path)
        if not resolved_path.is_absolute():
            resolved_path = (Path(resolved_cwd) / resolved_path).resolve()
        else:
            resolved_path = resolved_path.resolve()

        request = LocalToolRequest(
            tool_name=self._handler.name,
            action_name=DIRECTORY_LISTER_ACTION,
            workspace_id=workspace_id,
            summary=f"列目录：{resolved_path}",
            request_payload={
                "path": str(resolved_path),
                "recursive": recursive,
                "include_hidden": include_hidden,
                "max_entries": max_entries,
            },
            read_paths=[str(resolved_path)],
            cwd=resolved_cwd,
            blocked_action="directory-list-blocked",
            resume_from=DIRECTORY_LISTER_ACTION,
            approval_id=approval_id,
        )
        result = self._runtime.execute_tool(request, handler=self._handler)
        return DirectoryListResult(
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
