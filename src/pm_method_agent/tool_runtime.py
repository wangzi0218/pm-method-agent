from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from pm_method_agent.hook_enforcement import HookExecutionBlockedError, run_pre_operation_hooks
from pm_method_agent.models import RuntimeSession
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
class LocalToolRequest:
    tool_name: str
    action_name: str
    workspace_id: str = "default"
    summary: str = ""
    request_payload: Dict[str, object] = field(default_factory=dict)
    command_args: List[str] = field(default_factory=list)
    write_paths: List[str] = field(default_factory=list)
    cwd: str = ""
    timeout_seconds: float = 15.0
    blocked_action: str = "tool-blocked"
    resume_from: str = ""


@dataclass
class LocalToolExecutionOutcome:
    action: str
    terminal_state: str
    success: bool
    result_ref: str = ""
    output_payload: Dict[str, object] = field(default_factory=dict)
    error: Dict[str, object] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


@dataclass
class LocalToolExecutionResult:
    allowed: bool
    tool_name: str
    action: str
    command_args: List[str] = field(default_factory=list)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    cwd: str = ""
    output_payload: Dict[str, object] = field(default_factory=dict)
    runtime_session: Optional[RuntimeSession] = None
    reason: str = ""
    terminal_state: str = ""
    violation_kind: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "tool_name": self.tool_name,
            "action": self.action,
            "command_args": list(self.command_args),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "cwd": self.cwd,
            "output_payload": dict(self.output_payload),
            "runtime_session": self.runtime_session.to_dict() if self.runtime_session is not None else None,
            "reason": self.reason,
            "terminal_state": self.terminal_state,
            "violation_kind": self.violation_kind,
        }


class LocalToolHandler(Protocol):
    name: str

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        ...


class LocalToolRuntime:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime_policy = load_runtime_policy(base_dir=self._base_dir)
        self._runtime_session_store = default_runtime_session_store(self._base_dir)

    def execute_tool(
        self,
        request: LocalToolRequest,
        *,
        handler: LocalToolHandler,
    ) -> LocalToolExecutionResult:
        runtime_session = get_or_create_runtime_session(
            request.workspace_id,
            store=self._runtime_session_store,
        )
        start_runtime_query(
            runtime_session,
            message=request.summary or f"执行工具：{request.tool_name}",
        )

        try:
            run_pre_operation_hooks(
                runtime_session,
                self._runtime_policy,
                action_name=request.action_name,
                command_args=request.command_args,
                write_paths=request.write_paths,
            )
        except HookExecutionBlockedError as exc:
            complete_runtime_query(
                runtime_session,
                terminal_state=exc.violation.terminal_state,
                action=request.blocked_action,
                resume_from=request.resume_from or request.action_name,
            )
            save_runtime_session(runtime_session, store=self._runtime_session_store)
            return LocalToolExecutionResult(
                allowed=False,
                tool_name=request.tool_name,
                action=request.blocked_action,
                command_args=list(request.command_args),
                cwd=request.cwd,
                runtime_session=runtime_session,
                reason=exc.violation.reason,
                terminal_state=exc.violation.terminal_state,
                violation_kind=exc.violation.violation_kind,
            )

        entry = request_tool_call(
            runtime_session,
            tool_name=request.tool_name,
            request_payload=dict(request.request_payload),
        )
        try:
            outcome = handler.execute(request)
        except Exception as exc:
            fail_tool_call(
                runtime_session,
                call_id=str(entry["call_id"]),
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            fail_runtime_query(
                runtime_session,
                action="tool-execution-failed",
                resume_from=request.resume_from or request.action_name,
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            save_runtime_session(runtime_session, store=self._runtime_session_store)
            return LocalToolExecutionResult(
                allowed=True,
                tool_name=request.tool_name,
                action="tool-execution-failed",
                command_args=list(request.command_args),
                cwd=request.cwd,
                runtime_session=runtime_session,
                reason=str(exc),
                terminal_state="failed",
            )

        if not outcome.success:
            fail_tool_call(
                runtime_session,
                call_id=str(entry["call_id"]),
                error=dict(outcome.error),
            )
            fail_runtime_query(
                runtime_session,
                action=outcome.action,
                resume_from=request.resume_from or request.action_name,
                error=dict(outcome.error),
            )
            save_runtime_session(runtime_session, store=self._runtime_session_store)
            return LocalToolExecutionResult(
                allowed=True,
                tool_name=request.tool_name,
                action=outcome.action,
                command_args=list(request.command_args),
                exit_code=outcome.exit_code,
                stdout=outcome.stdout,
                stderr=outcome.stderr,
                cwd=request.cwd,
                output_payload=dict(outcome.output_payload),
                runtime_session=runtime_session,
                reason=str(outcome.error.get("message", "") or ""),
                terminal_state=outcome.terminal_state,
            )

        complete_tool_call(
            runtime_session,
            call_id=str(entry["call_id"]),
            result_ref=outcome.result_ref,
        )
        complete_runtime_query(
            runtime_session,
            terminal_state=outcome.terminal_state,
            action=outcome.action,
            resume_from=request.resume_from or request.action_name,
        )
        save_runtime_session(runtime_session, store=self._runtime_session_store)
        return LocalToolExecutionResult(
            allowed=True,
            tool_name=request.tool_name,
            action=outcome.action,
            command_args=list(request.command_args),
            exit_code=outcome.exit_code,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            cwd=request.cwd,
            output_payload=dict(outcome.output_payload),
            runtime_session=runtime_session,
            terminal_state=outcome.terminal_state,
        )
