from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Optional
from urllib.parse import urlparse

from pm_method_agent.renderers import (
    build_case_history_payload,
    render_case_history,
    render_case_state,
)
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case


JsonDict = Dict[str, object]


@dataclass
class HTTPResponse:
    status_code: int
    payload: JsonDict


class PMMethodHTTPService:
    def __init__(self, store_dir: Optional[str] = None) -> None:
        self._store = default_store(store_dir)

    def handle(self, method: str, path: str, body: Optional[bytes] = None) -> HTTPResponse:
        try:
            parsed_url = urlparse(path)
            normalized_path = parsed_url.path.rstrip("/") or "/"

            if method == "GET" and normalized_path == "/health":
                return HTTPResponse(200, {"status": "ok"})

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

            case_id = _extract_case_id(normalized_path)
            if not case_id:
                return HTTPResponse(404, {"error": "Not found."})

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


def _ensure_dict(payload: object) -> Optional[JsonDict]:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("Expected an object payload.")
    return payload


def _optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
