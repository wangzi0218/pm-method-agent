from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from pm_method_agent.tool_runtime import (
    LocalToolExecutionOutcome,
    LocalToolExecutionResult,
    LocalToolHandler,
    LocalToolRequest,
    LocalToolRuntime,
)


LOCAL_COMMAND_TOOL_NAME = "local-command"
COMMAND_EXECUTOR_ACTION = "command-executor.execute"


@dataclass
class CommandExecutionResult(LocalToolExecutionResult):
    pass


class LocalCommandToolHandler(LocalToolHandler):
    name = LOCAL_COMMAND_TOOL_NAME

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        try:
            completed = subprocess.run(
                list(request.command_args),
                cwd=request.cwd or None,
                capture_output=True,
                text=True,
                check=False,
                timeout=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return LocalToolExecutionOutcome(
                action="command-timeout",
                terminal_state="failed",
                success=False,
                error={
                    "type": "TimeoutExpired",
                    "message": str(exc),
                },
                exit_code=-1,
            )

        if completed.returncode != 0:
            return LocalToolExecutionOutcome(
                action="command-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "CommandFailed",
                    "exit_code": completed.returncode,
                    "stderr": completed.stderr,
                    "message": completed.stderr or f"command exited with {completed.returncode}",
                },
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
            )

        return LocalToolExecutionOutcome(
            action="command-executed",
            terminal_state="completed",
            success=True,
            result_ref=f"command:{' '.join(request.command_args)}",
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )


class LocalCommandExecutor:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime = LocalToolRuntime(base_dir=self._base_dir)
        self._handler = LocalCommandToolHandler()

    def execute(
        self,
        *,
        command_args: List[str],
        workspace_id: str = "default",
        cwd: Optional[str] = None,
        write_paths: Optional[List[str]] = None,
        timeout_seconds: float = 15.0,
        approval_id: str = "",
    ) -> CommandExecutionResult:
        normalized_args = [str(item).strip() for item in command_args if str(item).strip()]
        if not normalized_args:
            raise ValueError("Missing command args.")

        resolved_cwd = str(Path(cwd or self._base_dir).resolve())
        request = LocalToolRequest(
            tool_name=self._handler.name,
            action_name=COMMAND_EXECUTOR_ACTION,
            workspace_id=workspace_id,
            summary=f"执行命令：{' '.join(normalized_args)}",
            request_payload={
                "command_args": normalized_args,
                "cwd": resolved_cwd,
                "write_paths": list(write_paths or []),
                "timeout_seconds": timeout_seconds,
            },
            command_args=list(normalized_args),
            write_paths=list(write_paths or []),
            cwd=resolved_cwd,
            timeout_seconds=timeout_seconds,
            blocked_action="command-blocked",
            resume_from=COMMAND_EXECUTOR_ACTION,
            approval_id=approval_id,
        )
        result = self._runtime.execute_tool(request, handler=self._handler)
        return CommandExecutionResult(
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
