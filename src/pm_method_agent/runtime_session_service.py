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
RUNTIME_APPROVAL_LEDGER_LIMIT = 100
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
    event_index = _next_runtime_counter(runtime_session, "next_event_index")
    runtime_session.event_log.append(
        {
            "event_id": f"evt-{event_index:04d}",
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
    call_id = f"call-{_next_runtime_counter(runtime_session, 'next_call_index'):04d}"
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


def request_runtime_approval(
    runtime_session: RuntimeSession,
    *,
    tool_name: str,
    action_name: str,
    request_payload: Optional[Dict[str, object]] = None,
    command_args: Optional[list[str]] = None,
    read_paths: Optional[list[str]] = None,
    write_paths: Optional[list[str]] = None,
    cwd: str = "",
    timeout_seconds: float = 15.0,
    blocked_action: str = "",
    resume_from: str = "",
    violation: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    approval_id = f"approval-{_next_runtime_counter(runtime_session, 'next_approval_index'):04d}"
    entry = {
        "approval_id": approval_id,
        "query_id": runtime_session.current_query_id,
        "tool_name": tool_name,
        "action_name": action_name,
        "request_payload": request_payload or {},
        "command_args": list(command_args or []),
        "read_paths": list(read_paths or []),
        "write_paths": list(write_paths or []),
        "cwd": cwd,
        "timeout_seconds": timeout_seconds,
        "blocked_action": blocked_action,
        "resume_from": resume_from,
        "violation": dict(violation or {}),
        "status": "pending",
    }
    runtime_session.pending_approvals.append(dict(entry))
    runtime_session.approval_ledger.append(dict(entry))
    runtime_session.approval_ledger = runtime_session.approval_ledger[-RUNTIME_APPROVAL_LEDGER_LIMIT:]
    append_runtime_event(
        runtime_session,
        "approval-requested",
        {
            "approval_id": approval_id,
            "query_id": runtime_session.current_query_id,
            "tool_name": tool_name,
            "action_name": action_name,
            "violation": dict(violation or {}),
        },
    )
    return entry


def get_pending_runtime_approval(
    runtime_session: RuntimeSession,
    *,
    approval_id: str,
) -> Dict[str, object]:
    for item in runtime_session.pending_approvals:
        if str(item.get("approval_id")) == approval_id:
            return item
    raise KeyError(f"Pending approval '{approval_id}' does not exist.")


def get_runtime_approval(
    runtime_session: RuntimeSession,
    *,
    approval_id: str,
) -> Dict[str, object]:
    for item in runtime_session.approval_ledger:
        if str(item.get("approval_id")) == approval_id:
            return item
    raise KeyError(f"Approval '{approval_id}' does not exist.")


def approve_runtime_approval(
    runtime_session: RuntimeSession,
    *,
    approval_id: str,
    actor: str = "user",
) -> Dict[str, object]:
    return _resolve_runtime_approval(
        runtime_session,
        approval_id=approval_id,
        status="approved",
        actor=actor,
    )


def reject_runtime_approval(
    runtime_session: RuntimeSession,
    *,
    approval_id: str,
    actor: str = "user",
    reason: str = "",
) -> Dict[str, object]:
    return _resolve_runtime_approval(
        runtime_session,
        approval_id=approval_id,
        status="rejected",
        actor=actor,
        reason=reason,
    )


def expire_runtime_approval(
    runtime_session: RuntimeSession,
    *,
    approval_id: str,
    actor: str = "runtime",
    reason: str = "",
) -> Dict[str, object]:
    return _resolve_runtime_approval(
        runtime_session,
        approval_id=approval_id,
        status="expired",
        actor=actor,
        reason=reason,
    )


def request_hook_call(
    runtime_session: RuntimeSession,
    *,
    hook_name: str,
    hook_stage: str,
    request_payload: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    hook_call_id = f"hook-{_next_runtime_counter(runtime_session, 'next_hook_index'):04d}"
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


def _next_runtime_counter(runtime_session: RuntimeSession, key: str) -> int:
    current_value = int(runtime_session.runtime_metadata.get(key, 0) or 0)
    next_value = current_value + 1
    runtime_session.runtime_metadata[key] = next_value
    return next_value


def _resolve_runtime_approval(
    runtime_session: RuntimeSession,
    *,
    approval_id: str,
    status: str,
    actor: str,
    reason: str = "",
) -> Dict[str, object]:
    entry = get_pending_runtime_approval(runtime_session, approval_id=approval_id)
    runtime_session.pending_approvals = [
        item for item in runtime_session.pending_approvals if str(item.get("approval_id")) != approval_id
    ]
    _update_approval_ledger_entry(
        runtime_session,
        approval_id=approval_id,
        status=status,
        actor=actor,
        reason=reason,
    )
    append_runtime_event(
        runtime_session,
        f"approval-{status}",
        {
            "approval_id": approval_id,
            "tool_name": entry.get("tool_name", ""),
            "action_name": entry.get("action_name", ""),
            "actor": actor,
            "reason": reason,
        },
    )
    resolved_entry = dict(entry)
    resolved_entry["status"] = status
    resolved_entry["actor"] = actor
    resolved_entry["reason"] = reason
    return resolved_entry


def _update_approval_ledger_entry(
    runtime_session: RuntimeSession,
    *,
    approval_id: str,
    status: str,
    actor: str,
    reason: str,
) -> None:
    for item in runtime_session.approval_ledger:
        if str(item.get("approval_id")) != approval_id:
            continue
        item["status"] = status
        item["actor"] = actor
        item["reason"] = reason
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
