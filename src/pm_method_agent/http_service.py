from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Optional
from urllib.parse import urlparse

from pm_method_agent.agent_shell import PMMethodAgentShell
from pm_method_agent.command_executor import LOCAL_COMMAND_TOOL_NAME
from pm_method_agent.demo_seed import build_demo_scenario_generator_from_env, seed_workspace_demo
from pm_method_agent.operation_enforcement import evaluate_operation_enforcement
from pm_method_agent.project_profile_service import (
    create_project_profile,
    default_project_profile_store,
    get_project_profile,
    update_project_profile,
)
from pm_method_agent.renderers import (
    build_case_runtime_payload,
    build_runtime_session_payload,
    build_case_history_payload,
    build_workspace_cases_payload,
    render_case_history,
    render_case_state,
    render_workspace_overview,
)
from pm_method_agent.runtime_config import ensure_local_env_loaded, get_llm_runtime_status
from pm_method_agent.runtime_policy import load_runtime_policy, runtime_policy_to_dict
from pm_method_agent.runtime_session_service import default_runtime_session_store, get_or_create_runtime_session
from pm_method_agent.runtime_tools import RuntimeToolRegistry
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case
from pm_method_agent.web_demo_assets import get_web_demo_asset, get_web_demo_html
from pm_method_agent.workspace_service import (
    activate_workspace_case,
    default_workspace_store,
    get_or_create_workspace,
    get_workspace_approval_preferences,
    get_workspace_user_profile,
    save_workspace,
    update_workspace_approval_preferences,
    update_workspace_user_profile,
)


JsonDict = Dict[str, object]


@dataclass
class HTTPResponse:
    status_code: int
    payload: Optional[JsonDict] = None
    body: Optional[bytes] = None
    content_type: str = "application/json; charset=utf-8"

    @classmethod
    def json(cls, status_code: int, payload: JsonDict) -> "HTTPResponse":
        return cls(status_code=status_code, payload=payload)

    @classmethod
    def content(cls, status_code: int, body: bytes, content_type: str) -> "HTTPResponse":
        return cls(status_code=status_code, body=body, content_type=content_type)

    def encoded_body(self) -> bytes:
        if self.body is not None:
            return self.body
        return json.dumps(self.payload or {}, ensure_ascii=False, indent=2).encode("utf-8")


class PMMethodHTTPService:
    def __init__(self, store_dir: Optional[str] = None) -> None:
        ensure_local_env_loaded(store_dir)
        self._store = default_store(store_dir)
        self._project_profile_store = default_project_profile_store(store_dir)
        self._workspace_store = default_workspace_store(store_dir)
        self._runtime_session_store = default_runtime_session_store(store_dir)
        self._runtime_policy = load_runtime_policy(base_dir=store_dir)
        self._agent_shell = PMMethodAgentShell(base_dir=store_dir)
        self._local_tools = RuntimeToolRegistry(base_dir=store_dir)
        self._demo_scenario_generator = build_demo_scenario_generator_from_env()

    def handle(self, method: str, path: str, body: Optional[bytes] = None) -> HTTPResponse:
        try:
            parsed_url = urlparse(path)
            normalized_path = parsed_url.path.rstrip("/") or "/"

            if method == "GET" and normalized_path in {"/", "/demo"}:
                return HTTPResponse.content(200, get_web_demo_html(), "text/html; charset=utf-8")

            if method == "GET":
                asset = get_web_demo_asset(normalized_path)
                if asset:
                    content_type, content_body = asset
                    return HTTPResponse.content(200, content_body, content_type)

            if method == "GET" and normalized_path == "/health":
                return HTTPResponse.json(200, {"status": "ok", "llm_runtime": get_llm_runtime_status()})

            if method == "GET" and normalized_path == "/runtime/policy":
                return HTTPResponse.json(200, {"runtime_policy": runtime_policy_to_dict(self._runtime_policy)})

            if method == "GET" and normalized_path == "/runtime/tools":
                return HTTPResponse.json(200, {"tools": self._local_tools.list_tools()})

            tool_name = _extract_runtime_tool_name(normalized_path)
            if method == "GET" and tool_name:
                return HTTPResponse.json(200, {"tool": self._local_tools.describe_tool(tool_name)})

            if method == "POST" and normalized_path == "/runtime/policy/evaluate":
                payload = _parse_json_body(body)
                decision = evaluate_operation_enforcement(
                    self._runtime_policy,
                    action_name=str(payload.get("action_name", "")).strip(),
                    command_args=_ensure_string_list(payload.get("command_args")),
                    read_paths=_ensure_string_list(payload.get("read_paths")),
                    write_paths=_ensure_string_list(payload.get("write_paths")),
                )
                return HTTPResponse.json(
                    200,
                    {
                        "decision": decision.to_dict(),
                        "runtime_policy": runtime_policy_to_dict(self._runtime_policy),
                    },
                )

            if method == "POST" and normalized_path == "/runtime/commands/execute":
                payload = _parse_json_body(body)
                result = self._local_tools.execute(
                    tool_name=LOCAL_COMMAND_TOOL_NAME,
                    payload=payload,
                )
                return HTTPResponse.json(200, {"result": result.to_dict()})

            if method == "POST" and normalized_path == "/runtime/tools/execute":
                payload = _parse_json_body(body)
                tool_name = str(payload.get("tool_name", "")).strip()
                result = self._local_tools.execute(tool_name=tool_name, payload=payload)
                return HTTPResponse.json(
                    200,
                    {
                        "tool_name": tool_name,
                        "result": result.to_dict(),
                    },
                )

            if method == "POST" and normalized_path == "/project-profiles":
                payload = _parse_json_body(body)
                project_profile = create_project_profile(
                    project_name=str(payload.get("project_name", "")).strip(),
                    context_profile=_ensure_dict(payload.get("context_profile")),
                    stable_constraints=_ensure_string_list(payload.get("stable_constraints")),
                    success_metrics=_ensure_string_list(payload.get("success_metrics")),
                    notes=_ensure_string_list(payload.get("notes")),
                    project_profile_id=_optional_string(payload.get("project_profile_id")),
                    store=self._project_profile_store,
                )
                return HTTPResponse.json(201, {"project_profile": project_profile.to_dict()})

            if method == "POST" and normalized_path == "/cases":
                payload = _parse_json_body(body)
                case_state = create_case(
                    raw_input=str(payload.get("input", "")).strip(),
                    context_profile=_ensure_dict(payload.get("context_profile")),
                    mode=str(payload.get("mode", "auto")),
                    case_id=_optional_string(payload.get("case_id")),
                    store=self._store,
                )
                return HTTPResponse.json(201, _build_case_response_payload(case_state))

            workspace_id = _extract_workspace_id(normalized_path)
            if workspace_id:
                if method == "GET" and normalized_path == f"/workspaces/{workspace_id}":
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    active_project_profile = self._load_active_project_profile(workspace)
                    active_case = self._load_active_case(workspace)
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace": workspace.to_dict(),
                            "approval_preferences": get_workspace_approval_preferences(workspace),
                            "user_profile": get_workspace_user_profile(workspace),
                            "cases": build_workspace_cases_payload(
                                workspace,
                                self._load_recent_cases(workspace),
                                active_project_profile,
                                active_case,
                            ),
                        },
                    )

                if method == "GET" and normalized_path == f"/workspaces/{workspace_id}/cases":
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    recent_cases = self._load_recent_cases(workspace)
                    active_project_profile = self._load_active_project_profile(workspace)
                    active_case = self._load_active_case(workspace)
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace": workspace.to_dict(),
                            "cases": build_workspace_cases_payload(
                                workspace,
                                recent_cases,
                                active_project_profile,
                                active_case,
                            ),
                            "user_profile": get_workspace_user_profile(workspace),
                            "rendered_workspace": render_workspace_overview(
                                workspace,
                                recent_cases,
                                active_project_profile,
                                active_case,
                            ),
                        },
                    )

                if method == "GET" and normalized_path == f"/workspaces/{workspace_id}/approval-preferences":
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace_id": workspace_id,
                            "approval_preferences": get_workspace_approval_preferences(workspace),
                        },
                    )

                if method == "POST" and normalized_path == f"/workspaces/{workspace_id}/approval-preferences":
                    payload = _parse_json_body(body)
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    update_workspace_approval_preferences(
                        workspace,
                        auto_approve_actions=_ensure_string_list(payload.get("auto_approve_actions")),
                    )
                    save_workspace(workspace, store=self._workspace_store)
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace": workspace.to_dict(),
                            "approval_preferences": get_workspace_approval_preferences(workspace),
                        },
                    )

                if method == "GET" and normalized_path == f"/workspaces/{workspace_id}/user-profile":
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace_id": workspace_id,
                            "user_profile": get_workspace_user_profile(workspace),
                        },
                    )

                if method == "POST" and normalized_path == f"/workspaces/{workspace_id}/user-profile":
                    payload = _parse_json_body(body)
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    update_workspace_user_profile(
                        workspace,
                        preferred_output_style=_optional_string(payload.get("preferred_output_style")),
                        preferred_language=_optional_string(payload.get("preferred_language")),
                        decision_style=_optional_string(payload.get("decision_style")),
                        frequent_product_domains=_ensure_string_list(payload.get("frequent_product_domains")),
                        common_constraints=_ensure_string_list(payload.get("common_constraints")),
                    )
                    save_workspace(workspace, store=self._workspace_store)
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace": workspace.to_dict(),
                            "user_profile": get_workspace_user_profile(workspace),
                        },
                    )

                if method == "GET" and normalized_path == f"/workspaces/{workspace_id}/runtime/approvals":
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace_id": workspace_id,
                            "pending_approvals": self._local_tools.list_pending_approvals(
                                workspace_id=workspace_id,
                            ),
                        },
                    )

                if method == "GET" and normalized_path == f"/workspaces/{workspace_id}/runtime/session":
                    runtime_session = get_or_create_runtime_session(
                        workspace_id,
                        store=self._runtime_session_store,
                    )
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace_id": workspace_id,
                            "runtime_session": build_runtime_session_payload(runtime_session),
                        },
                    )

                approval_id = _extract_workspace_runtime_approval_id(normalized_path, workspace_id)
                if method == "POST" and approval_id:
                    payload = _parse_json_body(body)
                    action = _extract_workspace_runtime_approval_action(normalized_path, workspace_id)
                    if action == "approve":
                        result = self._local_tools.approve_pending_approval(
                            workspace_id=workspace_id,
                            approval_id=approval_id,
                        )
                    elif action == "reject":
                        result = self._local_tools.reject_pending_approval(
                            workspace_id=workspace_id,
                            approval_id=approval_id,
                            reason=str(payload.get("reason", "")).strip(),
                        )
                    elif action == "expire":
                        result = self._local_tools.expire_pending_approval(
                            workspace_id=workspace_id,
                            approval_id=approval_id,
                            reason=str(payload.get("reason", "")).strip(),
                        )
                    else:
                        raise HTTPServiceError(404, "Not found.")
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace_id": workspace_id,
                            "approval_id": approval_id,
                            "result": result.to_dict(),
                        },
                    )

                if method == "POST" and normalized_path == f"/workspaces/{workspace_id}/active-case":
                    payload = _parse_json_body(body)
                    target_case_id = str(payload.get("case_id", "")).strip()
                    if not target_case_id:
                        raise HTTPServiceError(400, "Missing case_id.")
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    case_state = self._load_case(target_case_id)
                    activate_workspace_case(workspace, target_case_id)
                    save_workspace(workspace, store=self._workspace_store)
                    return HTTPResponse.json(
                        200,
                        {
                            "workspace": workspace.to_dict(),
                            "case": case_state.to_dict(),
                            "case_runtime": build_case_runtime_payload(case_state),
                            "rendered_card": render_case_state(case_state),
                        },
                    )

                if method == "POST" and normalized_path == f"/workspaces/{workspace_id}/messages":
                    payload = _parse_json_body(body)
                    response = self._agent_shell.handle_message(
                        message=str(payload.get("message", "")).strip(),
                        workspace_id=workspace_id,
                    )
                    return HTTPResponse.json(200, _build_agent_response_payload(response))

                if method == "POST" and normalized_path == f"/workspaces/{workspace_id}/demo-seed":
                    payload = _parse_json_body(body)
                    replay_result = seed_workspace_demo(
                        self._agent_shell,
                        workspace_id=workspace_id,
                        generator=self._demo_scenario_generator,
                        theme=str(payload.get("theme", "")).strip(),
                        scenario_count=_ensure_demo_scenario_count(payload.get("scenario_count")),
                    )
                    workspace = replay_result.latest_response.workspace
                    recent_cases = self._load_recent_cases(workspace)
                    active_case = replay_result.latest_response.case_state
                    runtime_session = get_or_create_runtime_session(
                        workspace_id,
                        store=self._runtime_session_store,
                    )
                    return HTTPResponse.json(
                        200,
                        {
                            "message": f"已装载 {len(replay_result.seeded_case_ids)} 个示例案例。",
                            "workspace": workspace.to_dict(),
                            "cases": build_workspace_cases_payload(workspace, recent_cases),
                            "seed_result": replay_result.to_dict(),
                            "runtime_session": build_runtime_session_payload(runtime_session),
                            "case": active_case.to_dict() if active_case else None,
                            "case_runtime": (
                                build_case_runtime_payload(active_case) if active_case else None
                            ),
                            "rendered_card": render_case_state(active_case) if active_case else "",
                        },
                    )

            case_id = _extract_case_id(normalized_path)
            if case_id:
                if method == "GET" and normalized_path == f"/cases/{case_id}":
                    case_state = self._load_case(case_id)
                    return HTTPResponse.json(200, _build_case_response_payload(case_state))

                if method == "GET" and normalized_path == f"/cases/{case_id}/history":
                    case_state = self._load_case(case_id)
                    return HTTPResponse.json(
                        200,
                        {
                            "case_id": case_id,
                            "history": build_case_history_payload(case_state),
                            "case_runtime": build_case_runtime_payload(case_state),
                            "rendered_history": render_case_history(case_state),
                        },
                    )

                if method == "POST" and normalized_path == f"/cases/{case_id}/reply":
                    payload = _parse_json_body(body)
                    case_state = reply_to_case(
                        case_id=case_id,
                        reply_text=str(payload.get("reply", "")).strip(),
                        context_profile_updates=_ensure_dict(payload.get("context_profile_updates")),
                        store=self._store,
                    )
                    return HTTPResponse.json(200, _build_case_response_payload(case_state))

            project_profile_id = _extract_project_profile_id(normalized_path)
            if project_profile_id:
                if method == "GET" and normalized_path == f"/project-profiles/{project_profile_id}":
                    project_profile = self._load_project_profile(project_profile_id)
                    return HTTPResponse.json(200, {"project_profile": project_profile.to_dict()})

                if method == "POST" and normalized_path == f"/project-profiles/{project_profile_id}":
                    payload = _parse_json_body(body)
                    project_profile = update_project_profile(
                        project_profile_id=project_profile_id,
                        project_name=_optional_string(payload.get("project_name")),
                        context_profile_updates=_ensure_dict(payload.get("context_profile_updates")),
                        stable_constraints=_ensure_string_list(payload.get("stable_constraints")),
                        success_metrics=_ensure_string_list(payload.get("success_metrics")),
                        notes=_ensure_string_list(payload.get("notes")),
                        store=self._project_profile_store,
                    )
                    return HTTPResponse.json(200, {"project_profile": project_profile.to_dict()})

            if method == "POST" and normalized_path == "/agent/messages":
                payload = _parse_json_body(body)
                response = self._agent_shell.handle_message(
                    message=str(payload.get("message", "")).strip(),
                    workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                )
                return HTTPResponse.json(200, _build_agent_response_payload(response))

            return HTTPResponse.json(404, {"error": "Not found."})
        except HTTPServiceError as exc:
            return HTTPResponse.json(exc.status_code, {"error": exc.message})
        except ValueError as exc:
            return HTTPResponse.json(400, {"error": str(exc)})

    def _load_case(self, case_id: str):
        try:
            return get_case(case_id=case_id, store=self._store)
        except FileNotFoundError as exc:
            raise HTTPServiceError(404, str(exc)) from exc

    def _load_project_profile(self, project_profile_id: str):
        try:
            return get_project_profile(
                project_profile_id=project_profile_id,
                store=self._project_profile_store,
            )
        except FileNotFoundError as exc:
            raise HTTPServiceError(404, str(exc)) from exc

    def _load_active_project_profile(self, workspace):
        if not workspace.active_project_profile_id:
            return None
        try:
            return get_project_profile(
                workspace.active_project_profile_id,
                store=self._project_profile_store,
            )
        except FileNotFoundError:
            return None

    def _load_active_case(self, workspace):
        if not workspace.active_case_id:
            return None
        try:
            return self._load_case(workspace.active_case_id)
        except HTTPServiceError:
            return None

    def _load_recent_cases(self, workspace) -> list:
        cases = []
        for case_id in workspace.recent_case_ids:
            try:
                cases.append(self._load_case(case_id))
            except HTTPServiceError:
                continue
        return cases


class HTTPServiceError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def run_http_server(host: str = "127.0.0.1", port: int = 8000, store_dir: Optional[str] = None) -> None:
    service = PMMethodHTTPService(store_dir=store_dir)
    server = ThreadingHTTPServer((host, port), _build_handler(service))
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _build_handler(service: PMMethodHTTPService) -> Callable[..., BaseHTTPRequestHandler]:
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._handle_request("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle_request("POST")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _handle_request(self, method: str) -> None:
            body = None
            if method == "POST":
                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length) if content_length else b""
            try:
                response = service.handle(method=method, path=self.path, body=body)
            except HTTPServiceError as exc:
                response = HTTPResponse.json(exc.status_code, {"error": exc.message})
            except ValueError as exc:
                response = HTTPResponse.json(400, {"error": str(exc)})

            encoded = response.encoded_body()
            self.send_response(response.status_code)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return RequestHandler


def _build_case_response_payload(case_state) -> JsonDict:
    return {
        "case": case_state.to_dict(),
        "case_runtime": build_case_runtime_payload(case_state),
        "rendered_card": render_case_state(case_state),
    }




def _build_agent_response_payload(response) -> JsonDict:
    return {
        "action": response.action,
        "message": response.message,
        "workspace": response.workspace.to_dict(),
        "runtime_session": response.runtime_session.to_dict(),
        "case": response.case_state.to_dict() if response.case_state else None,
        "case_runtime": build_case_runtime_payload(response.case_state) if response.case_state else None,
        "project_profile": response.project_profile.to_dict() if response.project_profile else None,
        "rendered_card": response.rendered_card,
        "rendered_history": response.rendered_history,
    }


def _parse_json_body(body: Optional[bytes]) -> JsonDict:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON body.") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")
    return payload


def _extract_case_id(path: str) -> Optional[str]:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2 or parts[0] != "cases":
        return None
    return parts[1]


def _extract_workspace_id(path: str) -> Optional[str]:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2 or parts[0] != "workspaces":
        return None
    return parts[1]


def _extract_project_profile_id(path: str) -> Optional[str]:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2 or parts[0] != "project-profiles":
        return None
    return parts[1]


def _extract_workspace_runtime_approval_id(path: str, workspace_id: str) -> Optional[str]:
    parts = [part for part in path.strip("/").split("/") if part]
    expected_prefix = ["workspaces", workspace_id, "runtime", "approvals"]
    if parts[:4] != expected_prefix:
        return None
    if len(parts) != 6 or parts[5] not in {"approve", "reject", "expire"}:
        return None
    return parts[4]


def _extract_workspace_runtime_approval_action(path: str, workspace_id: str) -> Optional[str]:
    parts = [part for part in path.strip("/").split("/") if part]
    expected_prefix = ["workspaces", workspace_id, "runtime", "approvals"]
    if parts[:4] != expected_prefix or len(parts) != 6:
        return None
    if parts[5] not in {"approve", "reject", "expire"}:
        return None
    return parts[5]


def _extract_runtime_tool_name(path: str) -> Optional[str]:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) != 3 or parts[0] != "runtime" or parts[1] != "tools":
        return None
    return parts[2]


def _ensure_dict(payload: object) -> Optional[JsonDict]:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("Expected an object payload.")
    return payload


def _ensure_string_list(payload: object) -> Optional[list[str]]:
    if payload is None:
        return None
    if not isinstance(payload, list):
        raise ValueError("Expected a list payload.")
    normalized = []
    for item in payload:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _ensure_demo_scenario_count(payload: object) -> int:
    if payload is None:
        return 3
    try:
        value = int(payload)
    except (TypeError, ValueError):
        return 3
    if value <= 0:
        return 3
    return min(value, 5)
