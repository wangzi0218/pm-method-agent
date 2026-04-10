from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from pm_method_agent.models import RuntimeSession
from pm_method_agent.runtime_session_service import (
    complete_runtime_query,
    default_runtime_session_store,
    expire_runtime_approval,
    get_or_create_runtime_session,
    get_runtime_approval,
    reject_runtime_approval,
    save_runtime_session,
    start_runtime_query,
)
from pm_method_agent.runtime_policy import load_runtime_policy, resolve_runtime_approval_handling
from pm_method_agent.local_tools import LocalToolRegistry
from pm_method_agent.platform_tools import PlatformToolRegistry


@dataclass
class RuntimeApprovalResult:
    action: str
    approval_id: str
    status: str
    workspace_id: str
    runtime_session: RuntimeSession
    reason: str = ""
    output_payload: Dict[str, object] = field(default_factory=dict)
    terminal_state: str = "completed"

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "approval_id": self.approval_id,
            "status": self.status,
            "workspace_id": self.workspace_id,
            "reason": self.reason,
            "output_payload": dict(self.output_payload),
            "terminal_state": self.terminal_state,
            "runtime_session": self.runtime_session.to_dict(),
        }


class RuntimeToolRegistry:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._local_tools = LocalToolRegistry(base_dir=self._base_dir)
        self._platform_tools = PlatformToolRegistry(base_dir=self._base_dir)
        self._runtime_session_store = default_runtime_session_store(self._base_dir)
        self._runtime_policy = load_runtime_policy(base_dir=self._base_dir)

    def list_tools(self) -> List[dict]:
        return self._local_tools.list_tools() + self._platform_tools.list_tools()

    def describe_tool(self, tool_name: str) -> dict:
        if self._local_tools.supports(tool_name):
            return self._local_tools.describe_tool(tool_name)
        if self._platform_tools.supports(tool_name):
            return self._platform_tools.describe_tool(tool_name)
        raise ValueError(f"Unsupported tool: {tool_name or 'unknown'}")

    def execute(self, *, tool_name: str, payload: Dict[str, object]) -> object:
        if self._local_tools.supports(tool_name):
            return self._local_tools.execute(tool_name=tool_name, payload=payload)
        if self._platform_tools.supports(tool_name):
            return self._platform_tools.execute(tool_name=tool_name, payload=payload)
        raise ValueError(f"Unsupported tool: {tool_name or 'unknown'}")

    def list_pending_approvals(self, *, workspace_id: str) -> List[dict]:
        runtime_session = get_or_create_runtime_session(
            workspace_id,
            store=self._runtime_session_store,
        )
        return [dict(item) for item in runtime_session.pending_approvals]

    def approve_pending_approval(self, *, workspace_id: str, approval_id: str) -> object:
        runtime_session = get_or_create_runtime_session(
            workspace_id,
            store=self._runtime_session_store,
        )
        for item in runtime_session.pending_approvals:
            if str(item.get("approval_id")) != approval_id:
                continue
            payload = dict(item.get("request_payload", {}))
            payload["workspace_id"] = workspace_id
            payload["_approval_id"] = approval_id
            return self.execute(
                tool_name=str(item.get("tool_name", "")).strip(),
                payload=payload,
            )
        return self._build_resolved_approval_result(
            workspace_id=workspace_id,
            approval_id=approval_id,
            operation="approve",
        )

    def reject_pending_approval(
        self,
        *,
        workspace_id: str,
        approval_id: str,
        reason: str = "",
    ) -> RuntimeApprovalResult:
        return self._resolve_pending_approval_without_execution(
            workspace_id=workspace_id,
            approval_id=approval_id,
            resolution="rejected",
            reason=reason,
        )

    def expire_pending_approval(
        self,
        *,
        workspace_id: str,
        approval_id: str,
        reason: str = "",
    ) -> RuntimeApprovalResult:
        return self._resolve_pending_approval_without_execution(
            workspace_id=workspace_id,
            approval_id=approval_id,
            resolution="expired",
            reason=reason or "approval expired before execution",
        )

    def _resolve_pending_approval_without_execution(
        self,
        *,
        workspace_id: str,
        approval_id: str,
        resolution: str,
        reason: str,
    ) -> RuntimeApprovalResult:
        runtime_session = get_or_create_runtime_session(
            workspace_id,
            store=self._runtime_session_store,
        )
        if not any(str(item.get("approval_id")) == approval_id for item in runtime_session.pending_approvals):
            return self._build_resolved_approval_result(
                workspace_id=workspace_id,
                approval_id=approval_id,
                operation="reject" if resolution == "rejected" else "expire",
            )
        start_runtime_query(
            runtime_session,
            message=f"{'拒绝' if resolution == 'rejected' else '过期处理'}待确认操作：{approval_id}",
        )
        pending_approval = next(
            item for item in runtime_session.pending_approvals if str(item.get("approval_id")) == approval_id
        )
        if resolution == "expired":
            handling = resolve_runtime_approval_handling(
                self._runtime_policy,
                action_name=str(pending_approval.get("action_name", "")).strip(),
            )
            if handling.mode == "manual-only":
                complete_runtime_query(
                    runtime_session,
                    terminal_state="blocked",
                    action="approval-expire-not-allowed",
                    resume_from=str(pending_approval.get("action_name", "")).strip(),
                )
                save_runtime_session(runtime_session, store=self._runtime_session_store)
                return RuntimeApprovalResult(
                    action="approval-expire-not-allowed",
                    approval_id=approval_id,
                    status="pending",
                    workspace_id=workspace_id,
                    runtime_session=runtime_session,
                    reason=handling.reason,
                    output_payload={"approval": dict(pending_approval)},
                    terminal_state="blocked",
                )
        try:
            if resolution == "rejected":
                approval = reject_runtime_approval(
                    runtime_session,
                    approval_id=approval_id,
                    reason=reason,
                )
                action = "approval-rejected"
                terminal_state = "cancelled"
            else:
                approval = expire_runtime_approval(
                    runtime_session,
                    approval_id=approval_id,
                    reason=reason,
                )
                action = "approval-expired"
                terminal_state = "cancelled"
        except KeyError:
            return self._build_resolved_approval_result(
                workspace_id=workspace_id,
                approval_id=approval_id,
                operation="reject" if resolution == "rejected" else "expire",
            )

        complete_runtime_query(
            runtime_session,
            terminal_state=terminal_state,
            action=action,
            resume_from=str(approval.get("action_name", "")),
        )
        save_runtime_session(runtime_session, store=self._runtime_session_store)
        return RuntimeApprovalResult(
            action=action,
            approval_id=approval_id,
            status=resolution,
            workspace_id=workspace_id,
            runtime_session=runtime_session,
            reason=reason,
            output_payload={"approval": dict(approval)},
            terminal_state=terminal_state,
        )

    def _build_resolved_approval_result(
        self,
        *,
        workspace_id: str,
        approval_id: str,
        operation: str,
    ) -> RuntimeApprovalResult:
        runtime_session = get_or_create_runtime_session(
            workspace_id,
            store=self._runtime_session_store,
        )
        try:
            approval = get_runtime_approval(runtime_session, approval_id=approval_id)
        except KeyError as exc:
            raise ValueError(
                f"Approval '{approval_id}' does not exist in workspace '{workspace_id}'."
            ) from exc

        status = str(approval.get("status", "")).strip() or "unknown"
        return RuntimeApprovalResult(
            action=f"approval-already-{status}",
            approval_id=approval_id,
            status=status,
            workspace_id=workspace_id,
            runtime_session=runtime_session,
            reason=(
                f"这条待确认操作已经处理过了，当前状态是：{status}。"
                if operation == "approve"
                else f"这条待确认操作已经不在待处理队列里，当前状态是：{status}。"
            ),
            output_payload={"approval": dict(approval)},
            terminal_state="completed",
        )
