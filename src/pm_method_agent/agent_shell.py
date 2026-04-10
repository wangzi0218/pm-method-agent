from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Optional, TypeVar

from pm_method_agent.hook_enforcement import HookExecutionBlockedError, run_pre_operation_hooks
from pm_method_agent.models import CaseState, ProjectProfile, RuntimeSession, WorkspaceState
from pm_method_agent.project_profile_service import (
    create_project_profile,
    default_project_profile_store,
    get_project_profile,
    update_project_profile,
)
from pm_method_agent.renderers import render_case_history, render_case_state
from pm_method_agent.renderers import render_workspace_overview
from pm_method_agent.reply_interpreter import ReplyAnalysis, build_reply_interpreter_from_env
from pm_method_agent.runtime_config import ensure_local_env_loaded
from pm_method_agent.runtime_policy import (
    RuntimePolicyViolation,
    check_runtime_policy,
    load_runtime_policy,
)
from pm_method_agent.runtime_session_service import (
    complete_runtime_query,
    complete_tool_call,
    fail_runtime_query,
    default_runtime_session_store,
    fail_tool_call,
    get_or_create_runtime_session,
    record_runtime_turn_classification,
    request_tool_call,
    save_runtime_session,
    start_runtime_query,
)
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case
from pm_method_agent.workspace_service import (
    activate_workspace_case,
    default_workspace_store,
    get_or_create_workspace,
    save_workspace,
)

T = TypeVar("T")


@dataclass
class AgentShellResponse:
    action: str
    message: str
    workspace: WorkspaceState
    runtime_session: RuntimeSession
    case_state: Optional[CaseState] = None
    project_profile: Optional[ProjectProfile] = None
    rendered_card: str = ""
    rendered_history: str = ""


class RuntimePolicyBlockedError(Exception):
    def __init__(self, violation: RuntimePolicyViolation) -> None:
        super().__init__(violation.reason)
        self.violation = violation


class PMMethodAgentShell:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        ensure_local_env_loaded(base_dir)
        self._case_store = default_store(base_dir)
        self._project_profile_store = default_project_profile_store(base_dir)
        self._workspace_store = default_workspace_store(base_dir)
        self._runtime_session_store = default_runtime_session_store(base_dir)
        self._runtime_policy = load_runtime_policy(base_dir=base_dir)
        self._reply_interpreter = build_reply_interpreter_from_env()

    def handle_message(
        self,
        message: str,
        workspace_id: str = "default",
    ) -> AgentShellResponse:
        normalized_message = message.strip()
        workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
        runtime_session = get_or_create_runtime_session(workspace_id, store=self._runtime_session_store)
        active_project_profile = self._load_active_project_profile(workspace)
        active_case = self._load_active_case(workspace)
        start_runtime_query(
            runtime_session,
            active_case_id=workspace.active_case_id,
            message=normalized_message,
        )
        try:
            reply_analysis = self._run_ledger_step(
                runtime_session,
                tool_name="reply-interpreter",
                action_name="reply-interpreter.analyze-reply",
                request_payload={"message": normalized_message},
                operation=lambda: self._reply_interpreter.analyze_reply(
                    normalized_message,
                    previous_case=active_case,
                ),
                result_ref_builder=lambda result: f"parser:{result.parser_name}",
            )
            intent = _classify_agent_intent(
                message=normalized_message,
                reply_analysis=reply_analysis,
                active_case=active_case,
                workspace=workspace,
            )
            record_runtime_turn_classification(
                runtime_session,
                intent=intent,
                active_case_id=workspace.active_case_id,
            )
            violation = check_runtime_policy(self._runtime_policy, intent=intent)
            if violation is not None:
                response = AgentShellResponse(
                    action="policy-blocked",
                    message=violation.reason,
                    workspace=workspace,
                    runtime_session=runtime_session,
                    rendered_card=_render_runtime_policy_block(intent=intent, reason=violation.reason),
                )
                return self._finalize_response(response, forced_terminal_state=violation.terminal_state)

            if intent == "workspace-overview":
                recent_cases = self._run_ledger_step(
                    runtime_session,
                    tool_name="workspace-service",
                    action_name="workspace-service.load-recent-cases",
                    request_payload={"action": "load-recent-cases", "workspace_id": workspace.workspace_id},
                    operation=lambda: self._load_recent_cases(workspace),
                    result_ref_builder=lambda result: f"recent-cases:{len(result)}",
                )
                response = AgentShellResponse(
                    action="show-workspace",
                    message="这是当前工作区里最近的案例。",
                    workspace=workspace,
                    runtime_session=runtime_session,
                    rendered_card=self._run_ledger_step(
                        runtime_session,
                        tool_name="renderer",
                        action_name="renderer.workspace-overview",
                        request_payload={"card": "workspace-overview"},
                        operation=lambda: render_workspace_overview(workspace, recent_cases),
                        result_ref_builder=lambda _: "rendered:workspace-overview",
                    ),
                )
                return self._finalize_response(response)

            if intent == "switch-case":
                target_case = self._run_ledger_step(
                    runtime_session,
                    tool_name="workspace-service",
                    action_name="workspace-service.resolve-switch-case",
                    request_payload={"action": "resolve-switch-case", "workspace_id": workspace.workspace_id},
                    operation=lambda: self._resolve_switch_target(normalized_message, workspace),
                    result_ref_builder=lambda result: f"case:{result.case_id}" if result is not None else "case:not-found",
                )
                if target_case is None:
                    recent_cases = self._run_ledger_step(
                        runtime_session,
                        tool_name="workspace-service",
                        action_name="workspace-service.load-recent-cases",
                        request_payload={"action": "load-recent-cases", "workspace_id": workspace.workspace_id},
                        operation=lambda: self._load_recent_cases(workspace),
                        result_ref_builder=lambda result: f"recent-cases:{len(result)}",
                    )
                    response = AgentShellResponse(
                        action="show-workspace",
                        message="没找到你想切换的案例，先看一下当前工作区里的最近案例。",
                        workspace=workspace,
                        runtime_session=runtime_session,
                        rendered_card=self._run_ledger_step(
                            runtime_session,
                            tool_name="renderer",
                            action_name="renderer.workspace-overview",
                            request_payload={"card": "workspace-overview"},
                            operation=lambda: render_workspace_overview(workspace, recent_cases),
                            result_ref_builder=lambda _: "rendered:workspace-overview",
                        ),
                    )
                    return self._finalize_response(response)
                activate_workspace_case(workspace, target_case.case_id)
                save_workspace(workspace, store=self._workspace_store)
                response = AgentShellResponse(
                    action="switch-case",
                    message=f"已切换到案例 {target_case.case_id}。",
                    workspace=workspace,
                    runtime_session=runtime_session,
                    case_state=target_case,
                    rendered_card=self._run_ledger_step(
                        runtime_session,
                        tool_name="renderer",
                        action_name="renderer.case-state",
                        request_payload={"card": "case-state", "case_id": target_case.case_id},
                        operation=lambda: render_case_state(target_case),
                        result_ref_builder=lambda _: f"rendered:case:{target_case.case_id}",
                    ),
                )
                return self._finalize_response(response)

            if intent == "project-background":
                project_profile = self._run_ledger_step(
                    runtime_session,
                    tool_name="project-profile-service",
                    action_name="project-profile-service.update-or-create",
                    request_payload={"action": "update-or-create", "workspace_id": workspace.workspace_id},
                    operation=lambda: self._update_or_create_project_profile(
                        workspace=workspace,
                        message=normalized_message,
                        active_project_profile=active_project_profile,
                    ),
                    result_ref_builder=lambda result: f"project-profile:{result.project_profile_id}",
                )
                workspace.active_project_profile_id = project_profile.project_profile_id
                case_state = self._run_ledger_step(
                    runtime_session,
                    tool_name="session-service",
                    action_name="session-service.continue-active-case-with-project-profile",
                    request_payload={"action": "continue-active-case-with-project-profile"},
                    operation=lambda: self._continue_active_case_with_project_profile(
                        workspace=workspace,
                        message=normalized_message,
                        project_profile=project_profile,
                    ),
                    result_ref_builder=lambda result: (
                        f"case:{result.case_id}" if result is not None else "case:no-backfill"
                    ),
                )
                save_workspace(workspace, store=self._workspace_store)
                response = AgentShellResponse(
                    action="project-profile-updated",
                    message=(
                        "已记录这条项目背景，并回填到当前案例。"
                        if case_state is not None
                        else "已记录这条项目背景，后续分析会默认带上这层上下文。"
                    ),
                    workspace=workspace,
                    runtime_session=runtime_session,
                    case_state=case_state,
                    project_profile=project_profile,
                    rendered_card=(
                        self._run_ledger_step(
                            runtime_session,
                            tool_name="renderer",
                            action_name="renderer.background-follow-up",
                            request_payload={"card": "background-follow-up", "case_id": case_state.case_id},
                            operation=lambda: _render_project_background_follow_up(case_state),
                            result_ref_builder=lambda _: f"rendered:background-follow-up:{case_state.case_id}",
                        )
                        if case_state is not None
                        else ""
                    ),
                )
                return self._finalize_response(response)

            if intent == "history" and workspace.active_case_id:
                case_state = self._run_ledger_step(
                    runtime_session,
                    tool_name="session-service",
                    action_name="session-service.load-case",
                    request_payload={"action": "load-case", "case_id": workspace.active_case_id},
                    operation=lambda: get_case(workspace.active_case_id, store=self._case_store),
                    result_ref_builder=lambda result: f"case:{result.case_id}",
                )
                response = AgentShellResponse(
                    action="show-history",
                    message="这是当前活跃案例的历史记录。",
                    workspace=workspace,
                    runtime_session=runtime_session,
                    case_state=case_state,
                    rendered_history=self._run_ledger_step(
                        runtime_session,
                        tool_name="renderer",
                        action_name="renderer.case-history",
                        request_payload={"card": "case-history", "case_id": case_state.case_id},
                        operation=lambda: render_case_history(case_state),
                        result_ref_builder=lambda _: f"rendered:history:{case_state.case_id}",
                    ),
                )
                return self._finalize_response(response)

            if intent == "guidance" and workspace.active_case_id:
                case_state = self._run_ledger_step(
                    runtime_session,
                    tool_name="session-service",
                    action_name="session-service.load-case",
                    request_payload={"action": "load-case", "case_id": workspace.active_case_id},
                    operation=lambda: get_case(workspace.active_case_id, store=self._case_store),
                    result_ref_builder=lambda result: f"case:{result.case_id}",
                )
                response = AgentShellResponse(
                    action="show-guidance",
                    message="这是当前活跃案例的最新建议。",
                    workspace=workspace,
                    runtime_session=runtime_session,
                    case_state=case_state,
                    rendered_card=self._run_ledger_step(
                        runtime_session,
                        tool_name="renderer",
                        action_name="renderer.case-state",
                        request_payload={"card": "case-state", "case_id": case_state.case_id},
                        operation=lambda: render_case_state(case_state),
                        result_ref_builder=lambda _: f"rendered:case:{case_state.case_id}",
                    ),
                )
                return self._finalize_response(response)

            if intent == "continue-case" and workspace.active_case_id:
                case_state = self._run_ledger_step(
                    runtime_session,
                    tool_name="session-service",
                    action_name="session-service.reply-to-case",
                    request_payload={"action": "reply-to-case", "case_id": workspace.active_case_id},
                    operation=lambda: reply_to_case(
                        case_id=workspace.active_case_id,
                        reply_text=normalized_message,
                        store=self._case_store,
                    ),
                    result_ref_builder=lambda result: f"case:{result.case_id}",
                )
                activate_workspace_case(workspace, case_state.case_id)
                save_workspace(workspace, store=self._workspace_store)
                response = AgentShellResponse(
                    action="reply-case",
                    message="已承接当前活跃案例并继续推进。",
                    workspace=workspace,
                    runtime_session=runtime_session,
                    case_state=case_state,
                    rendered_card=self._run_ledger_step(
                        runtime_session,
                        tool_name="renderer",
                        action_name="renderer.case-state",
                        request_payload={"card": "case-state", "case_id": case_state.case_id},
                        operation=lambda: render_case_state(case_state),
                        result_ref_builder=lambda _: f"rendered:case:{case_state.case_id}",
                    ),
                )
                return self._finalize_response(response)

            case_state = self._run_ledger_step(
                runtime_session,
                tool_name="session-service",
                action_name="session-service.create-case",
                request_payload={"action": "create-case", "workspace_id": workspace.workspace_id},
                operation=lambda: create_case(
                    raw_input=normalized_message,
                    project_profile=active_project_profile,
                    store=self._case_store,
                ),
                result_ref_builder=lambda result: f"case:{result.case_id}",
            )
            activate_workspace_case(workspace, case_state.case_id)
            save_workspace(workspace, store=self._workspace_store)
            response = AgentShellResponse(
                action="create-case",
                message="已按新的输入创建分析案例。",
                workspace=workspace,
                runtime_session=runtime_session,
                case_state=case_state,
                rendered_card=self._run_ledger_step(
                    runtime_session,
                    tool_name="renderer",
                    action_name="renderer.case-state",
                    request_payload={"card": "case-state", "case_id": case_state.case_id},
                    operation=lambda: render_case_state(case_state),
                    result_ref_builder=lambda _: f"rendered:case:{case_state.case_id}",
                ),
            )
            return self._finalize_response(response)
        except (RuntimePolicyBlockedError, HookExecutionBlockedError) as exc:
            response = AgentShellResponse(
                action="policy-blocked",
                message=exc.violation.reason,
                workspace=workspace,
                runtime_session=runtime_session,
                rendered_card=_render_runtime_policy_block(
                    intent=exc.violation.intent,
                    action_name=exc.violation.action_name,
                    reason=exc.violation.reason,
                ),
            )
            return self._finalize_response(response, forced_terminal_state=exc.violation.terminal_state)
        except Exception as exc:
            fail_runtime_query(
                runtime_session,
                action="runtime-error",
                active_case_id=workspace.active_case_id,
                resume_from=runtime_session.resume_from,
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            runtime_session.runtime_metadata["last_error"] = dict(
                runtime_session.last_terminal_event.get("error", {})
            )
            save_runtime_session(runtime_session, store=self._runtime_session_store)
            raise

    def _load_active_project_profile(self, workspace: WorkspaceState) -> Optional[ProjectProfile]:
        if not workspace.active_project_profile_id:
            return None
        try:
            return get_project_profile(
                workspace.active_project_profile_id,
                store=self._project_profile_store,
            )
        except FileNotFoundError:
            return None

    def _load_recent_cases(self, workspace: WorkspaceState) -> list[CaseState]:
        cases: list[CaseState] = []
        for case_id in workspace.recent_case_ids:
            try:
                cases.append(get_case(case_id, store=self._case_store))
            except FileNotFoundError:
                continue
        return cases

    def _load_active_case(self, workspace: WorkspaceState) -> Optional[CaseState]:
        if not workspace.active_case_id:
            return None
        try:
            return get_case(workspace.active_case_id, store=self._case_store)
        except FileNotFoundError:
            return None

    def _update_or_create_project_profile(
        self,
        workspace: WorkspaceState,
        message: str,
        active_project_profile: Optional[ProjectProfile],
    ) -> ProjectProfile:
        reply_analysis = self._reply_interpreter.analyze_reply(message)
        notes = [message]
        stable_constraints = _extract_constraint_notes(message)
        success_metrics = _extract_metric_notes(message)
        if active_project_profile:
            return update_project_profile(
                project_profile_id=active_project_profile.project_profile_id,
                context_profile_updates=reply_analysis.context_updates,
                stable_constraints=stable_constraints,
                success_metrics=success_metrics,
                notes=notes,
                store=self._project_profile_store,
            )
        project_name = workspace.metadata.get("project_name") or "当前项目"
        return create_project_profile(
            project_name=str(project_name),
            context_profile=reply_analysis.context_updates,
            stable_constraints=stable_constraints,
            success_metrics=success_metrics,
            notes=notes,
            store=self._project_profile_store,
        )

    def _continue_active_case_with_project_profile(
        self,
        workspace: WorkspaceState,
        message: str,
        project_profile: ProjectProfile,
    ) -> Optional[CaseState]:
        if not workspace.active_case_id:
            return None
        case_state = get_case(workspace.active_case_id, store=self._case_store)
        if case_state.output_kind not in {"context-question-card", "continue-guidance-card"}:
            return None
        next_case = reply_to_case(
            case_id=workspace.active_case_id,
            reply_text=message,
            context_profile_updates=project_profile.context_profile,
            store=self._case_store,
        )
        activate_workspace_case(workspace, next_case.case_id)
        return next_case

    def _resolve_switch_target(self, message: str, workspace: WorkspaceState) -> Optional[CaseState]:
        explicit_case_id = _extract_case_id_from_message(message)
        if explicit_case_id:
            try:
                return get_case(explicit_case_id, store=self._case_store)
            except FileNotFoundError:
                return None

        if any(keyword in message for keyword in ["上一个案例", "上个案例", "前一个案例"]):
            if len(workspace.recent_case_ids) >= 2:
                try:
                    return get_case(workspace.recent_case_ids[1], store=self._case_store)
                except FileNotFoundError:
                    return None

        ordinal = _extract_case_ordinal(message)
        if ordinal is not None and 0 <= ordinal < len(workspace.recent_case_ids):
            try:
                return get_case(workspace.recent_case_ids[ordinal], store=self._case_store)
            except FileNotFoundError:
                return None
        return None

    def _run_ledger_step(
        self,
        runtime_session: RuntimeSession,
        *,
        tool_name: str,
        action_name: str,
        request_payload: Optional[dict[str, object]],
        operation: Callable[[], T],
        result_ref_builder: Callable[[T], str],
    ) -> T:
        run_pre_operation_hooks(
            runtime_session,
            self._runtime_policy,
            action_name=action_name,
        )
        entry = request_tool_call(
            runtime_session,
            tool_name=tool_name,
            request_payload=request_payload,
        )
        try:
            result = operation()
        except Exception as exc:
            fail_tool_call(
                runtime_session,
                call_id=str(entry["call_id"]),
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            raise
        complete_tool_call(
            runtime_session,
            call_id=str(entry["call_id"]),
            result_ref=result_ref_builder(result),
        )
        return result

    def _finalize_response(
        self,
        response: AgentShellResponse,
        forced_terminal_state: str = "",
    ) -> AgentShellResponse:
        terminal_state = forced_terminal_state or _resolve_terminal_state(response.action, response.case_state)
        resume_from = _resolve_runtime_resume_from(response.action, response.case_state)
        active_case_id = response.case_state.case_id if response.case_state is not None else response.workspace.active_case_id
        output_kind = response.case_state.output_kind if response.case_state is not None else ""
        workflow_state = response.case_state.workflow_state if response.case_state is not None else ""
        complete_runtime_query(
            response.runtime_session,
            terminal_state=terminal_state,
            action=response.action,
            active_case_id=active_case_id,
            resume_from=resume_from,
            output_kind=output_kind,
            workflow_state=workflow_state,
        )
        save_runtime_session(response.runtime_session, store=self._runtime_session_store)
        return response


def _classify_agent_intent(
    message: str,
    reply_analysis: ReplyAnalysis,
    active_case: Optional[CaseState],
    workspace: WorkspaceState,
) -> str:
    lowered = message.lower()
    if _looks_like_workspace_overview_request(message):
        return "workspace-overview"
    if _looks_like_switch_case_request(message, workspace):
        return "switch-case"
    if any(keyword in message for keyword in ["看看之前", "做过哪些决定", "之前补过", "历史", "history"]):
        return "history"
    if any(
        keyword in message
        for keyword in [
            "下一步",
            "最该补",
            "卡在哪",
            "该做什么",
            "怎么推进",
            "继续还是先停",
            "会有什么不同",
            "有什么区别",
            "怎么看",
            "怎么理解",
        ]
    ):
        return "guidance"
    if _looks_like_project_background(message, reply_analysis, active_case):
        return "project-background"
    if any(
        keyword in message
        for keyword in [
            "另一个",
            "新点子",
            "新想法",
            "新需求",
            "新场景",
            "还有个想法",
            "还有个需求",
            "还有一个问题",
            "换一个",
            "再看一个",
        ]
    ):
        return "new-case"
    if active_case is not None:
        if any(keyword in message for keyword in ["继续", "补充", "再补一句", "基于上面的信息", "刚才那个"]):
            return "continue-case"
        if _looks_like_new_case_without_explicit_keyword(message, reply_analysis, active_case):
            return "new-case"
        if _looks_like_meta_question(message, reply_analysis):
            return "guidance"
        return "continue-case"
    return "new-case"


def _extract_constraint_notes(message: str) -> list[str]:
    if any(keyword in message for keyword in ["合规", "预算", "周期", "资源", "设备", "权限", "上线"]):
        return [message]
    return []


def _extract_metric_notes(message: str) -> list[str]:
    if any(keyword in message for keyword in ["指标", "率", "留存", "转化", "GMV", "DAU", "到诊率", "履约率"]):
        return [message]
    return []


def _render_project_background_follow_up(case_state: CaseState) -> str:
    preview_case = CaseState.from_dict(case_state.to_dict())
    preview_case.output_kind = "continue-guidance-card"
    preview_case.metadata["continue_card_kind"] = "background-follow-up"
    preview_case.normalized_summary = "基础背景已经补上了，接下来可以开始把问题本身说得更具体一些。"
    return render_case_state(preview_case)


def _looks_like_project_background(
    message: str,
    reply_analysis: ReplyAnalysis,
    active_case: Optional[CaseState],
) -> bool:
    del active_case
    project_markers = [
        "这个项目",
        "这个产品",
        "我们主要",
        "我们团队",
        "默认",
        "一直跑在",
        "长期",
        "通用的",
    ]
    if not any(marker in message for marker in project_markers):
        return False
    if reply_analysis.inferred_gate_choice:
        return False
    if any(category in reply_analysis.categories for category in ["evidence", "decision"]):
        return False
    return bool(reply_analysis.context_updates) or bool(_extract_constraint_notes(message)) or bool(
        _extract_metric_notes(message)
    )


def _looks_like_new_case_without_explicit_keyword(
    message: str,
    reply_analysis: ReplyAnalysis,
    active_case: CaseState,
) -> bool:
    if reply_analysis.inferred_gate_choice:
        return False
    if any(keyword in message for keyword in ["顺便", "另外", "还有一件事", "还有个问题", "还有一个问题"]):
        return True
    if any(keyword in message for keyword in ["如果是", "假设换成", "换到", "换成"]):
        return False
    if any(category in reply_analysis.categories for category in ["context", "evidence", "decision"]):
        active_input = active_case.raw_input.strip()
        if not active_input:
            return False
        current_overlap = sum(1 for token in _message_keywords(active_input) if token in message)
        new_overlap = sum(1 for token in _message_keywords(message) if token in active_input)
        if current_overlap == 0 and new_overlap == 0 and len(message) >= 18:
            return True
    return False


def _looks_like_meta_question(message: str, reply_analysis: ReplyAnalysis) -> bool:
    if reply_analysis.context_updates or reply_analysis.inferred_gate_choice:
        return False
    meta_markers = [
        "如果是",
        "会有什么不同",
        "有什么区别",
        "怎么看",
        "怎么理解",
        "你觉得",
        "是不是更像",
        "那如果",
    ]
    return any(marker in message for marker in meta_markers)


def _message_keywords(message: str) -> list[str]:
    keywords: list[str] = []
    for token in [
        "前台",
        "店员",
        "店长",
        "老板",
        "护士",
        "医生",
        "审批",
        "发帖",
        "H5",
        "h5",
        "提醒",
        "预约",
        "漏人",
        "核销",
        "患者",
        "新用户",
        "运营",
        "内容社区",
        "诊所",
    ]:
        if token in message and token not in keywords:
            keywords.append(token)
    return keywords


def _looks_like_workspace_overview_request(message: str) -> bool:
    return any(
        keyword in message
        for keyword in [
            "最近案例",
            "案例列表",
            "最近几个 case",
            "最近几个案例",
            "当前工作区",
            "现在有哪些案例",
            "看看最近的案例",
        ]
    )


def _looks_like_switch_case_request(message: str, workspace: WorkspaceState) -> bool:
    if not workspace.recent_case_ids:
        return False
    if _extract_case_id_from_message(message):
        return any(keyword in message for keyword in ["切到", "切回", "打开", "回到", "看一下"])
    if any(keyword in message for keyword in ["上一个案例", "上个案例", "前一个案例"]):
        return True
    if _extract_case_ordinal(message) is not None and any(
        keyword in message for keyword in ["切到", "切回", "打开", "回到"]
    ):
        return True
    return False


def _extract_case_id_from_message(message: str) -> str:
    matched = re.search(r"(case-[0-9a-f]{8})", message)
    return matched.group(1) if matched else ""


def _extract_case_ordinal(message: str) -> Optional[int]:
    matched = re.search(r"第\s*([1-9]\d*)\s*个案例", message)
    if not matched:
        return None
    return int(matched.group(1)) - 1


def _resolve_terminal_state(action: str, case_state: Optional[CaseState]) -> str:
    if case_state is None:
        if action == "project-profile-updated":
            return "continued"
        return "completed"
    if case_state.workflow_state == "done":
        return "completed"
    if case_state.workflow_state == "blocked":
        return "blocked"
    if case_state.workflow_state == "deferred":
        return "deferred"
    if action in {"reply-case", "project-profile-updated"}:
        return "continued"
    return "completed"


def _resolve_runtime_resume_from(action: str, case_state: Optional[CaseState]) -> str:
    if case_state is None:
        if action == "project-profile-updated":
            return "active-case"
        return ""
    next_stage = str(case_state.metadata.get("next_stage", "") or "").strip()
    last_resume_stage = str(case_state.metadata.get("last_resume_stage", "") or "").strip()
    if case_state.workflow_state == "blocked":
        return next_stage or last_resume_stage or case_state.stage
    if case_state.workflow_state == "deferred":
        return next_stage or case_state.stage
    if action in {"show-guidance", "show-history", "switch-case"}:
        return case_state.stage
    return last_resume_stage or case_state.stage


def _render_runtime_policy_block(*, intent: str = "", action_name: str = "", reason: str) -> str:
    lines = [
        "# PM Method Agent 规则阻塞卡",
        "",
        "## 当前判断",
        "这一步先不继续执行。",
        "",
        "## 原因",
        reason,
    ]
    if intent:
        lines.extend(["", "## 当前意图", f"- `{intent}`"])
    if action_name:
        lines.extend(["", "## 当前动作", f"- `{action_name}`"])
    return "\n".join(lines)
