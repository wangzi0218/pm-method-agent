from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from pm_method_agent.agent_shell import PMMethodAgentShell
from pm_method_agent.models import RuntimeSession
from pm_method_agent.renderers import build_case_runtime_payload, build_runtime_session_payload
from pm_method_agent.runtime_session_service import (
    default_runtime_session_store,
    get_or_create_runtime_session,
)
from pm_method_agent.runtime_tools import RuntimeToolRegistry


@dataclass
class RuntimeResumeActionResult:
    action: str
    status: str
    workspace_id: str
    runtime_session: RuntimeSession
    suggestion_id: str = ""
    message: str = ""
    output_payload: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "status": self.status,
            "workspace_id": self.workspace_id,
            "suggestion_id": self.suggestion_id,
            "message": self.message,
            "output_payload": dict(self.output_payload),
            "runtime_session": build_runtime_session_payload(self.runtime_session),
        }


class RuntimeResumeActionExecutor:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime_session_store = default_runtime_session_store(self._base_dir)
        self._agent_shell = PMMethodAgentShell(base_dir=self._base_dir)
        self._runtime_tools = RuntimeToolRegistry(base_dir=self._base_dir)

    def execute(
        self,
        *,
        workspace_id: str,
        action: str = "",
        suggestion_id: str = "",
        message: str = "",
        approval_id: str = "",
        approval_decision: str = "",
        reason: str = "",
    ) -> RuntimeResumeActionResult:
        runtime_session = get_or_create_runtime_session(
            workspace_id,
            store=self._runtime_session_store,
        )
        runtime_payload = build_runtime_session_payload(runtime_session)
        suggestion = _find_resume_suggestion(runtime_payload, suggestion_id=suggestion_id, action=action)
        resolved_action = action or str(suggestion.get("action", "") or "")
        if not resolved_action:
            return RuntimeResumeActionResult(
                action="resume-action-required",
                status="needs-input",
                workspace_id=workspace_id,
                runtime_session=runtime_session,
                suggestion_id=suggestion_id,
                message="还需要指定一个继续动作。",
                output_payload={"resume_suggestions": runtime_payload.get("resume_suggestions", [])},
            )

        if resolved_action == "resolve-approval":
            return self._resolve_approval(
                workspace_id=workspace_id,
                runtime_session=runtime_session,
                suggestion=suggestion,
                suggestion_id=suggestion_id,
                approval_id=approval_id,
                approval_decision=approval_decision,
                reason=reason,
            )

        if resolved_action in {"reply-current-case", "resume-current-case", "create-case"}:
            return self._send_message(
                workspace_id=workspace_id,
                action=resolved_action,
                suggestion_id=suggestion_id,
                message=message,
                suggestion=suggestion,
                runtime_session=runtime_session,
            )

        if resolved_action == "inspect-runtime":
            return RuntimeResumeActionResult(
                action="inspect-runtime",
                status="completed",
                workspace_id=workspace_id,
                runtime_session=runtime_session,
                suggestion_id=suggestion_id,
                message="已读取当前运行时状态。",
                output_payload={"runtime_session": runtime_payload},
            )

        if resolved_action == "wait-current-query":
            return RuntimeResumeActionResult(
                action="wait-current-query",
                status="no-op",
                workspace_id=workspace_id,
                runtime_session=runtime_session,
                suggestion_id=suggestion_id,
                message="当前轮还在处理，暂时不需要追加动作。",
                output_payload={"runtime_session": runtime_payload},
            )

        return RuntimeResumeActionResult(
            action="unsupported-resume-action",
            status="failed",
            workspace_id=workspace_id,
            runtime_session=runtime_session,
            suggestion_id=suggestion_id,
            message=f"暂不支持这个继续动作：{resolved_action}。",
            output_payload={"requested_action": resolved_action},
        )

    def _resolve_approval(
        self,
        *,
        workspace_id: str,
        runtime_session: RuntimeSession,
        suggestion: dict,
        suggestion_id: str,
        approval_id: str,
        approval_decision: str,
        reason: str,
    ) -> RuntimeResumeActionResult:
        metadata = suggestion.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        resolved_approval_id = approval_id or str(metadata.get("item_id", "") or "")
        if not resolved_approval_id:
            return RuntimeResumeActionResult(
                action="approval-id-required",
                status="needs-input",
                workspace_id=workspace_id,
                runtime_session=runtime_session,
                suggestion_id=suggestion_id,
                message="还需要指定要处理的审批编号。",
            )
        if approval_decision not in {"approve", "reject", "expire"}:
            return RuntimeResumeActionResult(
                action="approval-decision-required",
                status="needs-input",
                workspace_id=workspace_id,
                runtime_session=runtime_session,
                suggestion_id=suggestion_id,
                message="需要先选择批准、拒绝或标记过期。",
                output_payload={"approval_id": resolved_approval_id},
            )

        if approval_decision == "approve":
            approval_result = self._runtime_tools.approve_pending_approval(
                workspace_id=workspace_id,
                approval_id=resolved_approval_id,
            )
        elif approval_decision == "reject":
            approval_result = self._runtime_tools.reject_pending_approval(
                workspace_id=workspace_id,
                approval_id=resolved_approval_id,
                reason=reason,
            )
        else:
            approval_result = self._runtime_tools.expire_pending_approval(
                workspace_id=workspace_id,
                approval_id=resolved_approval_id,
                reason=reason,
            )
        result_payload = approval_result.to_dict()
        result_runtime_session = approval_result.runtime_session or get_or_create_runtime_session(
            workspace_id,
            store=self._runtime_session_store,
        )
        return RuntimeResumeActionResult(
            action="resolve-approval",
            status="completed" if str(result_payload.get("terminal_state", "")) != "blocked" else "blocked",
            workspace_id=workspace_id,
            runtime_session=result_runtime_session,
            suggestion_id=suggestion_id,
            message="已处理待确认事项。",
            output_payload={"approval_result": result_payload},
        )

    def _send_message(
        self,
        *,
        workspace_id: str,
        action: str,
        suggestion_id: str,
        message: str,
        suggestion: dict,
        runtime_session: RuntimeSession,
    ) -> RuntimeResumeActionResult:
        normalized_message = str(message or "").strip()
        if not normalized_message:
            return RuntimeResumeActionResult(
                action="message-required",
                status="needs-input",
                workspace_id=workspace_id,
                runtime_session=runtime_session,
                suggestion_id=suggestion_id,
                message=str(suggestion.get("command_hint", "") or "还需要补一句要继续处理的内容。"),
                output_payload={"requested_action": action},
            )
        response = self._agent_shell.handle_message(
            message=normalized_message,
            workspace_id=workspace_id,
        )
        output_payload = {
            "agent_response": {
                "action": response.action,
                "message": response.message,
                "workspace": response.workspace.to_dict(),
                "case": response.case_state.to_dict() if response.case_state else None,
                "case_runtime": build_case_runtime_payload(response.case_state) if response.case_state else None,
                "project_profile": response.project_profile.to_dict() if response.project_profile else None,
                "rendered_card": response.rendered_card,
                "rendered_history": response.rendered_history,
            }
        }
        return RuntimeResumeActionResult(
            action=action,
            status="completed",
            workspace_id=workspace_id,
            runtime_session=response.runtime_session,
            suggestion_id=suggestion_id,
            message=response.message,
            output_payload=output_payload,
        )


def _find_resume_suggestion(runtime_payload: dict, *, suggestion_id: str, action: str) -> dict:
    suggestions = runtime_payload.get("resume_suggestions") or []
    if not isinstance(suggestions, list):
        return {}
    if suggestion_id:
        for item in suggestions:
            if isinstance(item, dict) and str(item.get("suggestion_id", "") or "") == suggestion_id:
                return item
    if action:
        for item in suggestions:
            if isinstance(item, dict) and str(item.get("action", "") or "") == action:
                return item
    if suggestions and isinstance(suggestions[0], dict):
        return suggestions[0]
    return {}
