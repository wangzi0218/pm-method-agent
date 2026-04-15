from __future__ import annotations

from pm_method_agent.models import AnalyzerFinding, CaseState


def analyze_validation_design(case_state: CaseState) -> None:
    text = case_state.raw_input.strip()
    case_state.stage = "validation-design"
    base_text = text
    for marker in [
        "\n\n这轮补到的场景背景：",
        "\n\n这轮补到的现状和证据：",
        "\n\n这轮补到的判断倾向：",
        "\n\n这轮补到的约束条件：",
        "\n\n这轮顺手补充：",
        "\n\n补充场景信息：",
        "\n\n补充现状证据：",
        "\n\n补充决策表达：",
        "\n\n补充限制条件：",
        "\n\n其他补充：",
        "\n\n补充信息：",
    ]:
        if marker in base_text:
            base_text = base_text.split(marker, 1)[0].strip()
            break

    focus_text = _summarize_validation_focus(base_text)
    hypothesis = f"可以先按这个假设去验证：如果解决“{focus_text}”背后的关键阻塞，核心行为指标会改善。"
    falsification = "如果现状数据并不支持问题成立，或非产品手段已能低成本解决，这条产品方向就应降级。"
    min_validation = "先收集 3 到 5 个真实案例，再设计最小验证动作。"

    case_state.add_finding(
        AnalyzerFinding(
            dimension="validation-design",
            claim=hypothesis,
            claim_type="option",
            evidence_level="weak",
            evidence=["这个假设目前主要来自输入本身，客观材料还不够。"],
            unknowns=[
                "当前基线指标是什么",
                "最小验证动作要观察什么变化",
            ],
            risk_if_wrong="medium",
            suggested_next_action=min_validation,
            owner="validation-design",
        )
    )

    case_state.add_finding(
        AnalyzerFinding(
            dimension="validation-design",
            claim="在往方案走之前，先把成功指标、护栏指标和停止条件说清。",
            claim_type="challenge",
            evidence_level="medium",
            evidence=["如果没有事前约定的判断标准，后面就很难判断这件事还值不值得继续做。"],
            unknowns=[
                "成功指标是什么",
                "失败或停止条件是什么",
            ],
            risk_if_wrong="high",
            suggested_next_action="至少先补 1 个成功指标、1 个护栏指标和 1 个停止条件。",
            owner="validation-design",
        )
    )

    case_state.extend_unknowns(
        [
            "当前的基线数据是多少",
            "验证周期多长才足够判断",
        ]
    )
    case_state.extend_next_actions(
        [
            min_validation,
            "把需求改写成可证伪假设，并写清什么证据会推翻它。",
            "补充成功指标、护栏指标和停止条件。",
        ]
    )
    case_state.metadata["falsifiable_hypothesis"] = hypothesis
    case_state.metadata["falsification_signal"] = falsification


def _summarize_validation_focus(text: str) -> str:
    normalized = " ".join(text.split()).strip("。！？!? ")
    if len(normalized) <= 36:
        return normalized
    candidate_clauses = [item.strip() for item in normalized.replace("。", "，").split("，") if item.strip()]
    focus_keywords = [
        "漏",
        "提醒",
        "发帖",
        "转化",
        "留存",
        "审批",
        "跟进",
        "复诊",
        "预约",
        "影响",
        "卡在",
        "没发出",
        "没完成",
        "问题",
    ]
    context_keywords = [
        "这是一个",
        "属于",
        "产品",
        "app",
        "App",
        "网页端",
        "小程序",
        "通过网页端",
        "主要通过",
        "主要使用",
    ]
    relationship_keywords = [
        "提出",
        "提出来",
        "在操作",
        "使用者",
        "对结果负责",
        "负责结果",
    ]
    for clause in candidate_clauses:
        if any(keyword in clause for keyword in focus_keywords):
            return clause
    for clause in candidate_clauses:
        if any(keyword in clause for keyword in context_keywords):
            continue
        if any(keyword in clause for keyword in relationship_keywords):
            continue
        if 8 <= len(clause) <= 28:
            return clause
    if candidate_clauses:
        return "当前这件事"
    return f"{normalized[:32].rstrip()}..."
