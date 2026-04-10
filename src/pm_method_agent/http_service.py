from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Optional
from urllib.parse import urlparse

from pm_method_agent.agent_shell import PMMethodAgentShell
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
from pm_method_agent.runtime_config import ensure_local_env_loaded, get_llm_runtime_status
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case
from pm_method_agent.workspace_service import (
    activate_workspace_case,
    default_workspace_store,
    get_or_create_workspace,
    save_workspace,
)


JsonDict = Dict[str, object]


@dataclass
class HTTPResponse:
    status_code: int
    payload: JsonDict


class PMMethodHTTPService:
    def __init__(self, store_dir: Optional[str] = None) -> None:
        ensure_local_env_loaded(store_dir)
        self._store = default_store(store_dir)
        self._project_profile_store = default_project_profile_store(store_dir)
        self._workspace_store = default_workspace_store(store_dir)
        self._agent_shell = PMMethodAgentShell(base_dir=store_dir)

    def handle(self, method: str, path: str, body: Optional[bytes] = None) -> HTTPResponse:
        try:
            parsed_url = urlparse(path)
            normalized_path = parsed_url.path.rstrip("/") or "/"

            if method == "GET" and normalized_path == "/health":
                return HTTPResponse(200, {"status": "ok", "llm_runtime": get_llm_runtime_status()})

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
                return HTTPResponse(201, {"project_profile": project_profile.to_dict()})

            if method == "POST" and normalized_path == "/cases":
                payload = _parse_json_body(body)
                case_state = create_case(
                    raw_input=str(payload.get("input", "")).strip(),
                    context_profile=_ensure_dict(payload.get("context_profile")),
                    mode=str(payload.get("mode", "auto")),
                    case_id=_optional_string(payload.get("case_id")),
                    store=self._store,
                )
                return HTTPResponse(201, _build_case_response_payload(case_state))

            workspace_id = _extract_workspace_id(normalized_path)
            if workspace_id:
                if method == "GET" and normalized_path == f"/workspaces/{workspace_id}":
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    return HTTPResponse(200, {"workspace": workspace.to_dict()})

                if method == "GET" and normalized_path == f"/workspaces/{workspace_id}/cases":
                    workspace = get_or_create_workspace(workspace_id, store=self._workspace_store)
                    recent_cases = self._load_recent_cases(workspace)
                    return HTTPResponse(
                        200,
                        {
                            "workspace": workspace.to_dict(),
                            "cases": build_workspace_cases_payload(workspace, recent_cases),
                            "rendered_workspace": render_workspace_overview(workspace, recent_cases),
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
                    return HTTPResponse(
                        200,
                        {
                            "workspace": workspace.to_dict(),
                            "case": case_state.to_dict(),
                            "rendered_card": render_case_state(case_state),
                        },
                    )

                if method == "POST" and normalized_path == f"/workspaces/{workspace_id}/messages":
                    payload = _parse_json_body(body)
                    response = self._agent_shell.handle_message(
                        message=str(payload.get("message", "")).strip(),
                        workspace_id=workspace_id,
                    )
                    return HTTPResponse(200, _build_agent_response_payload(response))

            case_id = _extract_case_id(normalized_path)
            if case_id:
                if method == "GET" and normalized_path == f"/cases/{case_id}":
                    case_state = self._load_case(case_id)
                    return HTTPResponse(200, _build_case_response_payload(case_state))

                if method == "GET" and normalized_path == f"/cases/{case_id}/history":
                    case_state = self._load_case(case_id)
                    return HTTPResponse(
                        200,
                        {
                            "case_id": case_id,
                            "history": build_case_history_payload(case_state),
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
                    return HTTPResponse(200, _build_case_response_payload(case_state))

            project_profile_id = _extract_project_profile_id(normalized_path)
            if project_profile_id:
                if method == "GET" and normalized_path == f"/project-profiles/{project_profile_id}":
                    project_profile = self._load_project_profile(project_profile_id)
                    return HTTPResponse(200, {"project_profile": project_profile.to_dict()})

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
                    return HTTPResponse(200, {"project_profile": project_profile.to_dict()})

            if method == "POST" and normalized_path == "/agent/messages":
                payload = _parse_json_body(body)
                response = self._agent_shell.handle_message(
                    message=str(payload.get("message", "")).strip(),
                    workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                )
                return HTTPResponse(200, _build_agent_response_payload(response))

            return HTTPResponse(404, {"error": "Not found."})
        except HTTPServiceError as exc:
            return HTTPResponse(exc.status_code, {"error": exc.message})
        except ValueError as exc:
            return HTTPResponse(400, {"error": str(exc)})

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
                response = HTTPResponse(exc.status_code, {"error": exc.message})
            except ValueError as exc:
                response = HTTPResponse(400, {"error": str(exc)})

            encoded = json.dumps(response.payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(response.status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return RequestHandler


def _build_case_response_payload(case_state) -> JsonDict:
    return {
        "case": case_state.to_dict(),
        "rendered_card": render_case_state(case_state),
    }


def _build_agent_response_payload(response) -> JsonDict:
    return {
        "action": response.action,
        "message": response.message,
        "workspace": response.workspace.to_dict(),
        "runtime_session": response.runtime_session.to_dict(),
        "case": response.case_state.to_dict() if response.case_state else None,
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
