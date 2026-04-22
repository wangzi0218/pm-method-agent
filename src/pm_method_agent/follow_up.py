from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from pm_method_agent.follow_up_copywriter import summarize_partial_question
from pm_method_agent.models import AnalyzerFinding, CaseState
from pm_method_agent.question_resolution import (
    question_family_key,
    question_text_matches,
    reply_answers_question,
)
from pm_method_agent.reply_interpreter import ReplyAnalysis


FOLLOW_UP_FOCUS_KEY = "follow_up_focus"
FOLLOW_UP_REASON_KEY = "follow_up_reason"
FOLLOW_UP_LOOP_STATE_KEY = "follow_up_loop_state"
FOLLOW_UP_CARRYOVER_NOTE_KEY = "follow_up_carryover_note"


@dataclass
class FollowUpPlan:
    questions: List[str]
    focus: str = ""
    reason: str = ""
    loop_state: str = "ready"
    carryover_note: str = ""


def attach_follow_up_plan(case_state: CaseState) -> CaseState:
    plan = build_follow_up_plan(case_state)
    case_state.pending_questions = list(plan.questions)
    if plan.focus:
        case_state.metadata[FOLLOW_UP_FOCUS_KEY] = plan.focus
    else:
        case_state.metadata.pop(FOLLOW_UP_FOCUS_KEY, None)
    if plan.reason:
        case_state.metadata[FOLLOW_UP_REASON_KEY] = plan.reason
    else:
        case_state.metadata.pop(FOLLOW_UP_REASON_KEY, None)
    if plan.carryover_note:
        case_state.metadata[FOLLOW_UP_CARRYOVER_NOTE_KEY] = plan.carryover_note
    else:
        case_state.metadata.pop(FOLLOW_UP_CARRYOVER_NOTE_KEY, None)
    case_state.metadata[FOLLOW_UP_LOOP_STATE_KEY] = plan.loop_state
    return case_state


def build_follow_up_plan(case_state: CaseState) -> FollowUpPlan:
    if case_state.output_kind == "decision-gate-card":
        return FollowUpPlan(
            questions=[],
            focus="先把方向定下来",
            reason=case_state.blocking_reason or "这一步更需要你先拍板，不适合继续补外围信息。",
            loop_state="awaiting-decision",
        )

    if case_state.workflow_state == "deferred":
        return FollowUpPlan(
            questions=[],
            focus="先按暂缓处理",
            reason=case_state.blocking_reason or "这轮先不继续往下推，等条件变化后再接回来。",
            loop_state="deferred",
        )

    if case_state.output_kind == "context-question-card":
        return FollowUpPlan(
            questions=_limit_questions(case_state.pending_questions),
            focus="先把场景对齐",
            reason=case_state.blocking_reason or "基础场景还没对齐，太快往下走容易偏。",
            loop_state="needs-answer",
        )

    if case_state.metadata.get("continue_card_kind") == "pre-framing" and case_state.pre_framing_result is not None:
        return FollowUpPlan(
            questions=_limit_questions(case_state.pre_framing_result.priority_questions),
            focus="先把理解方向收一收",
            reason=case_state.blocking_reason or "先收理解方向，再继续往下判断会更稳。",
            loop_state="needs-answer",
        )

    questions = _prioritize_partial_questions(case_state, _collect_follow_up_questions(case_state))
    if not questions:
        return FollowUpPlan(
            questions=[],
            focus=_follow_up_focus(case_state),
            reason="这轮已经能形成一个阶段结论，后面按需要再继续补。",
            loop_state="settled",
            carryover_note=_carryover_partial_note(case_state),
        )

    return FollowUpPlan(
        questions=questions,
        focus=_follow_up_focus(case_state),
        reason=_follow_up_reason(case_state),
        loop_state="needs-answer" if case_state.workflow_state == "blocked" else "open",
        carryover_note=_carryover_partial_note(case_state),
    )


def is_follow_up_question_answered(
    question: str,
    merged_context: Dict[str, object],
    reply_analysis: ReplyAnalysis,
    reply_text: str,
) -> bool:
    return reply_answers_question(
        question,
        merged_context=merged_context,
        role_relationships=reply_analysis.role_relationships,
        inferred_gate_choice=reply_analysis.inferred_gate_choice,
        reply_text=reply_text,
    )


def _collect_follow_up_questions(case_state: CaseState) -> List[str]:
    asked_questions = list(case_state.metadata.get("answered_questions", []))
    asked_question_keys = {
        _question_family_key(str(item).strip())
        for item in asked_questions
        if str(item).strip()
    }
    candidates: List[str] = []

    if case_state.output_kind == "continue-guidance-card":
        candidates.extend(_role_follow_up_questions(case_state))
    else:
        candidates.extend(_prioritized_unknowns(case_state))
        candidates.extend(_role_follow_up_questions(case_state))

    filtered: List[str] = []
    for item in candidates:
        normalized = str(item).strip()
        if not normalized:
            continue
        question_key = question_family_key(normalized)
        if question_key and question_key in asked_question_keys:
            continue
        if any(question_text_matches(normalized, answered) for answered in asked_questions):
            continue
        if not _question_is_still_open(normalized, case_state):
            continue
        if any(question_text_matches(normalized, existing) for existing in filtered):
            continue
        filtered.append(normalized)
        if len(filtered) >= 3:
            break
    return filtered


def _prioritized_unknowns(case_state: CaseState) -> List[str]:
    ordered_findings = _sort_findings(case_state.findings, stage=case_state.stage)
    unknowns: List[str] = []
    for finding in ordered_findings:
        for item in finding.unknowns:
            rendered = str(item).strip()
            if rendered and rendered not in unknowns:
                unknowns.append(rendered)
    for item in case_state.unknowns:
        rendered = str(item).strip()
        if rendered and rendered not in unknowns:
            unknowns.append(rendered)
    return unknowns


def _sort_findings(findings: List[AnalyzerFinding], *, stage: str) -> List[AnalyzerFinding]:
    dimension_priority = {
        "problem-definition": {"problem-framing": 0, "decision-challenge": 1, "validation-design": 2},
        "decision-challenge": {"decision-challenge": 0, "problem-framing": 1, "validation-design": 2},
        "validation-design": {"validation-design": 0, "decision-challenge": 1, "problem-framing": 2},
    }
    risk_priority = {"high": 0, "medium": 1, "low": 2}
    mapping = dimension_priority.get(stage, dimension_priority["problem-definition"])
    return sorted(
        findings,
        key=lambda item: (
            mapping.get(item.dimension, 9),
            risk_priority.get(item.risk_if_wrong, 9),
            risk_priority.get(item.evidence_level, 9),
        ),
    )


def _role_follow_up_questions(case_state: CaseState) -> List[str]:
    relationships = case_state.metadata.get("role_relationships", {})
    if not isinstance(relationships, dict):
        relationships = {}

    questions: List[str] = []
    if not relationships.get("proposers"):
        questions.append("这次是谁先把这个问题提出来的，还可以再说明确一点。")
    if not relationships.get("users"):
        questions.append("这件事平时是谁在具体操作，和提出需求的人是不是同一类人？")
    if not relationships.get("outcome_owners"):
        questions.append("最后谁会对结果负责，还可以再明确一点。")
    return questions


def _follow_up_focus(case_state: CaseState) -> str:
    if _active_partial_questions(case_state):
        return "先把刚补到一半的点说完整"
    if case_state.stage == "problem-definition":
        return "先把问题收稳"
    if case_state.stage == "decision-challenge":
        return "先把值不值得做看清"
    if case_state.stage == "validation-design":
        return "先把验证前提补稳"
    if case_state.stage == "context-alignment":
        return "先把场景对齐"
    return "继续往下收"


def _follow_up_reason(case_state: CaseState) -> str:
    if _active_partial_questions(case_state):
        return "你这轮已经碰到关键点了，但还有半步没落稳，顺着这一点补完会更省来回。"
    if case_state.workflow_state == "blocked":
        return case_state.blocking_reason or "这一步还有卡点，先补最影响推进的信息会更稳。"
    if case_state.stage == "validation-design":
        return "这轮已经能往验证走，但先补关键前提，后面会少来回。"
    if case_state.stage == "decision-challenge":
        return "这轮已经能看到方向，但还差几项信息才能把投入判断看稳。"
    return "这轮已经有基础判断了，再补最关键的几项会更顺。"


def _carryover_partial_note(case_state: CaseState) -> str:
    if _active_partial_questions(case_state):
        return ""
    raw_items = case_state.metadata.get("last_partial_pending_questions", [])
    if not isinstance(raw_items, list):
        return ""
    if not case_state.pending_questions:
        return ""
    for item in raw_items:
        normalized = str(item).strip()
        if not normalized:
            continue
        summary = summarize_partial_question(normalized, _latest_note(case_state))
        if summary:
            return f"刚才提到的那一点我先记住了，后面如果回到这一层，会接着看：{summary}"
    return ""


def _question_is_still_open(question: str, case_state: CaseState) -> bool:
    context_profile = case_state.context_profile
    relationships = case_state.metadata.get("role_relationships", {})
    if not isinstance(relationships, dict):
        relationships = {}

    if "企业产品、消费者产品还是内部产品" in question:
        return not bool(context_profile.get("business_model"))
    if "主要使用平台是桌面端、移动端、小程序还是多端" in question:
        return not bool(context_profile.get("primary_platform"))
    if "谁提出需求、谁使用产品、谁承担最终结果" in question:
        roles = context_profile.get("target_user_roles", [])
        return not (isinstance(roles, list) and len([item for item in roles if str(item).strip()]) >= 2)
    if "提出来" in question:
        return not bool(relationships.get("proposers"))
    if "具体操作" in question:
        return not bool(relationships.get("users"))
    if "对结果负责" in question:
        return not bool(relationships.get("outcome_owners"))
    return True


def _question_text_matches(left: str, right: str) -> bool:
    return question_text_matches(left, right)


def _compact_text(text: str) -> str:
    from pm_method_agent.question_resolution import compact_question_text

    return compact_question_text(text)


def _question_family_key(text: str) -> str:
    return question_family_key(text)


def _limit_questions(items: List[str]) -> List[str]:
    deduped: List[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized:
            continue
        if any(question_text_matches(normalized, existing) for existing in deduped):
            continue
        deduped.append(normalized)
        if len(deduped) >= 3:
            break
    return deduped


def _active_partial_questions(case_state: CaseState) -> List[str]:
    raw_items = case_state.metadata.get("last_partial_pending_questions", [])
    if not isinstance(raw_items, list):
        return []
    active_items: List[str] = []
    current_questions = list(case_state.pending_questions or [])
    for item in raw_items:
        normalized = str(item).strip()
        if not normalized:
            continue
        if any(question_text_matches(normalized, current) for current in current_questions):
            matched = next(
                (current for current in current_questions if question_text_matches(normalized, current)),
                normalized,
            )
            if matched not in active_items:
                active_items.append(matched)
    return active_items


def _prioritize_partial_questions(case_state: CaseState, questions: List[str]) -> List[str]:
    partials = _active_partial_questions(case_state)
    if not partials:
        return questions
    ordered: List[str] = []
    for partial in partials:
        if partial not in ordered:
            ordered.append(partial)
    for question in questions:
        if question not in ordered:
            ordered.append(question)
        if len(ordered) >= 3:
            break
    return ordered[:3]


def _latest_note(case_state: CaseState) -> str:
    raw_buckets = case_state.metadata.get("session_note_buckets", {})
    if not isinstance(raw_buckets, dict):
        return ""
    for bucket_key in ["evidence_notes", "context_notes", "decision_notes", "constraint_notes", "other_notes"]:
        notes = raw_buckets.get(bucket_key, [])
        if not isinstance(notes, list):
            continue
        for item in reversed(notes):
            rendered = str(item).strip()
            if rendered:
                return rendered
    return ""
