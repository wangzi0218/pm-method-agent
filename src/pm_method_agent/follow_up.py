from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from pm_method_agent.models import AnalyzerFinding, CaseState
from pm_method_agent.reply_interpreter import ReplyAnalysis


FOLLOW_UP_FOCUS_KEY = "follow_up_focus"
FOLLOW_UP_REASON_KEY = "follow_up_reason"
FOLLOW_UP_LOOP_STATE_KEY = "follow_up_loop_state"


@dataclass
class FollowUpPlan:
    questions: List[str]
    focus: str = ""
    reason: str = ""
    loop_state: str = "ready"


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

    questions = _collect_follow_up_questions(case_state)
    if not questions:
        return FollowUpPlan(
            questions=[],
            focus=_follow_up_focus(case_state),
            reason="这轮已经能形成一个阶段结论，后面按需要再继续补。",
            loop_state="settled",
        )

    return FollowUpPlan(
        questions=questions,
        focus=_follow_up_focus(case_state),
        reason=_follow_up_reason(case_state),
        loop_state="needs-answer" if case_state.workflow_state == "blocked" else "open",
    )


def is_follow_up_question_answered(
    question: str,
    merged_context: Dict[str, object],
    reply_analysis: ReplyAnalysis,
    reply_text: str,
) -> bool:
    normalized_question = question.strip()
    lowered = reply_text.lower()

    if "企业产品、消费者产品还是内部产品" in normalized_question:
        return bool(merged_context.get("business_model"))
    if "主要使用平台是桌面端、移动端、小程序还是多端" in normalized_question:
        return bool(merged_context.get("primary_platform"))
    if "谁提出需求、谁使用产品、谁承担最终结果" in normalized_question:
        roles = merged_context.get("target_user_roles", [])
        normalized_roles = [str(role).strip() for role in roles] if isinstance(roles, list) else []
        relationships = reply_analysis.role_relationships
        return (
            len([role for role in normalized_roles if role]) >= 2
            and bool(relationships.get("outcome_owners") or _has_responsibility_signal(reply_text))
        )

    if any(marker in normalized_question for marker in ["提出需求的人", "提出者"]):
        return bool(reply_analysis.role_relationships.get("proposers"))
    if any(marker in normalized_question for marker in ["实际使用的人", "实际使用者", "平时是谁在具体操作"]):
        return bool(reply_analysis.role_relationships.get("users")) or _contains_any(
            lowered,
            ["前台", "店员", "运营", "用户", "专员", "医生", "管理者"],
        )
    if any(marker in normalized_question for marker in ["结果责任人", "对结果负责", "谁会对结果负责"]):
        return bool(reply_analysis.role_relationships.get("outcome_owners")) or _has_responsibility_signal(reply_text)

    if _contains_any(normalized_question, ["流程", "环节", "真实过程", "怎么运行"]):
        return _contains_any(lowered, ["流程", "手工", "线下", "列表", "路径", "步骤", "环节", "现在主要靠"])

    if _contains_any(normalized_question, ["频率", "多久", "影响范围", "影响到什么结果", "基线数据"]):
        return _contains_any(
            lowered,
            ["每天", "每周", "每月", "经常", "偶尔", "最近", "投诉", "影响", "到诊率", "发帖率", "%", "次"],
        ) or any(char.isdigit() for char in reply_text)

    if _contains_any(normalized_question, ["为什么现在", "机会成本", "晚三个月", "时间窗口"]):
        return _contains_any(
            lowered,
            ["现在", "最近", "本月", "这个月", "排期", "资源", "窗口", "机会成本", "来不及", "影响"],
        )

    if _contains_any(normalized_question, ["非产品", "培训", "管理", "流程路径", "替代方案"]):
        return bool(reply_analysis.inferred_gate_choice == "try-non-product-first") or _contains_any(
            lowered,
            ["流程", "培训", "管理", "人工", "线下", "运营", "先试", "替代"],
        )

    if _contains_any(normalized_question, ["成功指标", "护栏指标", "停止条件", "最小验证动作", "验证周期", "基线指标"]):
        return _contains_any(
            lowered,
            ["指标", "成功", "失败", "停止", "验证", "基线", "观察", "周期", "到诊率", "转化", "留存", "%", "首帖率"],
        ) or any(char.isdigit() for char in reply_text)

    if _contains_any(normalized_question, ["目标和约束是否一致", "角色关系", "目标差异"]):
        return bool(reply_analysis.role_relationships.get("users")) and (
            bool(reply_analysis.role_relationships.get("outcome_owners"))
            or _contains_any(lowered, ["关注", "目标", "效率", "营收", "简单", "体验", "结果"])
        )

    return _question_keyword_overlap(normalized_question, reply_text)


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
        question_key = _question_family_key(normalized)
        if question_key and question_key in asked_question_keys:
            continue
        if any(_question_text_matches(normalized, answered) for answered in asked_questions):
            continue
        if not _question_is_still_open(normalized, case_state):
            continue
        if any(_question_text_matches(normalized, existing) for existing in filtered):
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
    if case_state.workflow_state == "blocked":
        return case_state.blocking_reason or "这一步还有卡点，先补最影响推进的信息会更稳。"
    if case_state.stage == "validation-design":
        return "这轮已经能往验证走，但先补关键前提，后面会少来回。"
    if case_state.stage == "decision-challenge":
        return "这轮已经能看到方向，但还差几项信息才能把投入判断看稳。"
    return "这轮已经有基础判断了，再补最关键的几项会更顺。"


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
    left_key = _question_family_key(left)
    right_key = _question_family_key(right)
    if left_key and right_key and left_key == right_key:
        return True
    normalized_left = _compact_text(left)
    normalized_right = _compact_text(right)
    if not normalized_left or not normalized_right:
        return False
    return normalized_left in normalized_right or normalized_right in normalized_left


def _compact_text(text: str) -> str:
    compact = text.strip()
    for token in ["当前", "这轮", "还可以", "再", "先", "是否", "是什么", "怎么", "。", "，", "、", " ", "？", "?"]:
        compact = compact.replace(token, "")
    return compact


def _question_family_key(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""

    family_markers = [
        ("business-model", ["企业产品、消费者产品还是内部产品", "产品类型", "企业产品", "消费者产品", "内部产品"]),
        ("primary-platform", ["主要使用平台是桌面端、移动端、小程序还是多端", "主要平台", "主要交付和使用平台"]),
        ("role-triplet", ["谁提出需求、谁使用产品、谁承担最终结果", "关键用户角色"]),
        ("proposer", ["谁是提出需求的人", "提出者", "谁先把这个问题提出来"]),
        ("user", ["谁是实际使用的人", "实际使用者", "平时是谁在具体操作"]),
        ("outcome-owner", ["谁承担最终业务结果", "结果责任人", "谁会对结果负责", "最后谁会对结果负责"]),
        ("role-alignment", ["目标和约束是否一致", "目标差异", "角色关系", "协作边界"]),
        ("process-flow", ["当前流程", "真实过程", "流程是怎么运行", "发生在流程的哪个环节"]),
        ("issue-frequency", ["频率和影响范围", "多久出现一次", "影响到什么结果", "问题发生的频率"]),
        ("existing-workaround", ["替代方案", "绕路方式", "现有替代做法"]),
        ("why-now", ["为什么现在", "时间窗口", "偏偏是现在"]),
        ("opportunity-cost", ["机会成本", "晚三个月", "会损失什么"]),
        ("non-product-path", ["非产品", "培训", "管理", "流程路径", "替代方案", "不同解法"]),
        ("success-metric", ["成功指标"]),
        ("guardrail-metric", ["护栏指标"]),
        ("stop-condition", ["停止条件", "失败或停止条件"]),
        ("baseline-metric", ["基线指标", "基线数据", "当前的基线数据", "当前基线指标"]),
        ("validation-action", ["最小验证动作", "观察什么变化"]),
        ("validation-period", ["验证周期"]),
    ]
    for family_key, markers in family_markers:
        if any(marker in normalized for marker in markers):
            return family_key
    return ""


def _question_keyword_overlap(question: str, reply_text: str) -> bool:
    keywords = [
        token
        for token in ["流程", "角色", "目标", "结果", "证据", "频率", "影响", "指标", "验证", "平台", "产品"]
        if token in question
    ]
    if not keywords:
        return False
    return sum(1 for token in keywords if token in reply_text) >= 1


def _has_responsibility_signal(text: str) -> bool:
    return _contains_any(text, ["负责", "结果", "店长", "管理者", "负责人", "老板", "核心医生"])


def _contains_any(text: str, items: List[str]) -> bool:
    return any(item in text for item in items)


def _limit_questions(items: List[str]) -> List[str]:
    deduped: List[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized:
            continue
        if any(_question_text_matches(normalized, existing) for existing in deduped):
            continue
        deduped.append(normalized)
        if len(deduped) >= 3:
            break
    return deduped
