from __future__ import annotations

from typing import Dict, List


def compact_question_text(text: str) -> str:
    compact = text.strip()
    for token in ["当前", "这轮", "还可以", "再", "先", "是否", "是什么", "怎么", "。", "，", "、", " ", "？", "?"]:
        compact = compact.replace(token, "")
    return compact


def question_family_key(text: str) -> str:
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
        ("non-product-path", ["非产品", "培训", "管理", "流程路径", "替代方案", "不同解法", "不改产品能否先解决 60%"]),
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


def question_text_matches(left: str, right: str) -> bool:
    left_key = question_family_key(left)
    right_key = question_family_key(right)
    if left_key and right_key and left_key == right_key:
        return True
    normalized_left = compact_question_text(left)
    normalized_right = compact_question_text(right)
    if not normalized_left or not normalized_right:
        return False
    return normalized_left in normalized_right or normalized_right in normalized_left


def normalize_question_matches(candidates: object, pending_questions: List[str]) -> List[str]:
    if not isinstance(candidates, list):
        return []
    normalized_matches: List[str] = []
    for item in candidates:
        if not isinstance(item, str) or not item.strip():
            continue
        matched = _match_to_pending_question(item.strip(), pending_questions)
        if matched and matched not in normalized_matches:
            normalized_matches.append(matched)
    return normalized_matches


def resolve_pending_question_matches(
    pending_questions: List[str],
    *,
    merged_context: Dict[str, object],
    role_relationships: Dict[str, List[str]],
    inferred_gate_choice: str | None,
    reply_text: str,
) -> List[str]:
    resolved: List[str] = []
    for question in pending_questions:
        if reply_answers_question(
            question,
            merged_context=merged_context,
            role_relationships=role_relationships,
            inferred_gate_choice=inferred_gate_choice,
            reply_text=reply_text,
        ):
            resolved.append(question)
    return resolved


def reply_answers_question(
    question: str,
    *,
    merged_context: Dict[str, object],
    role_relationships: Dict[str, List[str]],
    inferred_gate_choice: str | None,
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
        return (
            len([role for role in normalized_roles if role]) >= 2
            and bool(role_relationships.get("outcome_owners") or has_responsibility_signal(reply_text))
        )

    if any(marker in normalized_question for marker in ["提出需求的人", "提出者"]):
        return bool(role_relationships.get("proposers"))
    if any(marker in normalized_question for marker in ["实际使用的人", "实际使用者", "平时是谁在具体操作"]):
        return bool(role_relationships.get("users")) or contains_any(
            lowered,
            ["前台", "店员", "运营", "用户", "专员", "医生", "管理者"],
        )
    if any(marker in normalized_question for marker in ["结果责任人", "对结果负责", "谁会对结果负责"]):
        return bool(role_relationships.get("outcome_owners")) or has_responsibility_signal(reply_text)

    if contains_any(normalized_question, ["流程", "环节", "真实过程", "怎么运行"]):
        return contains_any(lowered, ["流程", "手工", "线下", "列表", "路径", "步骤", "环节", "现在主要靠"])

    if contains_any(normalized_question, ["频率", "多久", "影响范围", "影响到什么结果", "基线数据"]):
        return contains_any(
            lowered,
            ["每天", "每周", "每月", "经常", "偶尔", "最近", "投诉", "影响", "到诊率", "发帖率", "%", "次"],
        ) or any(char.isdigit() for char in reply_text)

    if contains_any(normalized_question, ["为什么现在", "机会成本", "晚三个月", "时间窗口"]):
        return contains_any(
            lowered,
            ["现在", "最近", "本月", "这个月", "排期", "资源", "窗口", "机会成本", "来不及", "影响"],
        )

    if contains_any(normalized_question, ["非产品", "培训", "管理", "流程路径", "替代方案"]):
        return bool(inferred_gate_choice == "try-non-product-first") or contains_any(
            lowered,
            ["流程", "培训", "管理", "人工", "线下", "运营", "先试", "替代"],
        )

    if contains_any(normalized_question, ["成功指标", "护栏指标", "停止条件", "最小验证动作", "验证周期", "基线指标"]):
        return contains_any(
            lowered,
            ["指标", "成功", "失败", "停止", "验证", "基线", "观察", "周期", "到诊率", "转化", "留存", "%", "首帖率"],
        ) or any(char.isdigit() for char in reply_text)

    if contains_any(normalized_question, ["目标和约束是否一致", "角色关系", "目标差异"]):
        return bool(role_relationships.get("users")) and (
            bool(role_relationships.get("outcome_owners"))
            or contains_any(lowered, ["关注", "目标", "效率", "营收", "简单", "体验", "结果"])
        )

    return question_keyword_overlap(normalized_question, reply_text)


def question_keyword_overlap(question: str, reply_text: str) -> bool:
    keywords = [
        token
        for token in ["流程", "角色", "目标", "结果", "证据", "频率", "影响", "指标", "验证", "平台", "产品"]
        if token in question
    ]
    if not keywords:
        return False
    return sum(1 for token in keywords if token in reply_text) >= 1


def contains_any(text: str, items: List[str]) -> bool:
    return any(item in text for item in items)


def has_responsibility_signal(text: str) -> bool:
    return contains_any(text, ["负责", "结果", "店长", "管理者", "负责人", "老板", "核心医生"])


def _match_to_pending_question(candidate: str, pending_questions: List[str]) -> str:
    for question in pending_questions:
        if question_text_matches(candidate, question):
            return question
    return ""
