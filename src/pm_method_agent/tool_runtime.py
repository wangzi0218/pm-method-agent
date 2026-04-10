from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from pm_method_agent.hook_enforcement import HookExecutionBlockedError, run_pre_operation_hooks
from pm_method_agent.models import RuntimeSession
from pm_method_agent.runtime_policy import (
    RuntimeApprovalHandlingDecision,
    load_runtime_policy,
    resolve_runtime_approval_handling,
)
from pm_method_agent.runtime_session_service import (
    approve_runtime_approval,
    append_runtime_event,
    complete_runtime_query,
    complete_tool_call,
    default_runtime_session_store,
    expire_runtime_approval,
    fail_runtime_query,
    fail_tool_call,
    get_or_create_runtime_session,
    get_pending_runtime_approval,
    request_tool_call,
    request_runtime_approval,
    save_runtime_session,
    start_runtime_query,
)
from pm_method_agent.workspace_service import default_workspace_store, get_or_create_workspace, get_workspace_approval_preferences


@dataclass
class LocalToolRequest:
    tool_name: str
    action_name: str
    workspace_id: str = "default"
    summary: str = ""
    request_payload: Dict[str, object] = field(default_factory=dict)
    command_args: List[str] = field(default_factory=list)
    read_paths: List[str] = field(default_factory=list)
    write_paths: List[str] = field(default_factory=list)
    cwd: str = ""
    timeout_seconds: float = 15.0
    blocked_action: str = "tool-blocked"
    resume_from: str = ""
    approval_id: str = ""


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
        self._workspace_store = default_workspace_store(self._base_dir)

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
        workspace_state = get_or_create_workspace(
            request.workspace_id,
            store=self._workspace_store,
        )
        workspace_approval_preferences = get_workspace_approval_preferences(workspace_state)
        approved_entry = None
        if request.approval_id:
            approved_entry = approve_runtime_approval(
                runtime_session,
                approval_id=request.approval_id,
            )

        try:
            run_pre_operation_hooks(
                runtime_session,
                self._runtime_policy,
                action_name=request.action_name,
                command_args=request.command_args,
                read_paths=request.read_paths,
                write_paths=request.write_paths,
            )
        except HookExecutionBlockedError as exc:
            if request.approval_id and exc.violation.violation_kind == "approval-required":
                _append_approval_override_event(
                    runtime_session,
                    approval_id=request.approval_id,
                    action_name=request.action_name,
                )
            else:
                pending_approval = None
                if exc.violation.violation_kind == "approval-required":
                    pending_approval = request_runtime_approval(
                        runtime_session,
                        tool_name=request.tool_name,
                        action_name=request.action_name,
                        request_payload=dict(request.request_payload),
                        command_args=list(request.command_args),
                        read_paths=list(request.read_paths),
                        write_paths=list(request.write_paths),
                        cwd=request.cwd,
                        timeout_seconds=request.timeout_seconds,
                        blocked_action=request.blocked_action,
                        resume_from=request.resume_from or request.action_name,
                        violation={
                            "reason": exc.violation.reason,
                            "violation_kind": exc.violation.violation_kind,
                            "terminal_state": exc.violation.terminal_state,
                        },
                    )
                    handling = resolve_runtime_approval_handling(
                        self._runtime_policy,
                        action_name=request.action_name,
                        workspace_auto_approve_actions=list(
                            workspace_approval_preferences.get("auto_approve_actions", [])
                        ),
                    )
                    auto_resolution = _apply_approval_handling(
                        runtime_session,
                        pending_approval=pending_approval,
                        handling=handling,
                    )
                    if auto_resolution is not None:
                        save_runtime_session(runtime_session, store=self._runtime_session_store)
                        if auto_resolution["status"] == "approved":
                            approved_entry = auto_resolution
                        else:
                            complete_runtime_query(
                                runtime_session,
                                terminal_state="cancelled",
                                action=f"approval-{auto_resolution['status']}",
                                resume_from=request.resume_from or request.action_name,
                            )
                            save_runtime_session(runtime_session, store=self._runtime_session_store)
                            return LocalToolExecutionResult(
                                allowed=False,
                                tool_name=request.tool_name,
                                action=f"approval-{auto_resolution['status']}",
                                command_args=list(request.command_args),
                                cwd=request.cwd,
                                output_payload={"approval": auto_resolution},
                                runtime_session=runtime_session,
                                reason=str(auto_resolution.get("reason", "")).strip(),
                                terminal_state="cancelled",
                                violation_kind="approval-required",
                            )
                    if approved_entry is not None:
                        _append_approval_override_event(
                            runtime_session,
                            approval_id=str(approved_entry["approval_id"]),
                            action_name=request.action_name,
                        )
                        save_runtime_session(runtime_session, store=self._runtime_session_store)
                        # 已经转成自动批准，继续走后面的真实执行。
                        pass
                    else:
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
                            output_payload={"pending_approval": pending_approval} if pending_approval else {},
                            runtime_session=runtime_session,
                            reason=exc.violation.reason,
                            terminal_state=exc.violation.terminal_state,
                            violation_kind=exc.violation.violation_kind,
                        )
                else:
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
                output_payload={"approved_request": approved_entry} if approved_entry is not None else {},
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
                output_payload=_with_approved_request(outcome.output_payload, approved_entry),
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
            output_payload=_with_approved_request(outcome.output_payload, approved_entry),
            runtime_session=runtime_session,
            terminal_state=outcome.terminal_state,
        )

    def list_pending_approvals(self, *, workspace_id: str) -> List[Dict[str, object]]:
        runtime_session = get_or_create_runtime_session(
            workspace_id,
            store=self._runtime_session_store,
        )
        return [dict(item) for item in runtime_session.pending_approvals]

    def load_pending_approval(self, *, workspace_id: str, approval_id: str) -> Dict[str, object]:
        runtime_session = get_or_create_runtime_session(
            workspace_id,
            store=self._runtime_session_store,
        )
        return dict(get_pending_runtime_approval(runtime_session, approval_id=approval_id))


def _with_approved_request(
    output_payload: Dict[str, object],
    approved_entry: Optional[Dict[str, object]],
) -> Dict[str, object]:
    rendered = dict(output_payload)
    if approved_entry is not None:
        rendered["approved_request"] = dict(approved_entry)
    return rendered


def _append_approval_override_event(
    runtime_session: RuntimeSession,
    *,
    approval_id: str,
    action_name: str,
) -> None:
    append_runtime_event(
        runtime_session,
        "approval-override-applied",
        {
            "approval_id": approval_id,
            "action_name": action_name,
        },
    )


def _apply_approval_handling(
    runtime_session: RuntimeSession,
    *,
    pending_approval: Dict[str, object],
    handling: RuntimeApprovalHandlingDecision,
) -> Optional[Dict[str, object]]:
    if handling.mode == "auto-approve":
        approved = approve_runtime_approval(
            runtime_session,
            approval_id=str(pending_approval["approval_id"]),
            actor=handling.source or "runtime-policy",
        )
        append_runtime_event(
            runtime_session,
            "approval-auto-approved",
            {
                "approval_id": approved["approval_id"],
                "source": handling.source,
                "reason": handling.reason,
            },
        )
        return approved
    if handling.mode == "auto-expire":
        expired = expire_runtime_approval(
            runtime_session,
            approval_id=str(pending_approval["approval_id"]),
            actor=handling.source or "runtime-policy",
            reason=handling.reason,
        )
        append_runtime_event(
            runtime_session,
            "approval-auto-expired",
            {
                "approval_id": expired["approval_id"],
                "source": handling.source,
                "reason": handling.reason,
            },
        )
        return expired
    return None
