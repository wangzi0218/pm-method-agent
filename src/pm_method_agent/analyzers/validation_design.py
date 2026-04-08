from __future__ import annotations

from pm_method_agent.models import AnalyzerFinding, CaseState


def analyze_validation_design(case_state: CaseState) -> None:
    text = case_state.raw_input.strip()
    case_state.stage = "validation-design"
    base_text = text
    for marker in [
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

    hypothesis = f"可先验证这个假设：如果解决“{base_text}”背后的关键阻塞，核心行为指标会改善。"
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
            claim="进入方案前，先把成功指标、护栏指标和停止条件定下来。",
            claim_type="challenge",
            evidence_level="medium",
            evidence=["如果没有事前约定的判断标准，后面就很难判断值不值得继续投。"],
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
