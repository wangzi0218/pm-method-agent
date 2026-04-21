from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from pm_method_agent.case_copywriter import apply_case_copywriting
from pm_method_agent.follow_up import attach_follow_up_plan, is_follow_up_question_answered
from pm_method_agent.follow_up_copywriter import apply_follow_up_copywriting
from pm_method_agent.models import CaseState, ProjectProfile
from pm_method_agent.orchestrator import continue_analysis_with_context, run_analysis_with_context
from pm_method_agent.project_profile_service import merge_project_profile_context
from pm_method_agent.reply_interpreter import (
    ReplyAnalysis,
    ReplyInterpreter,
    build_reply_interpreter_from_env,
)
from pm_method_agent.role_extraction import normalize_role_name
from pm_method_agent.runtime_config import get_llm_runtime_status


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
SESSION_LAST_GATE_CHOICE_KEY = "last_gate_choice"
SESSION_LAST_REPLY_PARSER_KEY = "last_reply_parser"
SESSION_ROLE_RELATIONSHIPS_KEY = "role_relationships"
SESSION_LAST_PARTIAL_PENDING_QUESTIONS_KEY = "last_partial_pending_questions"

NOTE_BUCKET_KEYS = [
    "context_notes",
    "evidence_notes",
    "decision_notes",
    "constraint_notes",
    "other_notes",
]

NOTE_BUCKET_LABELS = {
    "context_notes": "这轮补到的场景背景",
    "evidence_notes": "这轮补到的现状和证据",
    "decision_notes": "这轮补到的判断倾向",
    "constraint_notes": "这轮补到的约束条件",
    "other_notes": "这轮顺手补充",
}


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
    project_profile: Optional[ProjectProfile] = None,
    mode: str = "auto",
    case_id: Optional[str] = None,
    store: Optional[LocalCaseStore] = None,
) -> CaseState:
    active_store = store or default_store()
    resolved_case_id = case_id or _generate_case_id()
    merged_context_profile = merge_project_profile_context(project_profile, context_profile)
    initial_reply_analysis = build_reply_interpreter_from_env().analyze_reply(raw_input)
    merged_context_profile = _merge_context_profile(
        merged_context_profile,
        initial_reply_analysis.context_updates,
        raw_input,
    )
    initial_role_relationships = _normalize_role_relationships(initial_reply_analysis.role_relationships)
    case_state = run_analysis_with_context(
        raw_input=raw_input,
        mode=mode,
        case_id=resolved_case_id,
        context_profile=merged_context_profile,
        show_case_id=True,
        metadata={SESSION_ROLE_RELATIONSHIPS_KEY: initial_role_relationships},
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
    case_state.metadata[SESSION_LAST_GATE_CHOICE_KEY] = None
    case_state.metadata[SESSION_LAST_REPLY_PARSER_KEY] = None
    case_state.metadata[SESSION_ROLE_RELATIONSHIPS_KEY] = initial_role_relationships
    _record_reply_interpreter_enhancement(case_state, initial_reply_analysis)
    case_state.metadata["llm_runtime"] = get_llm_runtime_status()
    if project_profile is not None:
        project_profile_id = getattr(project_profile, "project_profile_id", None)
        project_name = getattr(project_profile, "project_name", None)
        case_state.metadata["project_profile_id"] = project_profile_id
        case_state.metadata["project_profile_name"] = project_name
    case_state.metadata["show_case_id"] = True
    case_state = attach_follow_up_plan(case_state)
    active_store.save(case_state)
    return case_state


def reply_to_case(
    case_id: str,
    reply_text: str,
    context_profile_updates: Optional[Dict[str, object]] = None,
    store: Optional[LocalCaseStore] = None,
    reply_interpreter: Optional[ReplyInterpreter] = None,
) -> CaseState:
    active_store = store or default_store()
    previous_case = active_store.load(case_id)
    original_input = str(previous_case.metadata.get(SESSION_INPUT_KEY, previous_case.raw_input))
    previous_notes = list(previous_case.metadata.get(SESSION_NOTES_KEY, []))
    updated_notes = previous_notes + [reply_text.strip()]
    active_reply_interpreter = reply_interpreter or build_reply_interpreter_from_env()
    reply_analysis = active_reply_interpreter.analyze_reply(
        reply_text,
        previous_case=previous_case,
    )

    merged_context = _merge_context_profile(
        previous_case.context_profile,
        reply_analysis.context_updates,
        reply_text,
    )
    if context_profile_updates:
        merged_context = _merge_context_profile(merged_context, context_profile_updates, reply_text)

    note_buckets = _merge_note_buckets(
        previous_case.metadata.get(SESSION_NOTE_BUCKETS_KEY, {}),
        reply_analysis,
        reply_text.strip(),
    )
    role_relationships = _merge_role_relationships(
        previous_case.metadata.get(SESSION_ROLE_RELATIONSHIPS_KEY, {}),
        reply_analysis,
    )
    rerun_input = _compose_session_input(original_input, note_buckets)
    answered_in_this_turn = _collect_answered_pending_questions(
        previous_case=previous_case,
        merged_context=merged_context,
        reply_analysis=reply_analysis,
        reply_text=reply_text.strip(),
    )
    resume_stage = _resolve_resume_stage(previous_case, reply_analysis, answered_in_this_turn)
    next_case = _build_next_case_from_reply(
        previous_case=previous_case,
        rerun_input=rerun_input,
        merged_context=merged_context,
        resume_stage=resume_stage,
        reply_analysis=reply_analysis,
        role_relationships=role_relationships,
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
    for question in answered_in_this_turn:
        if question in answered_questions:
            continue
        answered_questions.append(question)

    resolved_gates = list(previous_case.metadata.get(SESSION_RESOLVED_GATES_KEY, []))
    for gate in previous_case.decision_gates:
        if gate.blocking and reply_analysis.inferred_gate_choice:
            resolved_gates.append(
                {
                    "gate_id": gate.gate_id,
                    "stage": gate.stage,
                    "user_choice": reply_analysis.inferred_gate_choice,
                    "recommended_option": gate.recommended_option,
                    "resolution_kind": _resolve_gate_resolution_kind(
                        gate.recommended_option,
                        reply_analysis.inferred_gate_choice,
                    ),
                    "reply_text": reply_text.strip(),
                    "workflow_state_after": next_case.workflow_state,
                    "next_stage_after": next_case.metadata.get("next_stage"),
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
                "gate_choice": reply_analysis.inferred_gate_choice,
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
    next_case.metadata[SESSION_LAST_GATE_CHOICE_KEY] = reply_analysis.inferred_gate_choice
    next_case.metadata[SESSION_LAST_REPLY_PARSER_KEY] = reply_analysis.parser_name
    next_case.metadata[SESSION_ROLE_RELATIONSHIPS_KEY] = role_relationships
    next_case.metadata[SESSION_LAST_PARTIAL_PENDING_QUESTIONS_KEY] = list(reply_analysis.partial_pending_questions)
    _record_reply_interpreter_enhancement(next_case, reply_analysis)
    next_case.metadata["llm_runtime"] = get_llm_runtime_status()
    next_case.metadata["show_case_id"] = True
    next_case = attach_follow_up_plan(next_case)
    next_case = apply_follow_up_copywriting(next_case)
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
    for bucket_key in NOTE_BUCKET_KEYS:
        notes = note_buckets.get(bucket_key, [])
        if not notes:
            continue
        rendered_notes = "\n".join(f"- {note}" for note in notes if note.strip())
        sections.append(f"{NOTE_BUCKET_LABELS[bucket_key]}：\n{rendered_notes}")
    return f"{original_input.strip()}\n\n" + "\n\n".join(sections)


def _generate_case_id() -> str:
    return f"case-{uuid4().hex[:8]}"


def _resolve_resume_stage(
    previous_case: CaseState,
    reply_analysis: ReplyAnalysis,
    answered_in_this_turn: list[str],
) -> str:
    if previous_case.output_kind == "context-question-card":
        return "context-alignment"
    if previous_case.output_kind == "continue-guidance-card":
        next_stage = str(previous_case.metadata.get("next_stage", "") or "").strip()
        return next_stage or "problem-definition"
    if previous_case.output_kind == "stage-block-card":
        next_stage = str(previous_case.metadata.get("next_stage", "") or "").strip()
        return next_stage or "problem-definition"
    if previous_case.output_kind == "decision-gate-card":
        inferred_gate_choice = reply_analysis.inferred_gate_choice
        if inferred_gate_choice == "productize-now" and not _has_blocking_gate(previous_case, "problem-definition"):
            return "validation-design"
        return "decision-challenge"
    if previous_case.workflow_state == "done":
        return _resolve_done_case_resume_stage(previous_case, reply_analysis, answered_in_this_turn)
    return previous_case.stage


def _resolve_done_case_resume_stage(
    previous_case: CaseState,
    reply_analysis: ReplyAnalysis,
    answered_in_this_turn: list[str],
) -> str:
    stage_from_questions = _infer_stage_from_questions(previous_case, answered_in_this_turn)
    if stage_from_questions:
        return stage_from_questions

    stage_from_reply = _infer_stage_from_reply(reply_analysis)
    if stage_from_reply:
        return stage_from_reply

    if previous_case.stage in {"problem-definition", "decision-challenge", "validation-design"}:
        return previous_case.stage
    return "problem-definition"


def _build_next_case_from_reply(
    previous_case: CaseState,
    rerun_input: str,
    merged_context: Dict[str, object],
    resume_stage: str,
    reply_analysis: ReplyAnalysis,
    role_relationships: Dict[str, list[str]],
) -> CaseState:
    inferred_gate_choice = reply_analysis.inferred_gate_choice
    if previous_case.output_kind == "decision-gate-card":
        if not inferred_gate_choice:
            return _build_gate_outcome_case(
                previous_case=previous_case,
                rerun_input=rerun_input,
                merged_context=merged_context,
                summary="这轮回复里，还没有看到你对这个决策关口的明确选择。",
                blocking_reason="这一关需要先定方向，系统才能继续往下推进。",
                workflow_state="blocked",
                output_kind="decision-gate-card",
                next_stage="decision-challenge",
                next_actions=[
                    "可以直接回答：进入产品化阶段、优先评估非产品路径，或暂缓。",
                    "如果你已经有倾向，也可以顺手补一句原因，系统会继续承接。",
                ],
            )
        if inferred_gate_choice == "defer":
            return _build_gate_outcome_case(
                previous_case=previous_case,
                rerun_input=rerun_input,
                merged_context=merged_context,
                summary="这轮先记为暂缓，暂不继续推进产品化。",
                blocking_reason="这轮先按暂缓处理；如果后面条件变了，再接着往下看。",
                workflow_state="deferred",
                output_kind="stage-block-card",
                next_stage="decision-challenge",
                next_actions=[
                    "记录本轮暂缓原因和重新开启条件。",
                    "后续如果出现新证据，再重新进入当前案例。",
                ],
            )
        if inferred_gate_choice == "try-non-product-first":
            return _build_gate_outcome_case(
                previous_case=previous_case,
                rerun_input=rerun_input,
                merged_context=merged_context,
                summary="这轮先转去看非产品路径，再决定要不要继续产品化。",
                blocking_reason="这轮先按非产品路径看，先试流程、培训或管理方案。",
                workflow_state="blocked",
                output_kind="stage-block-card",
                next_stage="decision-challenge",
                next_actions=[
                    "先列出流程、培训、管理三类可试路径。",
                    "为非产品路径补一个最小试行周期和观察指标。",
                ],
            )
    return continue_analysis_with_context(
        raw_input=rerun_input,
        start_stage=resume_stage,
        case_id=previous_case.case_id,
        context_profile=merged_context,
        show_case_id=True,
        metadata={
            SESSION_ROLE_RELATIONSHIPS_KEY: role_relationships,
            "skip_pre_framing": previous_case.output_kind == "continue-guidance-card",
        },
    )


def _build_gate_outcome_case(
    previous_case: CaseState,
    rerun_input: str,
    merged_context: Dict[str, object],
    summary: str,
    blocking_reason: str,
    workflow_state: str,
    output_kind: str,
    next_stage: str,
    next_actions: list[str],
) -> CaseState:
    case_state = CaseState.from_dict(previous_case.to_dict())
    case_state.raw_input = rerun_input
    case_state.context_profile = merged_context
    case_state.workflow_state = workflow_state
    case_state.output_kind = output_kind
    case_state.normalized_summary = summary
    case_state.blocking_reason = blocking_reason
    case_state.next_actions = next_actions
    case_state.metadata["selected_modes"] = ["decision-challenge"]
    case_state.metadata["next_stage"] = next_stage
    return apply_follow_up_copywriting(apply_case_copywriting(attach_follow_up_plan(case_state)))


def _empty_note_buckets() -> Dict[str, list[str]]:
    return {bucket_key: [] for bucket_key in NOTE_BUCKET_KEYS}


def _collect_answered_pending_questions(
    *,
    previous_case: CaseState,
    merged_context: Dict[str, object],
    reply_analysis: ReplyAnalysis,
    reply_text: str,
) -> list[str]:
    answered_questions: list[str] = []
    for question in reply_analysis.answered_pending_questions:
        if question not in answered_questions:
            answered_questions.append(question)
    for question in previous_case.pending_questions:
        if question in reply_analysis.partial_pending_questions:
            continue
        if question in answered_questions:
            continue
        if is_follow_up_question_answered(question, merged_context, reply_analysis, reply_text):
            answered_questions.append(question)
    return answered_questions


def _record_reply_interpreter_enhancement(case_state: CaseState, reply_analysis: ReplyAnalysis) -> None:
    enhancements = case_state.metadata.get("llm_enhancements")
    if not isinstance(enhancements, dict):
        enhancements = {}
    enhancements["reply-interpreter"] = {
        "engine": reply_analysis.parser_name,
        "fallback_used": reply_analysis.fallback_used,
        "fallback_reason": reply_analysis.fallback_reason,
    }
    case_state.metadata["llm_enhancements"] = enhancements


def _merge_note_buckets(
    previous_buckets: object,
    reply_analysis: ReplyAnalysis,
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
    target_bucket = _select_primary_note_bucket(reply_analysis, bucket_mapping)
    if reply_text not in merged[target_bucket]:
        merged[target_bucket].append(reply_text)
    return merged


def _select_primary_note_bucket(
    reply_analysis: ReplyAnalysis,
    bucket_mapping: Dict[str, str],
) -> str:
    if reply_analysis.inferred_gate_choice:
        return bucket_mapping["decision"]
    for category in ["decision", "evidence", "constraint", "context", "other"]:
        if category in reply_analysis.categories:
            if category == "context" and not (
                reply_analysis.context_updates or any(reply_analysis.role_relationships.values())
            ):
                continue
            return bucket_mapping[category]
    if reply_analysis.context_updates or any(reply_analysis.role_relationships.values()):
        return bucket_mapping["context"]
    return bucket_mapping["other"]


def _merge_role_relationships(
    previous_relationships: object,
    reply_analysis: ReplyAnalysis,
) -> Dict[str, list[str]]:
    merged = _normalize_role_relationships(previous_relationships)
    current = _normalize_role_relationships(reply_analysis.role_relationships)
    for key, items in current.items():
        if items:
            merged[key] = list(items)
            continue
        for item in items:
            if item not in merged[key]:
                merged[key].append(item)
    return merged


def _normalize_role_relationships(value: object) -> Dict[str, list[str]]:
    normalized = {
        "proposers": [],
        "users": [],
        "outcome_owners": [],
    }
    if not isinstance(value, dict):
        return normalized
    for key in normalized:
        items = value.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            rendered = normalize_role_name(str(item).strip())
            if rendered and rendered not in normalized[key]:
                normalized[key].append(rendered)
    return normalized


def _merge_context_profile(
    existing: Dict[str, object],
    updates: Optional[Dict[str, object]],
    source_text: str = "",
) -> Dict[str, object]:
    merged = dict(existing)
    if not updates:
        return merged
    for key, value in updates.items():
        if key == "target_user_roles":
            if _has_explicit_correction_signal(source_text):
                deduped_roles: list[str] = []
                for role in list(value):
                    if role not in deduped_roles:
                        deduped_roles.append(role)
                merged[key] = deduped_roles
                continue
            current_roles = list(merged.get(key, []))
            for role in list(value):
                if role not in current_roles:
                    current_roles.append(role)
            merged[key] = current_roles
            continue
        merged[key] = value
    return merged


def _has_blocking_gate(case_state: CaseState, stage: str) -> bool:
    return any(gate.stage == stage and gate.blocking for gate in case_state.decision_gates)


def _resolve_gate_resolution_kind(recommended_option: str, user_choice: str) -> str:
    if user_choice == recommended_option:
        return "accepted-recommendation"
    return "overrode-recommendation"


def _infer_stage_from_questions(previous_case: CaseState, questions: list[str]) -> str:
    if not questions:
        return ""
    scores = {
        "context-alignment": 0,
        "problem-definition": 0,
        "decision-challenge": 0,
        "validation-design": 0,
    }
    for question in questions:
        matched = False
        for finding in previous_case.findings:
            for unknown in finding.unknowns:
                if _question_text_matches(question, str(unknown)):
                    scores[_normalize_dimension_to_stage(finding.dimension)] += 2
                    matched = True
                    break
            if matched:
                break
        if matched:
            continue
        scores[_infer_stage_from_question_text(question, previous_case)] += 1
    best_stage, best_score = max(scores.items(), key=lambda item: item[1])
    return best_stage if best_score > 0 else ""


def _infer_stage_from_reply(reply_analysis: ReplyAnalysis) -> str:
    if reply_analysis.inferred_gate_choice:
        return "decision-challenge"
    if reply_analysis.context_updates or any(reply_analysis.role_relationships.values()):
        return "problem-definition"
    categories = list(reply_analysis.categories)
    if "decision" in categories:
        return "decision-challenge"
    if "constraint" in categories:
        return "decision-challenge"
    if "evidence" in categories:
        return "validation-design"
    return ""


def _normalize_dimension_to_stage(dimension: str) -> str:
    mapping = {
        "problem-framing": "problem-definition",
        "decision-challenge": "decision-challenge",
        "validation-design": "validation-design",
    }
    return mapping.get(dimension, "problem-definition")


def _infer_stage_from_question_text(question: str, previous_case: CaseState) -> str:
    normalized = question.strip()
    if any(
        marker in normalized
        for marker in [
            "企业产品、消费者产品还是内部产品",
            "主要使用平台是桌面端、移动端、小程序还是多端",
            "谁提出需求、谁使用产品、谁承担最终结果",
        ]
    ):
        return "context-alignment"
    if any(
        marker in normalized
        for marker in [
            "提出需求的人",
            "实际使用的人",
            "结果责任人",
            "现象层",
            "为什么现在会发生",
            "当前流程",
            "频率和影响范围",
            "替代方案",
            "角色关系",
            "目标差异",
        ]
    ):
        return "problem-definition"
    if any(
        marker in normalized
        for marker in [
            "为什么现在",
            "机会成本",
            "晚三个月",
            "非产品",
            "培训",
            "管理",
            "流程路径",
            "时间窗口",
        ]
    ):
        return "decision-challenge"
    if any(
        marker in normalized
        for marker in [
            "成功指标",
            "护栏指标",
            "停止条件",
            "最小验证动作",
            "验证周期",
            "基线指标",
            "基线数据",
        ]
    ):
        return "validation-design"
    return previous_case.stage if previous_case.stage in {"problem-definition", "decision-challenge", "validation-design"} else "problem-definition"


def _question_text_matches(left: str, right: str) -> bool:
    normalized_left = _compact_question_text(left)
    normalized_right = _compact_question_text(right)
    if not normalized_left or not normalized_right:
        return False
    return normalized_left in normalized_right or normalized_right in normalized_left


def _compact_question_text(text: str) -> str:
    compact = text.strip()
    for token in ["当前", "这轮", "还可以", "再", "先", "是否", "是什么", "怎么", "。", "，", "、", " ", "？", "?"]:
        compact = compact.replace(token, "")
    return compact


def _has_explicit_correction_signal(source_text: str) -> bool:
    text = source_text.strip()
    if not text:
        return False
    return any(
        pattern in text
        for pattern in [
            "不是",
            "而是",
            "其实是",
            "其实不是",
            "更准确说",
            "准确说",
            "刚确认",
            "修正一下",
            "改成",
        ]
    )
