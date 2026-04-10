from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from pm_method_agent.models import RuntimeSession


RUNTIME_SESSION_STORE_DIRNAME = ".pm_method_agent/runtime_sessions"
RUNTIME_EVENT_LOG_LIMIT = 50
RUNTIME_LEDGER_LIMIT = 100
DEFAULT_CONTEXT_BUDGET = {
    "raw_history_budget": 40,
    "working_memory_budget": 12,
    "summary_memory_budget": 8,
}


@dataclass
class LocalRuntimeSessionStore:
    root_dir: Path

    def save(self, runtime_session: RuntimeSession) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._session_path(runtime_session.workspace_id).write_text(
            json.dumps(runtime_session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, workspace_id: str) -> RuntimeSession:
        session_path = self._session_path(workspace_id)
        if not session_path.exists():
            raise FileNotFoundError(f"Runtime session for workspace '{workspace_id}' does not exist.")
        payload = json.loads(session_path.read_text(encoding="utf-8"))
        return RuntimeSession.from_dict(payload)

    def exists(self, workspace_id: str) -> bool:
        return self._session_path(workspace_id).exists()

    def _session_path(self, workspace_id: str) -> Path:
        return self.root_dir / f"{workspace_id}.json"


def default_runtime_session_store(base_dir: Optional[str] = None) -> LocalRuntimeSessionStore:
    root_dir = Path(base_dir or ".").resolve() / RUNTIME_SESSION_STORE_DIRNAME
    return LocalRuntimeSessionStore(root_dir=root_dir)


def get_or_create_runtime_session(
    workspace_id: str,
    store: Optional[LocalRuntimeSessionStore] = None,
) -> RuntimeSession:
    active_store = store or default_runtime_session_store()
    if active_store.exists(workspace_id):
        return active_store.load(workspace_id)
    runtime_session = RuntimeSession(
        session_id=f"runtime-{uuid4().hex[:8]}",
        workspace_id=workspace_id,
        context_budget=dict(DEFAULT_CONTEXT_BUDGET),
        compression_state={
            "compressed_turns": 0,
            "last_compression_turn": 0,
            "status": "not-needed",
        },
    )
    active_store.save(runtime_session)
    return runtime_session


def save_runtime_session(
    runtime_session: RuntimeSession,
    store: Optional[LocalRuntimeSessionStore] = None,
) -> RuntimeSession:
    active_store = store or default_runtime_session_store()
    active_store.save(runtime_session)
    return runtime_session


def start_runtime_query(
    runtime_session: RuntimeSession,
    *,
    active_case_id: str = "",
    message: str,
) -> RuntimeSession:
    close_incomplete_hooks(runtime_session, reason="next-query-started")
    close_incomplete_tool_calls(runtime_session, reason="next-query-started")
    runtime_session.turn_count += 1
    runtime_session.current_query_id = f"query-{runtime_session.turn_count:04d}"
    runtime_session.runtime_status = "running"
    runtime_session.current_loop_state = "classifying-turn"
    if active_case_id:
        runtime_session.active_case_id = active_case_id
    append_runtime_event(
        runtime_session,
        "turn-received",
        {
            "query_id": runtime_session.current_query_id,
            "turn_count": runtime_session.turn_count,
            "active_case_id": runtime_session.active_case_id,
            "message": message,
        },
    )
    append_runtime_event(
        runtime_session,
        "loop-started",
        {
            "query_id": runtime_session.current_query_id,
            "loop_state": runtime_session.current_loop_state,
        },
    )
    return runtime_session


def record_runtime_turn_classification(
    runtime_session: RuntimeSession,
    *,
    intent: str,
    active_case_id: str = "",
) -> RuntimeSession:
    runtime_session.current_loop_state = "executing"
    if active_case_id:
        runtime_session.active_case_id = active_case_id
    append_runtime_event(
        runtime_session,
        "turn-classified",
        {
            "query_id": runtime_session.current_query_id,
            "intent": intent,
            "active_case_id": runtime_session.active_case_id,
        },
    )
    return runtime_session


def complete_runtime_query(
    runtime_session: RuntimeSession,
    *,
    terminal_state: str,
    action: str,
    active_case_id: str = "",
    resume_from: str = "",
    output_kind: str = "",
    workflow_state: str = "",
) -> RuntimeSession:
    return _terminate_runtime_query(
        runtime_session,
        terminal_state=terminal_state,
        action=action,
        active_case_id=active_case_id,
        resume_from=resume_from,
        output_kind=output_kind,
        workflow_state=workflow_state,
        runtime_status_after="idle",
    )


def fail_runtime_query(
    runtime_session: RuntimeSession,
    *,
    action: str,
    active_case_id: str = "",
    resume_from: str = "",
    error: Optional[Dict[str, object]] = None,
) -> RuntimeSession:
    return _terminate_runtime_query(
        runtime_session,
        terminal_state="failed",
        action=action,
        active_case_id=active_case_id,
        resume_from=resume_from,
        error=error,
        runtime_status_after="failed",
    )


def interrupt_runtime_query(
    runtime_session: RuntimeSession,
    *,
    action: str,
    active_case_id: str = "",
    resume_from: str = "",
    reason: Optional[Dict[str, object]] = None,
) -> RuntimeSession:
    return _terminate_runtime_query(
        runtime_session,
        terminal_state="interrupted",
        action=action,
        active_case_id=active_case_id,
        resume_from=resume_from,
        error=reason,
        runtime_status_after="interrupted",
    )


def cancel_runtime_query(
    runtime_session: RuntimeSession,
    *,
    action: str,
    active_case_id: str = "",
    resume_from: str = "",
    reason: Optional[Dict[str, object]] = None,
) -> RuntimeSession:
    return _terminate_runtime_query(
        runtime_session,
        terminal_state="cancelled",
        action=action,
        active_case_id=active_case_id,
        resume_from=resume_from,
        error=reason,
        runtime_status_after="cancelled",
    )


def append_runtime_event(
    runtime_session: RuntimeSession,
    event_type: str,
    payload: Optional[Dict[str, object]] = None,
) -> RuntimeSession:
    runtime_session.event_log.append(
        {
            "event_id": f"evt-{len(runtime_session.event_log) + 1:04d}",
            "event_type": event_type,
            "payload": payload or {},
        }
    )
    runtime_session.event_log = runtime_session.event_log[-RUNTIME_EVENT_LOG_LIMIT:]
    return runtime_session


def request_tool_call(
    runtime_session: RuntimeSession,
    *,
    tool_name: str,
    request_payload: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    call_id = f"call-{len(runtime_session.execution_ledger) + 1:04d}"
    entry = {
        "call_id": call_id,
        "query_id": runtime_session.current_query_id,
        "tool_name": tool_name,
        "request_payload": request_payload or {},
        "status": "requested",
        "result_ref": "",
        "error": {},
    }
    runtime_session.execution_ledger.append(dict(entry))
    runtime_session.execution_ledger = runtime_session.execution_ledger[-RUNTIME_LEDGER_LIMIT:]
    runtime_session.pending_tool_calls.append(
        {
            "call_id": call_id,
            "query_id": runtime_session.current_query_id,
            "tool_name": tool_name,
            "status": "requested",
        }
    )
    append_runtime_event(
        runtime_session,
        "tool-call-requested",
        {
            "call_id": call_id,
            "query_id": runtime_session.current_query_id,
            "tool_name": tool_name,
        },
    )
    return entry


def request_hook_call(
    runtime_session: RuntimeSession,
    *,
    hook_name: str,
    hook_stage: str,
    request_payload: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    hook_call_id = f"hook-{len(runtime_session.event_log) + len(runtime_session.pending_hooks) + 1:04d}"
    entry = {
        "hook_call_id": hook_call_id,
        "query_id": runtime_session.current_query_id,
        "hook_name": hook_name,
        "hook_stage": hook_stage,
        "request_payload": request_payload or {},
        "status": "requested",
        "result_payload": {},
        "error": {},
    }
    runtime_session.pending_hooks.append(dict(entry))
    append_runtime_event(
        runtime_session,
        "hook-call-requested",
        {
            "hook_call_id": hook_call_id,
            "query_id": runtime_session.current_query_id,
            "hook_name": hook_name,
            "hook_stage": hook_stage,
        },
    )
    return entry


def complete_hook_call(
    runtime_session: RuntimeSession,
    *,
    hook_call_id: str,
    result_payload: Optional[Dict[str, object]] = None,
) -> RuntimeSession:
    _update_pending_hook_entry(
        runtime_session,
        hook_call_id=hook_call_id,
        status="completed",
        result_payload=result_payload or {},
        error={},
    )
    runtime_session.pending_hooks = [
        item for item in runtime_session.pending_hooks if str(item.get("hook_call_id")) != hook_call_id
    ]
    append_runtime_event(
        runtime_session,
        "hook-call-completed",
        {
            "hook_call_id": hook_call_id,
            "result_payload": result_payload or {},
        },
    )
    return runtime_session


def fail_hook_call(
    runtime_session: RuntimeSession,
    *,
    hook_call_id: str,
    error: Optional[Dict[str, object]] = None,
) -> RuntimeSession:
    rendered_error = error or {}
    _update_pending_hook_entry(
        runtime_session,
        hook_call_id=hook_call_id,
        status="failed",
        result_payload={},
        error=rendered_error,
    )
    runtime_session.pending_hooks = [
        item for item in runtime_session.pending_hooks if str(item.get("hook_call_id")) != hook_call_id
    ]
    append_runtime_event(
        runtime_session,
        "hook-call-failed",
        {
            "hook_call_id": hook_call_id,
            "error": rendered_error,
        },
    )
    return runtime_session


def close_incomplete_hooks(
    runtime_session: RuntimeSession,
    *,
    reason: str,
) -> RuntimeSession:
    pending_items = list(runtime_session.pending_hooks)
    for item in pending_items:
        hook_call_id = str(item.get("hook_call_id", "")).strip()
        if not hook_call_id:
            continue
        fail_hook_call(
            runtime_session,
            hook_call_id=hook_call_id,
            error={
                "reason": reason,
                "message": "hook call was left pending and was closed by runtime recovery",
            },
        )
    return runtime_session


def complete_tool_call(
    runtime_session: RuntimeSession,
    *,
    call_id: str,
    result_ref: str = "",
) -> RuntimeSession:
    _update_ledger_entry(
        runtime_session,
        call_id=call_id,
        status="completed",
        result_ref=result_ref,
        error={},
    )
    runtime_session.pending_tool_calls = [
        item for item in runtime_session.pending_tool_calls if str(item.get("call_id")) != call_id
    ]
    append_runtime_event(
        runtime_session,
        "tool-call-completed",
        {
            "call_id": call_id,
            "result_ref": result_ref,
        },
    )
    return runtime_session


def fail_tool_call(
    runtime_session: RuntimeSession,
    *,
    call_id: str,
    error: Optional[Dict[str, object]] = None,
) -> RuntimeSession:
    rendered_error = error or {}
    _update_ledger_entry(
        runtime_session,
        call_id=call_id,
        status="failed",
        result_ref="",
        error=rendered_error,
    )
    runtime_session.pending_tool_calls = [
        item for item in runtime_session.pending_tool_calls if str(item.get("call_id")) != call_id
    ]
    append_runtime_event(
        runtime_session,
        "tool-call-failed",
        {
            "call_id": call_id,
            "error": rendered_error,
        },
    )
    return runtime_session


def close_incomplete_tool_calls(
    runtime_session: RuntimeSession,
    *,
    reason: str,
) -> RuntimeSession:
    pending_items = list(runtime_session.pending_tool_calls)
    for item in pending_items:
        call_id = str(item.get("call_id", "")).strip()
        if not call_id:
            continue
        fail_tool_call(
            runtime_session,
            call_id=call_id,
            error={
                "reason": reason,
                "message": "tool call was left pending and was closed by runtime recovery",
            },
        )
    return runtime_session


def _update_ledger_entry(
    runtime_session: RuntimeSession,
    *,
    call_id: str,
    status: str,
    result_ref: str,
    error: Dict[str, object],
) -> None:
    for item in runtime_session.execution_ledger:
        if str(item.get("call_id")) != call_id:
            continue
        item["status"] = status
        item["result_ref"] = result_ref
        item["error"] = error
        return


def _update_pending_hook_entry(
    runtime_session: RuntimeSession,
    *,
    hook_call_id: str,
    status: str,
    result_payload: Dict[str, object],
    error: Dict[str, object],
) -> None:
    for item in runtime_session.pending_hooks:
        if str(item.get("hook_call_id")) != hook_call_id:
            continue
        item["status"] = status
        item["result_payload"] = result_payload
        item["error"] = error
        return


def _terminate_runtime_query(
    runtime_session: RuntimeSession,
    *,
    terminal_state: str,
    action: str,
    active_case_id: str = "",
    resume_from: str = "",
    output_kind: str = "",
    workflow_state: str = "",
    error: Optional[Dict[str, object]] = None,
    runtime_status_after: str = "idle",
) -> RuntimeSession:
    runtime_session.runtime_status = runtime_status_after
    runtime_session.current_loop_state = "idle"
    runtime_session.resume_from = resume_from
    if active_case_id:
        runtime_session.active_case_id = active_case_id
    runtime_session.last_terminal_event = {
        "query_id": runtime_session.current_query_id,
        "terminal_state": terminal_state,
        "action": action,
        "active_case_id": runtime_session.active_case_id,
        "resume_from": resume_from,
        "output_kind": output_kind,
        "workflow_state": workflow_state,
        "error": error or {},
    }
    append_runtime_event(
        runtime_session,
        "terminal-state-emitted",
        dict(runtime_session.last_terminal_event),
    )
    runtime_session.current_query_id = ""
    return runtime_session
