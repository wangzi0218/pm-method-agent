from __future__ import annotations

from pm_method_agent.models import AnalyzerFinding, CaseState, DecisionGate


URGENT_HINTS = ["马上", "尽快", "紧急", "本月", "本季度", "立刻"]
LOW_PRIORITY_HINTS = [
    "nice to have",
    "nice-to-have",
    "不用现在做",
    "不急着做",
    "不着急",
    "以后再说",
    "先放放",
    "资源比较紧张",
    "资源紧张",
    "资源有限",
    "不一定有资源",
    "没那么重要",
]
ORG_HINTS = ["培训", "流程", "规范", "SOP", "激励", "考核", "权限"]
NON_PRODUCT_ATTEMPT_HINTS = [
    "已经试过",
    "已试过",
    "试过培训",
    "试过流程",
    "试过提醒",
    "流程提醒",
    "培训提醒",
    "效果不稳定",
    "效果回落",
    "没有稳定解决",
]


def analyze_decision_challenge(case_state: CaseState) -> None:
    text = case_state.raw_input.strip()
    context_profile = case_state.context_profile
    case_state.stage = "decision-challenge"
    has_min_context = bool(context_profile.get("business_model")) and bool(context_profile.get("primary_platform"))
    has_org_hint = any(keyword in text for keyword in ORG_HINTS)
    non_product_already_tried = any(keyword in text for keyword in NON_PRODUCT_ATTEMPT_HINTS)
    has_low_priority_hint = any(keyword in text for keyword in LOW_PRIORITY_HINTS)

    why_now_level = "weak"
    why_now_claim = "为什么是现在做，这一点还不够清楚。"
    why_now_evidence = ["当前没有明确时间窗口或机会成本说明。"]
    if has_low_priority_hint:
        why_now_level = "medium"
        why_now_claim = "当前更像可以延后处理的事项，紧迫性还不够强。"
        why_now_evidence = ["输入里已经出现了资源受限、优先级不高或可以暂缓的信号。"]
    elif any(keyword in text for keyword in URGENT_HINTS):
        why_now_level = "medium"
        why_now_claim = "输入里已经有时机信号，但还要判断这是真窗口，还是临时性的紧急感。"
        why_now_evidence = ["输入中出现了和时效或优先级相关的表达。"]

    case_state.add_finding(
        AnalyzerFinding(
            dimension="decision-challenge",
            claim=why_now_claim,
            claim_type="challenge",
            evidence_level=why_now_level,
            evidence=why_now_evidence,
            unknowns=[
                "如果晚三个月做，会损失什么",
                "当前机会成本是什么",
            ],
            risk_if_wrong="high",
            suggested_next_action="补充为什么现在做，以及延后会损失什么。",
            owner="decision-challenge",
        )
    )

    non_product_level = "weak"
    non_product_claim = "现在还不能直接判断一定要做产品，流程、培训、管理等路径最好一起比较。"
    non_product_evidence = ["当前还没有排除流程、培训或管理等路径。"]
    non_product_unknowns = [
        "不改产品能否先解决 60%",
        "不同解法的实施成本和响应速度差异",
    ]
    non_product_action = "把产品和非产品路径放在一起做一轮粗比较。"
    if non_product_already_tried:
        non_product_level = "medium"
        non_product_claim = "已经有信号表明非产品路径试过了，但还要确认失败原因和覆盖范围。"
        non_product_evidence = ["输入中已经出现“已试过流程、培训或提醒，但效果不稳定”的线索。"]
        non_product_unknowns = [
            "已经试过哪些非产品路径",
            "为什么这些路径没有稳定解决问题",
        ]
        non_product_action = "补看已尝试路径的覆盖范围、持续性和失败原因。"
    elif has_org_hint:
        non_product_level = "medium"
        non_product_evidence = ["输入中已经出现流程、规范或权限相关线索。"]

    case_state.add_finding(
        AnalyzerFinding(
            dimension="decision-challenge",
            claim=non_product_claim,
            claim_type="challenge",
            evidence_level=non_product_level,
            evidence=non_product_evidence,
            unknowns=non_product_unknowns,
            risk_if_wrong="high",
            suggested_next_action=non_product_action,
            owner="decision-challenge",
        )
    )

    if context_profile.get("business_model") == "tob":
        case_state.add_finding(
            AnalyzerFinding(
                dimension="decision-challenge",
                claim="这是企业产品场景，价值判断还要把组织流程、权限链和角色关系一起看。",
                claim_type="fact",
                evidence_level="medium",
                evidence=["场景基础信息中已标记当前产品属于企业产品。"],
                unknowns=["采购方、使用方、管理方是否一致"],
                risk_if_wrong="medium",
                suggested_next_action="补看组织侧收益、执行成本和责任分配影响。",
                owner="decision-challenge",
            )
        )
    if context_profile.get("primary_platform") in {"mobile-web", "native-app", "mini-program"}:
        case_state.add_finding(
            AnalyzerFinding(
                dimension="decision-challenge",
                claim="当前主要是非桌面端场景，后面评估时还要把展示空间和操作打断成本一起算进去。",
                claim_type="fact",
                evidence_level="medium",
                evidence=["场景基础信息中已标记当前主要平台为非桌面端。"],
                unknowns=["当前关键操作是否适合在受限屏幕中完成"],
                risk_if_wrong="medium",
                suggested_next_action="后面评估时，把信息密度、流程长度和中断成本一起看。",
                owner="decision-challenge",
            )
        )

    case_state.extend_unknowns(
        [
            "是否真有明确时间窗口",
            "是否存在更低成本的非产品解法",
        ]
    )
    case_state.extend_next_actions(
        [
            "补充为什么现在做，并和机会成本一起看。",
            (
                "补看已尝试非产品路径的覆盖范围和失败原因。"
                if non_product_already_tried
                else "列出产品、流程、培训、运营四类路径，先做粗比较。"
            ),
        ]
    )

    if not has_min_context:
        recommended_option = "try-non-product-first"
        gate_reason = "基础场景信息还不够，先别急着直接进入产品化。"
        gate_blocking = True
    elif has_low_priority_hint:
        recommended_option = "defer"
        gate_reason = "当前紧迫性不足，而且资源也偏紧，先暂缓会更稳妥。"
        gate_blocking = True
    elif non_product_already_tried:
        recommended_option = "productize-now"
        gate_reason = "已有信号表明非产品路径已经试过且效果不稳，可以继续往验证设计走。"
        gate_blocking = False
    elif has_org_hint:
        recommended_option = "try-non-product-first"
        gate_reason = "当前更像组织流程类问题，先看非产品路径会更稳一些。"
        gate_blocking = True
    else:
        recommended_option = "productize-now"
        gate_reason = "基础场景信息已经具备，当前也没有更优的非产品路径信号，可以继续做验证。"
        gate_blocking = False

    case_state.add_gate(
        DecisionGate(
            gate_id=f"G-{len(case_state.decision_gates) + 1:03d}",
            stage="decision-challenge",
            question="基于现有信息，当前值得投入产品能力吗？",
            options=["productize-now", "try-non-product-first", "defer"],
            recommended_option=recommended_option,
            reason=gate_reason,
            blocking=gate_blocking,
        )
    )
