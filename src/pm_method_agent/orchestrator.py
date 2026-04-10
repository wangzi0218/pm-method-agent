from __future__ import annotations

from typing import Dict, List, Optional

from pm_method_agent.analyzers import (
    analyze_decision_challenge,
    analyze_problem_framing,
    analyze_validation_design,
)
from pm_method_agent.case_copywriter import apply_case_copywriting
from pm_method_agent.models import CaseState
from pm_method_agent.pre_framing import build_pre_framing_result, should_trigger_pre_framing
from pm_method_agent.runtime_config import get_llm_runtime_status


MODE_TO_STAGE = {
    "problem-framing": "problem-definition",
    "decision-challenge": "decision-challenge",
    "validation-design": "validation-design",
}

REQUIRED_CONTEXT_QUESTIONS = {
    "business_model": "当前产品属于企业产品、消费者产品还是内部产品？",
    "primary_platform": "当前主要使用平台是桌面端、移动端、小程序还是多端？",
    "target_user_roles": "谁提出需求、谁使用产品、谁承担最终结果？",
}


def run_analysis(
    raw_input: str,
    mode: str = "auto",
    case_id: str = "case-001",
    show_case_id: bool = False,
) -> CaseState:
    return run_analysis_with_context(
        raw_input=raw_input,
        mode=mode,
        case_id=case_id,
        context_profile=None,
        show_case_id=show_case_id,
        metadata=None,
    )


def _run_analysis(
    raw_input: str,
    mode: str,
    case_id: str,
    context_profile: Optional[Dict[str, object]],
    show_case_id: bool,
    metadata: Optional[Dict[str, object]],
) -> CaseState:
    if mode.strip().lower() == "auto":
        return _run_agent_flow(
            raw_input=raw_input,
            case_id=case_id,
            context_profile=context_profile,
            show_case_id=show_case_id,
            metadata=metadata,
        )

    selected_modes = _resolve_modes(mode)
    case_state = CaseState(
        case_id=case_id,
        stage=MODE_TO_STAGE[selected_modes[0]],
        raw_input=raw_input.strip(),
        workflow_state=MODE_TO_STAGE[selected_modes[0]],
        output_kind="review-card",
        context_profile=context_profile or {},
        metadata={
            "selected_modes": selected_modes,
            "show_case_id": show_case_id,
            "llm_runtime": get_llm_runtime_status(),
            **dict(metadata or {}),
        },
    )

    for selected_mode in selected_modes:
        if selected_mode == "problem-framing":
            analyze_problem_framing(case_state)
        elif selected_mode == "decision-challenge":
            analyze_decision_challenge(case_state)
        elif selected_mode == "validation-design":
            analyze_validation_design(case_state)

    return apply_case_copywriting(case_state)


def _run_agent_flow(
    raw_input: str,
    case_id: str,
    context_profile: Optional[Dict[str, object]],
    show_case_id: bool,
    metadata: Optional[Dict[str, object]],
) -> CaseState:
    normalized_input = raw_input.strip()
    case_state = CaseState(
        case_id=case_id,
        stage="intake",
        workflow_state="intake",
        output_kind="review-card",
        raw_input=normalized_input,
        context_profile=context_profile or {},
        metadata={
            "selected_modes": [],
            "show_case_id": show_case_id,
            "llm_runtime": get_llm_runtime_status(),
            **dict(metadata or {}),
        },
    )
    return _continue_agent_flow(case_state, "pre-framing")


def run_analysis_with_context(
    raw_input: str,
    mode: str = "auto",
    case_id: str = "case-001",
    context_profile: Optional[Dict[str, object]] = None,
    show_case_id: bool = False,
    metadata: Optional[Dict[str, object]] = None,
) -> CaseState:
    return _run_analysis(raw_input, mode, case_id, context_profile, show_case_id, metadata)


def continue_analysis_with_context(
    raw_input: str,
    start_stage: str,
    case_id: str = "case-001",
    context_profile: Optional[Dict[str, object]] = None,
    show_case_id: bool = False,
    metadata: Optional[Dict[str, object]] = None,
) -> CaseState:
    normalized_start_stage = start_stage.strip().lower()
    if normalized_start_stage not in {
        "pre-framing",
        "context-alignment",
        "problem-definition",
        "decision-challenge",
        "validation-design",
    }:
        raise ValueError(
            "Unsupported start_stage. Use one of: pre-framing, context-alignment, "
            "problem-definition, decision-challenge, validation-design."
        )

    case_state = CaseState(
        case_id=case_id,
        stage=normalized_start_stage,
        workflow_state=normalized_start_stage,
        output_kind="review-card",
        raw_input=raw_input.strip(),
        context_profile=context_profile or {},
        metadata={
            "selected_modes": [],
            "show_case_id": show_case_id,
            "llm_runtime": get_llm_runtime_status(),
            **dict(metadata or {}),
        },
    )
    return _continue_agent_flow(case_state, normalized_start_stage)


def _resolve_modes(mode: str) -> List[str]:
    normalized = mode.strip().lower()
    if normalized == "auto":
        return [
            "problem-framing",
            "decision-challenge",
            "validation-design",
        ]
    if normalized not in MODE_TO_STAGE:
        raise ValueError(
            "Unsupported mode. Use one of: auto, problem-framing, decision-challenge, validation-design."
        )
    return [normalized]


def _continue_agent_flow(case_state: CaseState, start_stage: str) -> CaseState:
    if start_stage == "pre-framing":
        if should_trigger_pre_framing(case_state):
            return apply_case_copywriting(_build_pre_framing_card(case_state))
        start_stage = "context-alignment"

    if start_stage == "context-alignment":
        if should_trigger_pre_framing(case_state):
            return apply_case_copywriting(_build_pre_framing_card(case_state))
        if _should_request_context_before_analysis(case_state):
            return apply_case_copywriting(_build_context_alignment_card(case_state))
        start_stage = "problem-definition"

    if start_stage == "problem-definition":
        case_state.metadata["continue_card_kind"] = ""
        case_state.workflow_state = "problem-definition"
        analyze_problem_framing(case_state)
        case_state.metadata["selected_modes"].append("problem-framing")
        if _should_block_after_problem_definition(case_state):
            return apply_case_copywriting(_build_problem_block_card(case_state))
        start_stage = "decision-challenge"

    if start_stage == "decision-challenge":
        case_state.metadata["continue_card_kind"] = ""
        case_state.workflow_state = "decision-challenge"
        analyze_decision_challenge(case_state)
        case_state.metadata["selected_modes"].append("decision-challenge")
        if _should_block_after_decision_challenge(case_state):
            return apply_case_copywriting(_build_decision_gate_card(case_state))
        start_stage = "validation-design"

    if start_stage == "validation-design":
        case_state.metadata["continue_card_kind"] = ""
        case_state.workflow_state = "validation-design"
        analyze_validation_design(case_state)
        case_state.metadata["selected_modes"].append("validation-design")
        case_state.workflow_state = "done"
        case_state.output_kind = "review-card"
        case_state.metadata["next_stage"] = "已完成当前轮次分析"
        return apply_case_copywriting(case_state)

    return apply_case_copywriting(case_state)


def _build_pre_framing_card(case_state: CaseState) -> CaseState:
    pre_framing_result = build_pre_framing_result(case_state)
    missing_context_questions = _missing_context_questions(case_state)
    case_state.stage = "pre-framing"
    case_state.workflow_state = "blocked"
    case_state.output_kind = "continue-guidance-card"
    case_state.pre_framing_result = pre_framing_result
    case_state.blocking_reason = pre_framing_result.reason
    case_state.pending_questions = (
        missing_context_questions[:3]
        if missing_context_questions
        else list(pre_framing_result.priority_questions)
    )
    case_state.normalized_summary = pre_framing_result.reason or "这件事还有几种都说得通的理解，先收一收会更稳。"
    case_state.extend_next_actions(
        [
            "先回答更像哪一类问题，再决定要不要往方案层走。",
            "优先补发生环节、关键角色和为什么现在更值得处理。",
        ]
    )
    case_state.metadata["next_stage"] = "context-alignment" if missing_context_questions else "problem-definition"
    case_state.metadata["continue_card_kind"] = "pre-framing"
    return case_state


def _missing_context_questions(case_state: CaseState) -> List[str]:
    context_profile = case_state.context_profile
    questions: List[str] = []
    if not context_profile.get("business_model"):
        questions.append(REQUIRED_CONTEXT_QUESTIONS["business_model"])
    if not context_profile.get("primary_platform"):
        questions.append(REQUIRED_CONTEXT_QUESTIONS["primary_platform"])
    if not _has_min_role_context(context_profile):
        questions.append(REQUIRED_CONTEXT_QUESTIONS["target_user_roles"])
    return questions


def _has_min_role_context(context_profile: Dict[str, object]) -> bool:
    roles = context_profile.get("target_user_roles", [])
    if not isinstance(roles, list):
        return False
    normalized_roles = [str(role).strip() for role in roles if str(role).strip()]
    return len(normalized_roles) >= 2


def _should_request_context_before_analysis(case_state: CaseState) -> bool:
    missing_questions = _missing_context_questions(case_state)
    if not missing_questions:
        return False
    return len(missing_questions) >= 2 or len(case_state.raw_input.strip()) < 20


def _build_context_alignment_card(case_state: CaseState) -> CaseState:
    pending_questions = _missing_context_questions(case_state)[:3]
    case_state.stage = "context-alignment"
    case_state.workflow_state = "blocked"
    case_state.output_kind = "context-question-card"
    case_state.blocking_reason = "场景信息还不够，太快往下看，判断容易跑偏。"
    case_state.pending_questions = pending_questions
    case_state.normalized_summary = "先补几项场景信息，再继续往下看会更稳一些。"
    case_state.extend_next_actions(
        [
            "先补充产品类型、主要平台和关键用户角色。",
            "补完这几项后，再进入问题定义审查。",
        ]
    )
    case_state.metadata["next_stage"] = "problem-definition"
    case_state.metadata["continue_card_kind"] = ""
    return case_state


def _should_block_after_problem_definition(case_state: CaseState) -> bool:
    if len(case_state.raw_input.strip()) < 20:
        return True
    for finding in case_state.findings:
        if finding.dimension == "problem-framing" and finding.claim_type == "missing-information":
            return True
    return False


def _build_problem_block_card(case_state: CaseState) -> CaseState:
    case_state.workflow_state = "blocked"
    case_state.output_kind = "stage-block-card"
    case_state.blocking_reason = "问题本身还没有收稳，现在往下聊方案，容易把力气用偏。"
    case_state.metadata["next_stage"] = "problem-definition"
    case_state.metadata["continue_card_kind"] = ""
    return case_state


def _should_block_after_decision_challenge(case_state: CaseState) -> bool:
    for gate in case_state.decision_gates:
        if gate.stage == "decision-challenge" and gate.blocking:
            return True
    return False


def _build_decision_gate_card(case_state: CaseState) -> CaseState:
    case_state.workflow_state = "blocked"
    case_state.output_kind = "decision-gate-card"
    case_state.blocking_reason = "这一轮先把要不要继续产品化定下来，再往验证设计走。"
    case_state.metadata["next_stage"] = "decision-challenge"
    case_state.metadata["continue_card_kind"] = ""
    return case_state
