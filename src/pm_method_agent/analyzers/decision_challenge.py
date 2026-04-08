from __future__ import annotations

from pm_method_agent.models import AnalyzerFinding, CaseState, DecisionGate


URGENT_HINTS = ["马上", "尽快", "紧急", "本月", "本季度", "立刻"]
ORG_HINTS = ["培训", "流程", "规范", "SOP", "激励", "考核", "权限"]


def analyze_decision_challenge(case_state: CaseState) -> None:
    text = case_state.raw_input.strip()
    context_profile = case_state.context_profile
    case_state.stage = "decision-challenge"
    has_min_context = bool(context_profile.get("business_model")) and bool(context_profile.get("primary_platform"))
    has_org_hint = any(keyword in text for keyword in ORG_HINTS)

    why_now_level = "weak"
    why_now_claim = "现在做的理由还不够清。"
    why_now_evidence = ["当前没有明确时间窗口或机会成本说明。"]
    if any(keyword in text for keyword in URGENT_HINTS):
        why_now_level = "medium"
        why_now_claim = "输入里已经出现时机信号，但还要判断是真窗口还是情绪性紧急。"
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
    non_product_evidence = ["当前还没有排除流程、培训或管理等路径。"]
    if has_org_hint:
        non_product_level = "medium"
        non_product_evidence = ["输入中已经出现流程、规范或权限相关线索。"]

    case_state.add_finding(
        AnalyzerFinding(
            dimension="decision-challenge",
            claim="还不能证明一定要做产品，流程、培训、管理等路径也要一起比较。",
            claim_type="challenge",
            evidence_level=non_product_level,
            evidence=non_product_evidence,
            unknowns=[
                "不改产品能否先解决 60%",
                "不同解法的实施成本和响应速度差异",
            ],
            risk_if_wrong="high",
            suggested_next_action="把产品和非产品路径放在一起做一轮粗比较。",
            owner="decision-challenge",
        )
    )

    if context_profile.get("business_model") == "tob":
        case_state.add_finding(
            AnalyzerFinding(
                dimension="decision-challenge",
                claim="这是企业产品场景，价值判断还要看组织流程、权限链和角色关系。",
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
                claim="当前不是桌面端，后面评估还要把展示空间和操作打断成本算进去。",
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
            "列出产品、流程、培训、运营四类路径，先做粗比较。",
        ]
    )

    case_state.add_gate(
        DecisionGate(
            gate_id=f"G-{len(case_state.decision_gates) + 1:03d}",
            stage="decision-challenge",
            question="基于现有信息，当前值得投入产品能力吗？",
            options=["productize-now", "try-non-product-first", "defer"],
            recommended_option="try-non-product-first" if has_org_hint or not has_min_context else "productize-now",
            reason=(
                "现在做的理由和解法比较都还不够，先看非产品路径更稳。"
                if has_org_hint or not has_min_context
                else "基础场景信息已经具备，当前也没有更优的非产品路径信号，可以继续验证。"
            ),
            blocking=has_org_hint or not has_min_context,
        )
    )
