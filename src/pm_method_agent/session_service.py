from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from pm_method_agent.models import CaseState
from pm_method_agent.orchestrator import continue_analysis_with_context, run_analysis_with_context


SESSION_STORE_DIRNAME = ".pm_method_agent/cases"
SESSION_MODE_KEY = "session_mode"
SESSION_INPUT_KEY = "session_original_input"
SESSION_NOTES_KEY = "session_notes"
SESSION_NOTE_BUCKETS_KEY = "session_note_buckets"
SESSION_TURNS_KEY = "conversation_turns"
SESSION_STAGE_HISTORY_KEY = "stage_history"
SESSION_ANSWERED_QUESTIONS_KEY = "answered_questions"
SESSION_RESOLVED_GATES_KEY = "resolved_gates"
SESSION_LATEST_REPLY_KEY = "latest_user_reply"
SESSION_LAST_RESUME_STAGE_KEY = "last_resume_stage"

NOTE_BUCKET_KEYS = [
    "context_notes",
    "evidence_notes",
    "decision_notes",
    "constraint_notes",
    "other_notes",
]


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
    case_state.metadata[SESSION_NOTE_BUCKETS_KEY] = _empty_note_buckets()
    case_state.metadata[SESSION_TURNS_KEY] = [
        {
            "turn_id": "turn-001",
            "role": "user",
            "turn_kind": "input",
            "content": raw_input.strip(),
        }
    ]
    case_state.metadata[SESSION_STAGE_HISTORY_KEY] = []
    case_state.metadata[SESSION_ANSWERED_QUESTIONS_KEY] = []
    case_state.metadata[SESSION_RESOLVED_GATES_KEY] = []
    case_state.metadata[SESSION_LATEST_REPLY_KEY] = ""
    case_state.metadata[SESSION_LAST_RESUME_STAGE_KEY] = "context-alignment"
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
    reply_analysis = _analyze_reply(reply_text)

    merged_context = _merge_context_profile(
        previous_case.context_profile,
        reply_analysis["context_updates"],
    )
    if context_profile_updates:
        merged_context = _merge_context_profile(merged_context, context_profile_updates)

    note_buckets = _merge_note_buckets(
        previous_case.metadata.get(SESSION_NOTE_BUCKETS_KEY, {}),
        reply_analysis,
        reply_text.strip(),
    )
    rerun_input = _compose_session_input(original_input, note_buckets)
    resume_stage = _resolve_resume_stage(previous_case)
    next_case = continue_analysis_with_context(
        raw_input=rerun_input,
        start_stage=resume_stage,
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

    answered_questions = list(previous_case.metadata.get(SESSION_ANSWERED_QUESTIONS_KEY, []))
    for question in previous_case.pending_questions:
        if question not in answered_questions:
            answered_questions.append(question)

    resolved_gates = list(previous_case.metadata.get(SESSION_RESOLVED_GATES_KEY, []))
    for gate in previous_case.decision_gates:
        if gate.blocking:
            resolved_gates.append(
                {
                    "gate_id": gate.gate_id,
                    "stage": gate.stage,
                    "user_choice": reply_analysis.get("inferred_gate_choice"),
                    "reply_text": reply_text.strip(),
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
                "resume_stage": resume_stage,
            }
        )

    next_case.metadata[SESSION_MODE_KEY] = str(previous_case.metadata.get(SESSION_MODE_KEY, "auto"))
    next_case.metadata[SESSION_INPUT_KEY] = original_input
    next_case.metadata[SESSION_NOTES_KEY] = updated_notes
    next_case.metadata[SESSION_NOTE_BUCKETS_KEY] = note_buckets
    next_case.metadata[SESSION_TURNS_KEY] = turns
    next_case.metadata[SESSION_STAGE_HISTORY_KEY] = stage_history
    next_case.metadata[SESSION_ANSWERED_QUESTIONS_KEY] = answered_questions
    next_case.metadata[SESSION_RESOLVED_GATES_KEY] = resolved_gates
    next_case.metadata[SESSION_LATEST_REPLY_KEY] = reply_text.strip()
    next_case.metadata[SESSION_LAST_RESUME_STAGE_KEY] = resume_stage
    next_case.metadata["show_case_id"] = True
    active_store.save(next_case)
    return next_case


def get_case(case_id: str, store: Optional[LocalCaseStore] = None) -> CaseState:
    active_store = store or default_store()
    case_state = active_store.load(case_id)
    case_state.metadata["show_case_id"] = True
    return case_state


def _compose_session_input(original_input: str, note_buckets: Dict[str, list[str]]) -> str:
    if not any(note_buckets.get(bucket_key) for bucket_key in NOTE_BUCKET_KEYS):
        return original_input.strip()
    sections = []
    bucket_labels = {
        "context_notes": "补充场景信息",
        "evidence_notes": "补充现状证据",
        "decision_notes": "补充决策表达",
        "constraint_notes": "补充限制条件",
        "other_notes": "其他补充",
    }
    for bucket_key in NOTE_BUCKET_KEYS:
        notes = note_buckets.get(bucket_key, [])
        if not notes:
            continue
        rendered_notes = "\n".join(f"- {note}" for note in notes if note.strip())
        sections.append(f"{bucket_labels[bucket_key]}：\n{rendered_notes}")
    return f"{original_input.strip()}\n\n" + "\n\n".join(sections)


def _analyze_reply(reply_text: str) -> Dict[str, object]:
    text = reply_text.strip()
    extracted: Dict[str, object] = {}
    lowered = text.lower()
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
    categories = _classify_reply_categories(text, extracted)
    return {
        "context_updates": extracted,
        "categories": categories,
        "inferred_gate_choice": _infer_gate_choice(lowered),
    }


def _generate_case_id() -> str:
    return f"case-{uuid4().hex[:8]}"


def _resolve_resume_stage(previous_case: CaseState) -> str:
    if previous_case.output_kind == "context-question-card":
        return "context-alignment"
    if previous_case.output_kind == "stage-block-card":
        return "problem-definition"
    if previous_case.output_kind == "decision-gate-card":
        return "decision-challenge"
    if previous_case.workflow_state == "done":
        return "problem-definition"
    return previous_case.stage


def _empty_note_buckets() -> Dict[str, list[str]]:
    return {bucket_key: [] for bucket_key in NOTE_BUCKET_KEYS}


def _merge_note_buckets(
    previous_buckets: object,
    reply_analysis: Dict[str, object],
    reply_text: str,
) -> Dict[str, list[str]]:
    merged = _empty_note_buckets()
    if isinstance(previous_buckets, dict):
        for bucket_key in NOTE_BUCKET_KEYS:
            merged[bucket_key] = list(previous_buckets.get(bucket_key, []))

    bucket_mapping = {
        "context": "context_notes",
        "evidence": "evidence_notes",
        "decision": "decision_notes",
        "constraint": "constraint_notes",
        "other": "other_notes",
    }
    target_buckets = [bucket_mapping[category] for category in reply_analysis["categories"]]
    if not target_buckets:
        target_buckets = ["other_notes"]

    for bucket_key in target_buckets:
        if reply_text not in merged[bucket_key]:
            merged[bucket_key].append(reply_text)
    return merged


def _merge_context_profile(
    existing: Dict[str, object],
    updates: Optional[Dict[str, object]],
) -> Dict[str, object]:
    merged = dict(existing)
    if not updates:
        return merged
    for key, value in updates.items():
        if key == "target_user_roles":
            current_roles = list(merged.get(key, []))
            for role in list(value):
                if role not in current_roles:
                    current_roles.append(role)
            merged[key] = current_roles
            continue
        merged[key] = value
    return merged


def _classify_reply_categories(text: str, context_updates: Dict[str, object]) -> list[str]:
    categories = []
    if context_updates or any(keyword in text for keyword in ["角色", "用户", "产品", "平台", "面向"]):
        categories.append("context")
    if any(
        keyword in text
        for keyword in ["现在", "目前", "最近", "两周", "高峰期", "流程", "漏", "案例", "数据", "基线", "发生"]
    ) or any(character.isdigit() for character in text):
        categories.append("evidence")
    if any(keyword in text for keyword in ["继续产品化", "继续做", "暂缓", "先不做", "优先", "还是继续", "先试"]):
        categories.append("decision")
    if any(keyword in text for keyword in ["合规", "预算", "周期", "资源", "设备", "权限", "上线", "本周", "本月"]):
        categories.append("constraint")
    if not categories:
        categories.append("other")
    return categories


def _infer_gate_choice(lowered_text: str) -> Optional[str]:
    if any(keyword in lowered_text for keyword in ["暂缓", "先不做", "defer"]):
        return "defer"
    if any(keyword in lowered_text for keyword in ["继续产品化", "继续做", "还是继续", "继续推进", "productize"]):
        return "productize-now"
    if any(keyword in lowered_text for keyword in ["先试流程", "先试培训", "非产品", "流程提醒", "培训", "try non product"]):
        return "try-non-product-first"
    return None
