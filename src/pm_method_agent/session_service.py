from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from pm_method_agent.models import CaseState
from pm_method_agent.orchestrator import run_analysis_with_context


SESSION_STORE_DIRNAME = ".pm_method_agent/cases"
SESSION_MODE_KEY = "session_mode"
SESSION_INPUT_KEY = "session_original_input"
SESSION_NOTES_KEY = "session_notes"
SESSION_TURNS_KEY = "conversation_turns"
SESSION_STAGE_HISTORY_KEY = "stage_history"


@dataclass
class LocalCaseStore:
    root_dir: Path

    def save(self, case_state: CaseState) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._case_path(case_state.case_id).write_text(
            json.dumps(case_state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, case_id: str) -> CaseState:
        case_path = self._case_path(case_id)
        if not case_path.exists():
            raise FileNotFoundError(f"Case '{case_id}' does not exist.")
        payload = json.loads(case_path.read_text(encoding="utf-8"))
        return CaseState.from_dict(payload)

    def _case_path(self, case_id: str) -> Path:
        return self.root_dir / f"{case_id}.json"


def default_store(base_dir: Optional[str] = None) -> LocalCaseStore:
    root_dir = Path(base_dir or ".").resolve() / SESSION_STORE_DIRNAME
    return LocalCaseStore(root_dir=root_dir)


def create_case(
    raw_input: str,
    context_profile: Optional[Dict[str, object]] = None,
    mode: str = "auto",
    case_id: Optional[str] = None,
    store: Optional[LocalCaseStore] = None,
) -> CaseState:
    active_store = store or default_store()
    resolved_case_id = case_id or _generate_case_id()
    case_state = run_analysis_with_context(
        raw_input=raw_input,
        mode=mode,
        case_id=resolved_case_id,
        context_profile=context_profile or {},
        show_case_id=True,
    )
    case_state.metadata[SESSION_MODE_KEY] = mode
    case_state.metadata[SESSION_INPUT_KEY] = raw_input.strip()
    case_state.metadata[SESSION_NOTES_KEY] = []
    case_state.metadata[SESSION_TURNS_KEY] = [
        {
            "turn_id": "turn-001",
            "role": "user",
            "turn_kind": "input",
            "content": raw_input.strip(),
        }
    ]
    case_state.metadata[SESSION_STAGE_HISTORY_KEY] = []
    case_state.metadata["show_case_id"] = True
    active_store.save(case_state)
    return case_state


def reply_to_case(
    case_id: str,
    reply_text: str,
    context_profile_updates: Optional[Dict[str, object]] = None,
    store: Optional[LocalCaseStore] = None,
) -> CaseState:
    active_store = store or default_store()
    previous_case = active_store.load(case_id)
    original_input = str(previous_case.metadata.get(SESSION_INPUT_KEY, previous_case.raw_input))
    previous_notes = list(previous_case.metadata.get(SESSION_NOTES_KEY, []))
    updated_notes = previous_notes + [reply_text.strip()]

    merged_context = dict(previous_case.context_profile)
    merged_context.update(_extract_context_from_reply(reply_text))
    if context_profile_updates:
        merged_context.update(context_profile_updates)

    rerun_input = _compose_session_input(original_input, updated_notes)
    next_case = run_analysis_with_context(
        raw_input=rerun_input,
        mode=str(previous_case.metadata.get(SESSION_MODE_KEY, "auto")),
        case_id=case_id,
        context_profile=merged_context,
        show_case_id=True,
    )

    turns = list(previous_case.metadata.get(SESSION_TURNS_KEY, []))
    turns.append(
        {
            "turn_id": f"turn-{len(turns) + 1:03d}",
            "role": "user",
            "turn_kind": "reply",
            "content": reply_text.strip(),
        }
    )

    stage_history = list(previous_case.metadata.get(SESSION_STAGE_HISTORY_KEY, []))
    if (
        previous_case.stage != next_case.stage
        or previous_case.workflow_state != next_case.workflow_state
        or previous_case.output_kind != next_case.output_kind
    ):
        stage_history.append(
            {
                "from_stage": previous_case.stage,
                "to_stage": next_case.stage,
                "from_workflow_state": previous_case.workflow_state,
                "to_workflow_state": next_case.workflow_state,
                "trigger": "user-reply",
            }
        )

    next_case.metadata[SESSION_MODE_KEY] = str(previous_case.metadata.get(SESSION_MODE_KEY, "auto"))
    next_case.metadata[SESSION_INPUT_KEY] = original_input
    next_case.metadata[SESSION_NOTES_KEY] = updated_notes
    next_case.metadata[SESSION_TURNS_KEY] = turns
    next_case.metadata[SESSION_STAGE_HISTORY_KEY] = stage_history
    next_case.metadata["show_case_id"] = True
    active_store.save(next_case)
    return next_case


def get_case(case_id: str, store: Optional[LocalCaseStore] = None) -> CaseState:
    active_store = store or default_store()
    case_state = active_store.load(case_id)
    case_state.metadata["show_case_id"] = True
    return case_state


def _compose_session_input(original_input: str, notes: list[str]) -> str:
    if not notes:
        return original_input.strip()
    rendered_notes = "\n".join(f"- {note}" for note in notes if note.strip())
    return f"{original_input.strip()}\n\n补充信息：\n{rendered_notes}".strip()


def _extract_context_from_reply(reply_text: str) -> Dict[str, object]:
    text = reply_text.strip()
    extracted: Dict[str, object] = {}
    if any(keyword in text.lower() for keyword in ["tob", "企业产品"]):
        extracted["business_model"] = "tob"
    elif any(keyword in text.lower() for keyword in ["toc", "消费者产品"]):
        extracted["business_model"] = "toc"
    elif "内部产品" in text or "internal" in text.lower():
        extracted["business_model"] = "internal"

    if any(keyword in text for keyword in ["桌面端", "pc"]):
        extracted["primary_platform"] = "pc"
    elif any(keyword in text for keyword in ["移动网页", "mobile web", "h5"]):
        extracted["primary_platform"] = "mobile-web"
    elif any(keyword in text for keyword in ["原生应用", "app", "移动端"]):
        extracted["primary_platform"] = "native-app"
    elif any(keyword in text for keyword in ["小程序"]):
        extracted["primary_platform"] = "mini-program"
    elif any(keyword in text for keyword in ["多端"]):
        extracted["primary_platform"] = "multi-platform"

    inferred_roles = []
    for role in ["前台", "管理者", "管理员", "运营", "新用户", "患者", "审批专员", "部门负责人"]:
        if role in text and role not in inferred_roles:
            inferred_roles.append(role)
    if inferred_roles:
        extracted["target_user_roles"] = inferred_roles
    return extracted


def _generate_case_id() -> str:
    return f"case-{uuid4().hex[:8]}"
