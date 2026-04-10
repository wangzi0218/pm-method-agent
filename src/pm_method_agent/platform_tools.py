from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from pm_method_agent.project_profile_service import (
    create_project_profile,
    default_project_profile_store,
    get_project_profile,
    update_project_profile,
)
from pm_method_agent.renderers import (
    build_case_history_payload,
    build_workspace_cases_payload,
    render_case_history,
    render_case_state,
    render_workspace_overview,
)
from pm_method_agent.session_service import default_store, get_case
from pm_method_agent.tool_catalog import ToolDescriptor
from pm_method_agent.tool_runtime import (
    LocalToolExecutionOutcome,
    LocalToolExecutionResult,
    LocalToolHandler,
    LocalToolRequest,
    LocalToolRuntime,
)
from pm_method_agent.workspace_service import default_workspace_store, get_or_create_workspace


PLATFORM_WORKSPACE_OVERVIEW_TOOL_NAME = "platform-workspace-overview"
PLATFORM_CASE_READ_TOOL_NAME = "platform-case-read"
PLATFORM_PROJECT_PROFILE_READ_TOOL_NAME = "platform-project-profile-read"
PLATFORM_PROJECT_PROFILE_UPSERT_TOOL_NAME = "platform-project-profile-upsert"

WORKSPACE_OVERVIEW_ACTION = "workspace-service.load-recent-cases"
CASE_READ_ACTION = "case-service.read"
PROJECT_PROFILE_READ_ACTION = "project-profile-service.read"
PROJECT_PROFILE_UPSERT_ACTION = "project-profile-service.update-or-create"


PLATFORM_TOOL_DESCRIPTORS = [
    ToolDescriptor(
        tool_name=PLATFORM_WORKSPACE_OVERVIEW_TOOL_NAME,
        kind="workspace-read",
        summary="读取工作区状态和最近案例概览，适合网页或平台侧外壳直接消费。",
        execution_scope="platform",
        input_schema={
            "required": ["workspace_id"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。"},
            },
        },
    ),
    ToolDescriptor(
        tool_name=PLATFORM_CASE_READ_TOOL_NAME,
        kind="case-read",
        summary="读取指定案例的结构化数据和渲染卡片。",
        execution_scope="platform",
        input_schema={
            "required": ["case_id"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。默认 default。"},
                "case_id": {"type": "string", "description": "案例编号。"},
            },
        },
    ),
    ToolDescriptor(
        tool_name=PLATFORM_PROJECT_PROFILE_READ_TOOL_NAME,
        kind="project-profile-read",
        summary="读取指定项目背景，适合网页或平台侧展示稳定上下文。",
        execution_scope="platform",
        input_schema={
            "required": ["project_profile_id"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。默认 default。"},
                "project_profile_id": {"type": "string", "description": "项目背景编号。"},
            },
        },
    ),
    ToolDescriptor(
        tool_name=PLATFORM_PROJECT_PROFILE_UPSERT_TOOL_NAME,
        kind="project-profile-write",
        summary="创建或更新项目背景，适合平台侧显式维护稳定上下文。",
        execution_scope="platform",
        input_schema={
            "required": ["project_name"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。默认 default。"},
                "project_profile_id": {"type": "string", "description": "已有项目背景编号；不传时创建。"},
                "project_name": {"type": "string", "description": "项目名称。"},
                "context_profile": {"type": "object", "description": "创建时使用的场景基础信息。"},
                "context_profile_updates": {"type": "object", "description": "更新时追加或覆盖的场景信息。"},
                "stable_constraints": {"type": "array", "description": "长期稳定约束。"},
                "success_metrics": {"type": "array", "description": "关键成功指标。"},
                "notes": {"type": "array", "description": "补充备注。"},
            },
        },
    ),
]


@dataclass
class PlatformToolResult(LocalToolExecutionResult):
    pass


class PlatformWorkspaceOverviewHandler(LocalToolHandler):
    name = PLATFORM_WORKSPACE_OVERVIEW_TOOL_NAME

    def __init__(self, *, base_dir: str) -> None:
        self._case_store = default_store(base_dir)
        self._workspace_store = default_workspace_store(base_dir)

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        workspace_id = _required_string(request.request_payload.get("workspace_id"), field_name="workspace_id")
        workspace = get_or_create_workspace(workspace_id=workspace_id, store=self._workspace_store)
        recent_cases = []
        for case_id in workspace.recent_case_ids:
            try:
                recent_cases.append(get_case(case_id=case_id, store=self._case_store))
            except FileNotFoundError:
                continue
        return LocalToolExecutionOutcome(
            action="platform-workspace-loaded",
            terminal_state="completed",
            success=True,
            result_ref=f"workspace:{workspace_id}",
            output_payload={
                "workspace": workspace.to_dict(),
                "cases": build_workspace_cases_payload(workspace, recent_cases),
                "rendered_workspace": render_workspace_overview(workspace, recent_cases),
            },
        )


class PlatformCaseReadHandler(LocalToolHandler):
    name = PLATFORM_CASE_READ_TOOL_NAME

    def __init__(self, *, base_dir: str) -> None:
        self._case_store = default_store(base_dir)

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        case_id = _required_string(request.request_payload.get("case_id"), field_name="case_id")
        case_state = get_case(case_id=case_id, store=self._case_store)
        return LocalToolExecutionOutcome(
            action="platform-case-loaded",
            terminal_state="completed",
            success=True,
            result_ref=f"case:{case_id}",
            output_payload={
                "case": case_state.to_dict(),
                "history": build_case_history_payload(case_state),
                "rendered_card": render_case_state(case_state),
                "rendered_history": render_case_history(case_state),
            },
        )


class PlatformProjectProfileReadHandler(LocalToolHandler):
    name = PLATFORM_PROJECT_PROFILE_READ_TOOL_NAME

    def __init__(self, *, base_dir: str) -> None:
        self._project_profile_store = default_project_profile_store(base_dir)

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        project_profile_id = _required_string(
            request.request_payload.get("project_profile_id"),
            field_name="project_profile_id",
        )
        project_profile = get_project_profile(
            project_profile_id=project_profile_id,
            store=self._project_profile_store,
        )
        return LocalToolExecutionOutcome(
            action="platform-project-profile-loaded",
            terminal_state="completed",
            success=True,
            result_ref=f"project-profile:{project_profile_id}",
            output_payload={
                "project_profile": project_profile.to_dict(),
            },
        )


class PlatformProjectProfileUpsertHandler(LocalToolHandler):
    name = PLATFORM_PROJECT_PROFILE_UPSERT_TOOL_NAME

    def __init__(self, *, base_dir: str) -> None:
        self._project_profile_store = default_project_profile_store(base_dir)

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        project_profile_id = _optional_string(request.request_payload.get("project_profile_id"))
        project_name = _required_string(request.request_payload.get("project_name"), field_name="project_name")
        stable_constraints = _ensure_string_list(request.request_payload.get("stable_constraints"))
        success_metrics = _ensure_string_list(request.request_payload.get("success_metrics"))
        notes = _ensure_string_list(request.request_payload.get("notes"))

        if project_profile_id:
            project_profile = update_project_profile(
                project_profile_id=project_profile_id,
                project_name=project_name,
                context_profile_updates=_ensure_object(request.request_payload.get("context_profile_updates")),
                stable_constraints=stable_constraints,
                success_metrics=success_metrics,
                notes=notes,
                store=self._project_profile_store,
            )
            action = "platform-project-profile-updated"
        else:
            project_profile = create_project_profile(
                project_name=project_name,
                context_profile=_ensure_object(request.request_payload.get("context_profile")),
                stable_constraints=stable_constraints,
                success_metrics=success_metrics,
                notes=notes,
                store=self._project_profile_store,
            )
            action = "platform-project-profile-created"

        return LocalToolExecutionOutcome(
            action=action,
            terminal_state="completed",
            success=True,
            result_ref=f"project-profile:{project_profile.project_profile_id}",
            output_payload={
                "project_profile": project_profile.to_dict(),
            },
        )


class PlatformToolRegistry:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime = LocalToolRuntime(base_dir=self._base_dir)
        self._handlers: Dict[str, LocalToolHandler] = {
            PLATFORM_WORKSPACE_OVERVIEW_TOOL_NAME: PlatformWorkspaceOverviewHandler(base_dir=self._base_dir),
            PLATFORM_CASE_READ_TOOL_NAME: PlatformCaseReadHandler(base_dir=self._base_dir),
            PLATFORM_PROJECT_PROFILE_READ_TOOL_NAME: PlatformProjectProfileReadHandler(base_dir=self._base_dir),
            PLATFORM_PROJECT_PROFILE_UPSERT_TOOL_NAME: PlatformProjectProfileUpsertHandler(base_dir=self._base_dir),
        }

    def list_tools(self) -> List[dict]:
        return [item.to_dict() for item in PLATFORM_TOOL_DESCRIPTORS]

    def supports(self, tool_name: str) -> bool:
        return _find_descriptor(tool_name) is not None

    def describe_tool(self, tool_name: str) -> dict:
        descriptor = _find_descriptor(tool_name)
        if descriptor is None:
            raise ValueError(f"Unsupported platform tool: {tool_name or 'unknown'}")
        return descriptor.to_dict()

    def execute(self, *, tool_name: str, payload: Dict[str, object]) -> PlatformToolResult:
        handler = self._handlers.get(str(tool_name).strip())
        if handler is None:
            raise ValueError(f"Unsupported platform tool: {tool_name or 'unknown'}")

        request = _build_request(
            tool_name=tool_name,
            payload=payload,
        )
        result = self._runtime.execute_tool(request, handler=handler)
        return PlatformToolResult(
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


def _build_request(*, tool_name: str, payload: Dict[str, object]) -> LocalToolRequest:
    normalized_tool_name = str(tool_name).strip()
    workspace_id = _optional_string(payload.get("workspace_id")) or "default"
    action_name = _action_name_for_tool(normalized_tool_name)
    summary = _summary_for_tool(normalized_tool_name, payload)
    return LocalToolRequest(
        tool_name=normalized_tool_name,
        action_name=action_name,
        workspace_id=workspace_id,
        summary=summary,
        request_payload=dict(payload),
        blocked_action=f"{normalized_tool_name}-blocked",
        resume_from=action_name,
        approval_id=_optional_string(payload.get("_approval_id")),
    )


def _action_name_for_tool(tool_name: str) -> str:
    if tool_name == PLATFORM_WORKSPACE_OVERVIEW_TOOL_NAME:
        return WORKSPACE_OVERVIEW_ACTION
    if tool_name == PLATFORM_CASE_READ_TOOL_NAME:
        return CASE_READ_ACTION
    if tool_name == PLATFORM_PROJECT_PROFILE_READ_TOOL_NAME:
        return PROJECT_PROFILE_READ_ACTION
    if tool_name == PLATFORM_PROJECT_PROFILE_UPSERT_TOOL_NAME:
        return PROJECT_PROFILE_UPSERT_ACTION
    return f"{tool_name}.execute"


def _summary_for_tool(tool_name: str, payload: Dict[str, object]) -> str:
    if tool_name == PLATFORM_WORKSPACE_OVERVIEW_TOOL_NAME:
        return f"读取工作区：{_optional_string(payload.get('workspace_id')) or 'default'}"
    if tool_name == PLATFORM_CASE_READ_TOOL_NAME:
        return f"读取案例：{_optional_string(payload.get('case_id'))}"
    if tool_name == PLATFORM_PROJECT_PROFILE_READ_TOOL_NAME:
        return f"读取项目背景：{_optional_string(payload.get('project_profile_id'))}"
    if tool_name == PLATFORM_PROJECT_PROFILE_UPSERT_TOOL_NAME:
        profile_id = _optional_string(payload.get("project_profile_id"))
        if profile_id:
            return f"更新项目背景：{profile_id}"
        return f"创建项目背景：{_optional_string(payload.get('project_name'))}"
    return f"执行平台工具：{tool_name}"


def _required_string(value: object, *, field_name: str) -> str:
    rendered = _optional_string(value)
    if not rendered:
        raise ValueError(f"Missing {field_name}.")
    return rendered


def _optional_string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _ensure_object(value: object) -> Optional[Dict[str, object]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Expected object payload.")
    return dict(value)


def _ensure_string_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _find_descriptor(tool_name: str) -> Optional[ToolDescriptor]:
    normalized = str(tool_name).strip()
    for descriptor in PLATFORM_TOOL_DESCRIPTORS:
        if descriptor.tool_name == normalized:
            return descriptor
    return None
