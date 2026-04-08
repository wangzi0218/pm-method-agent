from __future__ import annotations

from pm_method_agent.models import AnalyzerFinding, CaseState, DecisionGate


SOLUTION_KEYWORDS = [
    "增加",
    "新增",
    "加一个",
    "功能",
    "弹窗",
    "按钮",
    "页面",
    "看板",
    "提醒",
]

STAKEHOLDER_HINTS = {
    "前台": "前台/操作人员",
    "患者": "患者",
    "老板": "老板/经营者",
    "管理": "管理者",
    "医生": "医生",
    "护士": "护士",
    "运营": "运营人员",
}


def analyze_problem_framing(case_state: CaseState) -> None:
    text = case_state.raw_input.strip()
    stakeholders = _guess_stakeholders(text)
    is_solution_led = any(keyword in text for keyword in SOLUTION_KEYWORDS)
    context_profile = case_state.context_profile

    case_state.stage = "problem-definition"
    case_state.normalized_summary = _build_summary(text, is_solution_led, context_profile)

    evidence = []
    if is_solution_led:
        evidence.append("输入中直接出现了明显的方案词汇，说明当前表达偏方案导向。")
    evidence.append("当前原始输入已经提供了一个待分析的问题场景。")
    if context_profile:
        evidence.append("已经提供了部分产品与场景基础信息，可以减少错误语境下的判断。")
    case_state.extend_evidence(evidence)

    unknowns = [
        "当前流程是怎么运行的",
        "问题发生的频率和影响范围",
        "当前是否已有替代方案或绕路方式",
    ]
    if not context_profile.get("business_model"):
        unknowns.append("当前产品属于企业产品、消费者产品还是内部产品")
    if not context_profile.get("primary_platform"):
        unknowns.append("当前主要使用平台是桌面端、移动端、小程序还是多端")
    if stakeholders:
        unknowns.append("不同关键角色的目标和约束是否一致")
    case_state.extend_unknowns(unknowns)

    if is_solution_led:
        case_state.add_finding(
            AnalyzerFinding(
                dimension="problem-framing",
                claim="当前输入已经带出方案，问题本身还没有单独说清。",
                claim_type="inference",
                evidence_level="weak",
                evidence=[
                    "输入里已经出现功能或界面层表达。",
                    "现状问题链路还没有展开。",
                ],
                unknowns=[
                    "现象层到底发生了什么",
                    "为什么现在会发生",
                ],
                risk_if_wrong="high",
                suggested_next_action="先改写成“现象 / 解释 / 方案假设”三层。",
                owner="problem-framing",
            )
        )

    stakeholder_claim = "关键角色还没有说清。"
    stakeholder_evidence = ["当前输入没有展开受影响对象和责任关系。"]
    stakeholder_level = "weak"
    if stakeholders:
        stakeholder_claim = "已能看到部分角色，但目标和责任边界还不清。"
        stakeholder_evidence = [f"输入中显式或隐式提到了：{'、'.join(stakeholders)}。"]
        stakeholder_level = "weak"

    case_state.add_finding(
        AnalyzerFinding(
            dimension="problem-framing",
            claim=stakeholder_claim,
            claim_type="inference",
            evidence_level=stakeholder_level,
            evidence=stakeholder_evidence,
            unknowns=[
                "谁是提出需求的人",
                "谁是实际使用的人",
                "谁承担最终业务结果",
            ],
            risk_if_wrong="medium",
            suggested_next_action="补充角色关系，并区分提出者、使用者和结果责任人。",
            owner="problem-framing",
        )
    )

    if not context_profile.get("business_model") or not context_profile.get("primary_platform"):
        case_state.add_finding(
            AnalyzerFinding(
                dimension="problem-framing",
                claim="场景基础信息还不够，后面的判断容易失真。",
                claim_type="missing-information",
                evidence_level="none",
                evidence=["产品类型或主要平台还没有补齐。"],
                unknowns=[
                    "这是企业产品、消费者产品还是内部产品",
                    "主要交付和使用平台是什么",
                ],
                risk_if_wrong="high",
                suggested_next_action="先补齐最小场景信息，再继续看价值和方案。",
                human_decision_needed=True,
                owner="problem-framing",
            )
        )

    next_actions = [
        "把当前输入拆成现象、解释、方案假设三层。",
        "补充现状流程、失败案例和现有替代做法。",
        "标出核心角色，以及他们的目标差异。",
    ]
    if not context_profile.get("business_model") or not context_profile.get("primary_platform"):
        next_actions.insert(0, "先补齐最小场景信息，至少包括产品类型、主要平台和关键用户角色。")
    case_state.extend_next_actions(next_actions)

    gate_needed = is_solution_led or len(text) < 30
    if gate_needed:
        gate_blocking = len(text) < 30 or not context_profile.get("business_model") or not context_profile.get("primary_platform")
        case_state.add_gate(
            DecisionGate(
                gate_id=f"G-{len(case_state.decision_gates) + 1:03d}",
                stage="problem-definition",
                question="问题是否已经定义清楚，可以进入方案讨论？",
                options=["continue-to-solution", "collect-more-evidence", "defer"],
                recommended_option="collect-more-evidence",
                reason="输入里已经混入方案，现状证据也还不够。",
                blocking=gate_blocking,
            )
        )


def _guess_stakeholders(text: str) -> list[str]:
    result = []
    for keyword, label in STAKEHOLDER_HINTS.items():
        if keyword in text and label not in result:
            result.append(label)
    return result


def _build_summary(text: str, is_solution_led: bool, context_profile: dict[str, object]) -> str:
    has_context = bool(context_profile)
    if is_solution_led:
        if not has_context:
            return "输入已经带出方案，场景信息也还不够，建议先把问题收拢。"
        return "输入已经带出方案，建议先把问题本身收拢。"
    if len(text) < 20:
        if not has_context:
            return "输入信息偏少，场景信息也不够，当前更像待展开的问题线索。"
        return "输入信息偏少，当前更像待展开的问题线索。"
    if not has_context:
        return "输入更接近问题描述，但场景信息还不够，后续判断风险偏高。"
    return "输入更接近问题描述，但还要补证据、角色关系和现状流程。"
