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
FOLLOW_UP_QUESTION_BUDGET_KEY = "follow_up_question_budget"
FOLLOW_UP_STRATEGY_KEY = "follow_up_strategy"
FOLLOW_UP_STOP_REASON_KEY = "follow_up_stop_reason"


@dataclass
class FollowUpPlan:
    questions: List[str]
    focus: str = ""
    reason: str = ""
    loop_state: str = "ready"
    carryover_note: str = ""
    question_budget: int = 0
    strategy: str = ""
    stop_reason: str = ""


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
    case_state.metadata[FOLLOW_UP_QUESTION_BUDGET_KEY] = max(0, int(plan.question_budget))
    if plan.strategy:
        case_state.metadata[FOLLOW_UP_STRATEGY_KEY] = plan.strategy
    else:
        case_state.metadata.pop(FOLLOW_UP_STRATEGY_KEY, None)
    if plan.stop_reason:
        case_state.metadata[FOLLOW_UP_STOP_REASON_KEY] = plan.stop_reason
    else:
        case_state.metadata.pop(FOLLOW_UP_STOP_REASON_KEY, None)
    case_state.metadata[FOLLOW_UP_LOOP_STATE_KEY] = plan.loop_state
    return case_state


def build_follow_up_plan(case_state: CaseState) -> FollowUpPlan:
    if case_state.output_kind == "decision-gate-card":
        return FollowUpPlan(
            questions=[],
            focus="先把方向定下来",
            reason=case_state.blocking_reason or "这一步更需要你先拍板，不适合继续补外围信息。",
            loop_state="awaiting-decision",
            strategy="gate-first",
            stop_reason="当前已经到人工决策点，这一轮不继续追问外围信息。",
        )

    if case_state.workflow_state == "deferred":
        return FollowUpPlan(
            questions=[],
            focus="先按暂缓处理",
            reason=case_state.blocking_reason or "这轮先不继续往下推，等条件变化后再接回来。",
            loop_state="deferred",
            strategy="deferred-stop",
            stop_reason="用户已经明确表达暂缓倾向，这一轮不继续追问。",
        )

    if case_state.output_kind == "context-question-card":
        questions = _limit_questions(case_state.pending_questions, limit=3)
        return FollowUpPlan(
            questions=questions,
            focus="先把场景对齐",
            reason=case_state.blocking_reason or "基础场景还没对齐，太快往下走容易偏。",
            loop_state="needs-answer",
            question_budget=len(questions),
            strategy="context-bundle",
        )

    if case_state.metadata.get("continue_card_kind") == "pre-framing" and case_state.pre_framing_result is not None:
        questions = _limit_questions(case_state.pre_framing_result.priority_questions, limit=2)
        return FollowUpPlan(
            questions=questions,
            focus="先把理解方向收一收",
            reason=case_state.blocking_reason or "先收理解方向，再继续往下判断会更稳。",
            loop_state="needs-answer",
            question_budget=len(questions),
            strategy="direction-clarification",
        )

    questions = _prioritize_partial_questions(case_state, _collect_follow_up_questions(case_state))
    question_budget = _resolve_question_budget(case_state, questions)
    questions = _limit_questions(questions, limit=question_budget)
    if not questions:
        return FollowUpPlan(
            questions=[],
            focus=_follow_up_focus(case_state),
            reason="这轮已经能形成一个阶段结论，后面按需要再继续补。",
            loop_state="settled",
            carryover_note=_carryover_partial_note(case_state),
            question_budget=question_budget,
            strategy=_resolve_follow_up_strategy(case_state),
            stop_reason=_resolve_settled_stop_reason(case_state),
        )

    return FollowUpPlan(
        questions=questions,
        focus=_follow_up_focus(case_state),
        reason=_follow_up_reason(case_state),
        loop_state="needs-answer" if case_state.workflow_state == "blocked" else "open",
        carryover_note=_carryover_partial_note(case_state),
        question_budget=question_budget,
        strategy=_resolve_follow_up_strategy(case_state),
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
        return "还差半步。"
    if case_state.workflow_state == "blocked":
        return case_state.blocking_reason or "这一步还有卡点，先补最影响推进的信息会更稳。"
    if case_state.stage == "validation-design":
        return "前提还没补齐。"
    if case_state.stage == "decision-challenge":
        return "投入判断还没站稳。"
    return "还有几项关键信息没补。"


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


def _limit_questions(items: List[str], limit: int = 3) -> List[str]:
    if limit <= 0:
        return []
    deduped: List[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized:
            continue
        if any(question_text_matches(normalized, existing) for existing in deduped):
            continue
        deduped.append(normalized)
        if len(deduped) >= limit:
            break
    return deduped


def _active_partial_questions(case_state: CaseState) -> List[str]:
    raw_items = case_state.metadata.get("last_partial_pending_questions", [])
    if not isinstance(raw_items, list):
        return []
    active_items: List[str] = []
    current_questions = [str(item).strip() for item in list(case_state.pending_questions or []) if str(item).strip()]
    derived_questions = _collect_follow_up_questions(case_state)
    all_candidates: List[str] = []
    for item in current_questions + derived_questions:
        if item and item not in all_candidates:
            all_candidates.append(item)
    for item in raw_items:
        normalized = str(item).strip()
        if not normalized:
            continue
        if any(question_text_matches(normalized, current) for current in all_candidates):
            matched = next(
                (current for current in all_candidates if question_text_matches(normalized, current)),
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


def _resolve_question_budget(case_state: CaseState, questions: List[str]) -> int:
    if not questions:
        return 0
    if _active_partial_questions(case_state):
        return 1
    if len(questions) == 1:
        return 1
    if _questions_form_context_bundle(questions):
        return min(3, len(questions))
    if _questions_are_tightly_coupled(questions[0], questions[1]):
        return 2
    return 1


def _resolve_follow_up_strategy(case_state: CaseState) -> str:
    if _active_partial_questions(case_state):
        return "partial-follow-up"
    if case_state.stage == "problem-definition":
        return "stage-critical"
    if case_state.stage == "decision-challenge":
        return "decision-evidence"
    if case_state.stage == "validation-design":
        return "validation-priority"
    return "default-follow-up"


def _resolve_settled_stop_reason(case_state: CaseState) -> str:
    if case_state.workflow_state == "deferred":
        return "这轮已经按暂缓收住，不继续追问。"
    if case_state.workflow_state == "blocked":
        return "这轮更需要先停在关口或阻塞点上，不继续补外围问题。"
    return "当前阶段已经足够先给结论，这一轮不再为了完整性继续追问。"


def _questions_form_context_bundle(questions: List[str]) -> bool:
    family_keys = [_question_family_key(question) for question in questions[:3]]
    normalized_keys = {key for key in family_keys if key}
    context_bundle_keys = {"business-model", "primary-platform", "role-triplet"}
    if context_bundle_keys.issubset(normalized_keys):
        return True
    role_bundle_keys = {"proposer", "user", "outcome-owner"}
    return role_bundle_keys.issubset(normalized_keys)


def _questions_are_tightly_coupled(left: str, right: str) -> bool:
    pair = {_question_family_key(left), _question_family_key(right)}
    coupled_groups = [
        {"business-model", "primary-platform"},
        {"proposer", "user"},
        {"user", "outcome-owner"},
        {"proposer", "outcome-owner"},
        {"why-now", "opportunity-cost"},
        {"success-metric", "baseline-metric"},
        {"success-metric", "stop-condition"},
        {"guardrail-metric", "stop-condition"},
        {"baseline-metric", "validation-action"},
        {"non-product-path", "opportunity-cost"},
        {"role-triplet", "role-alignment"},
    ]
    return any(pair == group for group in coupled_groups)


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
