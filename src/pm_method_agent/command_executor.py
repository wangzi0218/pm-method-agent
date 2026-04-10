from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from pm_method_agent.hook_enforcement import HookExecutionBlockedError, run_pre_operation_hooks
from pm_method_agent.runtime_policy import load_runtime_policy
from pm_method_agent.runtime_session_service import (
    complete_runtime_query,
    complete_tool_call,
    default_runtime_session_store,
    fail_runtime_query,
    fail_tool_call,
    get_or_create_runtime_session,
    request_tool_call,
    save_runtime_session,
    start_runtime_query,
)


@dataclass
class CommandExecutionResult:
    allowed: bool
    action: str
    command_args: List[str]
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    cwd: str = ""
    runtime_session: Optional[object] = None
    reason: str = ""
    terminal_state: str = ""
    violation_kind: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "command_args": list(self.command_args),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "cwd": self.cwd,
            "runtime_session": self.runtime_session.to_dict() if self.runtime_session is not None else None,
            "reason": self.reason,
            "terminal_state": self.terminal_state,
            "violation_kind": self.violation_kind,
        }


class LocalCommandExecutor:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime_policy = load_runtime_policy(base_dir=self._base_dir)
        self._runtime_session_store = default_runtime_session_store(self._base_dir)

    def execute(
        self,
        *,
        command_args: List[str],
        workspace_id: str = "default",
        cwd: Optional[str] = None,
        write_paths: Optional[List[str]] = None,
        timeout_seconds: float = 15.0,
    ) -> CommandExecutionResult:
        normalized_args = [str(item).strip() for item in command_args if str(item).strip()]
        if not normalized_args:
            raise ValueError("Missing command args.")

        resolved_cwd = str(Path(cwd or self._base_dir).resolve())
        runtime_session = get_or_create_runtime_session(workspace_id, store=self._runtime_session_store)
        start_runtime_query(
            runtime_session,
            message=f"执行命令：{' '.join(normalized_args)}",
        )

        try:
            run_pre_operation_hooks(
                runtime_session,
                self._runtime_policy,
                action_name="command-executor.execute",
                command_args=normalized_args,
                write_paths=write_paths,
            )
        except HookExecutionBlockedError as exc:
            complete_runtime_query(
                runtime_session,
                terminal_state=exc.violation.terminal_state,
                action="command-blocked",
                resume_from="command-executor.execute",
            )
            save_runtime_session(runtime_session, store=self._runtime_session_store)
            return CommandExecutionResult(
                allowed=False,
                action="command-blocked",
                command_args=normalized_args,
                cwd=resolved_cwd,
                runtime_session=runtime_session,
                reason=exc.violation.reason,
                terminal_state=exc.violation.terminal_state,
                violation_kind=exc.violation.violation_kind,
            )

        entry = request_tool_call(
            runtime_session,
            tool_name="local-command-executor",
            request_payload={
                "command_args": normalized_args,
                "cwd": resolved_cwd,
                "write_paths": list(write_paths or []),
                "timeout_seconds": timeout_seconds,
            },
        )
        try:
            completed = subprocess.run(
                normalized_args,
                cwd=resolved_cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            fail_tool_call(
                runtime_session,
                call_id=str(entry["call_id"]),
                error={
                    "type": "TimeoutExpired",
                    "message": str(exc),
                },
            )
            fail_runtime_query(
                runtime_session,
                action="command-timeout",
                resume_from="command-executor.execute",
                error={
                    "type": "TimeoutExpired",
                    "message": str(exc),
                },
            )
            save_runtime_session(runtime_session, store=self._runtime_session_store)
            return CommandExecutionResult(
                allowed=True,
                action="command-timeout",
                command_args=normalized_args,
                exit_code=-1,
                cwd=resolved_cwd,
                runtime_session=runtime_session,
                reason=str(exc),
                terminal_state="failed",
            )

        if completed.returncode != 0:
            fail_tool_call(
                runtime_session,
                call_id=str(entry["call_id"]),
                error={
                    "type": "CommandFailed",
                    "exit_code": completed.returncode,
                    "stderr": completed.stderr,
                },
            )
            fail_runtime_query(
                runtime_session,
                action="command-failed",
                resume_from="command-executor.execute",
                error={
                    "type": "CommandFailed",
                    "exit_code": completed.returncode,
                    "stderr": completed.stderr,
                },
            )
            save_runtime_session(runtime_session, store=self._runtime_session_store)
            return CommandExecutionResult(
                allowed=True,
                action="command-failed",
                command_args=normalized_args,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                cwd=resolved_cwd,
                runtime_session=runtime_session,
                terminal_state="failed",
            )

        complete_tool_call(
            runtime_session,
            call_id=str(entry["call_id"]),
            result_ref=f"command:{' '.join(normalized_args)}",
        )
        complete_runtime_query(
            runtime_session,
            terminal_state="completed",
            action="command-executed",
            resume_from="command-executor.execute",
        )
        save_runtime_session(runtime_session, store=self._runtime_session_store)
        return CommandExecutionResult(
            allowed=True,
            action="command-executed",
            command_args=normalized_args,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            cwd=resolved_cwd,
            runtime_session=runtime_session,
            terminal_state="completed",
        )
