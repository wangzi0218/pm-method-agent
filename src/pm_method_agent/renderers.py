from __future__ import annotations

import json
from typing import List

from pm_method_agent.models import CaseState

STAGE_LABELS = {
    "intake": "输入接收",
    "context-alignment": "场景对齐",
    "problem-definition": "问题定义",
    "decision-challenge": "决策挑战",
    "validation-design": "验证设计",
    "done": "已完成",
    "deferred": "已暂缓",
}

MODE_LABELS = {
    "problem-framing": "问题定义",
    "decision-challenge": "决策挑战",
    "validation-design": "验证设计",
}

DIMENSION_LABELS = {
    "problem-framing": "问题定义",
    "root-cause-and-alternatives": "根因与替代路径",
    "decision-challenge": "决策挑战",
    "validation-design": "验证设计",
}

EVIDENCE_LEVEL_LABELS = {
    "none": "无",
    "weak": "弱",
    "medium": "中",
    "strong": "强",
}

RISK_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}

CONTEXT_KEY_LABELS = {
    "business_model": "产品类型",
    "primary_platform": "主要平台",
    "distribution_channel": "分发渠道",
    "product_domain": "业务领域",
    "target_user_roles": "关键用户角色",
    "constraints": "限制条件",
}

CONTEXT_VALUE_LABELS = {
    "business_model": {
        "tob": "企业产品",
        "toc": "消费者产品",
        "internal": "内部产品",
    },
    "primary_platform": {
        "pc": "桌面端",
        "mobile-web": "移动网页",
        "native-app": "原生应用",
        "mini-program": "小程序",
        "multi-platform": "多端",
    },
}

OPTION_LABELS = {
    "continue-to-solution": "继续进入方案阶段",
    "collect-more-evidence": "补充证据后再评估",
    "defer": "暂缓",
    "productize-now": "进入产品化阶段",
    "try-non-product-first": "优先评估非产品路径",
}

OUTPUT_KIND_LABELS = {
    "review-card": "审查卡",
    "context-question-card": "场景补充卡",
    "stage-block-card": "阶段阻塞卡",
    "decision-gate-card": "决策关口卡",
}

UNKNOWN_GROUP_ORDER = [
    "场景信息",
    "现状与证据",
    "决策与验证",
    "其他",
]


def render_case_state(case_state: CaseState, output_format: str = "markdown") -> str:
    if output_format == "json":
        return json.dumps(case_state.to_dict(), ensure_ascii=False, indent=2)
    if output_format != "markdown":
        raise ValueError("Unsupported format. Use 'markdown' or 'json'.")
    return _render_markdown(case_state)


def _render_markdown(case_state: CaseState) -> str:
    if case_state.output_kind == "context-question-card":
        return _render_context_question_card(case_state)
    if case_state.output_kind in {"stage-block-card", "decision-gate-card"}:
        return _render_block_card(case_state)

    lines: List[str] = []
    lines.append("# PM Method Agent 审查卡")
    lines.append("")
    _append_case_id(lines, case_state)
    lines.append(f"- 当前阶段：`{_label_for(STAGE_LABELS, case_state.stage)}`")
    lines.append(f"- 运行状态：`{_label_for(STAGE_LABELS, case_state.workflow_state)}`")
    selected_modes = case_state.metadata.get("selected_modes", [])
    selected_mode_labels = [_label_for(MODE_LABELS, mode) for mode in selected_modes]
    lines.append(f"- 执行模块：`{'、'.join(selected_mode_labels)}`")
    lines.append("")
    lines.append("## 基础信息")
    if case_state.context_profile:
        for key, value in case_state.context_profile.items():
            label = CONTEXT_KEY_LABELS.get(key, key)
            rendered = _render_context_value(key, value)
            lines.append(f"- {label}：{rendered}")
    else:
        lines.append("- 未提供")
    lines.append("")
    lines.append("## 输入")
    lines.append(case_state.raw_input)
    lines.append("")
    lines.append("## 初步判断")
    lines.append(case_state.normalized_summary or "暂无")
    lines.append("")
    lines.append("## 关键判断")
    for finding in case_state.findings:
        _append_finding(lines, finding)
    lines.append("")
    lines.append("## 需要确认")
    if case_state.decision_gates:
        for gate in case_state.decision_gates:
            recommended_option = OPTION_LABELS.get(gate.recommended_option, gate.recommended_option)
            option_labels = [OPTION_LABELS.get(option, option) for option in gate.options]
            lines.append(
                f"- {gate.question} "
                f"(建议={recommended_option}，阻塞={'是' if gate.blocking else '否'})"
            )
            lines.append(f"  选项：{' / '.join(option_labels)}")
            lines.append(f"  原因：{gate.reason}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 先做这几步")
    for action in _collect_next_actions(case_state):
        lines.append(f"- {action}")
    lines.append("")
    _append_unknowns(lines, case_state)
    return "\n".join(lines)


def _render_context_question_card(case_state: CaseState) -> str:
    lines: List[str] = []
    lines.append("# PM Method Agent 场景补充卡")
    lines.append("")
    _append_case_id(lines, case_state)
    lines.append(f"- 当前阶段：`{_label_for(STAGE_LABELS, case_state.stage)}`")
    lines.append("")
    lines.append("## 当前判断")
    lines.append(case_state.normalized_summary or "信息还不够，建议先补几项基础信息。")
    lines.append("")
    lines.append("## 为什么先补")
    lines.append(case_state.blocking_reason or "这几个信息会直接影响后面的判断口径。")
    lines.append("")
    lines.append("## 先补这几项")
    for question in case_state.pending_questions:
        lines.append(f"- {question}")
    lines.append("")
    lines.append("## 补完后继续")
    next_stage = case_state.metadata.get("next_stage", "problem-definition")
    lines.append(f"- `{_label_for(STAGE_LABELS, str(next_stage))}`")
    lines.append("")
    lines.append("## 下一步")
    for action in _collect_next_actions(case_state, limit=3):
        lines.append(f"- {action}")
    return "\n".join(lines)


def _render_block_card(case_state: CaseState) -> str:
    title = "决策关口卡" if case_state.output_kind == "decision-gate-card" else "阶段阻塞卡"
    lines: List[str] = []
    lines.append(f"# PM Method Agent {title}")
    lines.append("")
    _append_case_id(lines, case_state)
    lines.append(f"- 当前阶段：`{_label_for(STAGE_LABELS, case_state.stage)}`")
    lines.append("")
    lines.append("## 当前判断")
    lines.append(case_state.normalized_summary or "当前阶段暂不建议继续推进。")
    lines.append("")
    lines.append("## 为什么先停在这里")
    lines.append(case_state.blocking_reason or "当前条件还不够，先别急着往下走。")
    lines.append("")
    if case_state.findings:
        lines.append("## 关键判断")
        for finding in case_state.findings:
            _append_finding(lines, finding)
        lines.append("")
    lines.append("## 继续前先确认")
    if case_state.decision_gates:
        for gate in case_state.decision_gates:
            recommended_option = OPTION_LABELS.get(gate.recommended_option, gate.recommended_option)
            option_labels = [OPTION_LABELS.get(option, option) for option in gate.options]
            lines.append(
                f"- {gate.question} "
                f"(建议={recommended_option}，阻塞={'是' if gate.blocking else '否'})"
            )
            lines.append(f"  选项：{' / '.join(option_labels)}")
            lines.append(f"  原因：{gate.reason}")
    else:
        lines.append("- 当前没有需要立即拍板的决策点。")
    lines.append("")
    lines.append("## 下一步")
    for action in _collect_next_actions(case_state):
        lines.append(f"- {action}")
    if case_state.unknowns:
        lines.append("")
        _append_unknowns(lines, case_state)
    return "\n".join(lines)


def _label_for(mapping: dict, key: str) -> str:
    return mapping.get(key, key)


def _append_finding(lines: List[str], finding) -> None:
    lines.append(
        f"- [{_label_for(DIMENSION_LABELS, finding.dimension)}] {finding.claim} "
        f"(证据={_label_for(EVIDENCE_LEVEL_LABELS, finding.evidence_level)}，"
        f"风险={_label_for(RISK_LABELS, finding.risk_if_wrong)})"
    )
    if finding.evidence:
        lines.append(f"  信号：{_join_limited(finding.evidence, limit=1)}")
    if finding.unknowns:
        lines.append(f"  要补：{_join_limited(finding.unknowns, limit=2)}")


def _append_unknowns(lines: List[str], case_state: CaseState) -> None:
    lines.append("## 待补信息")
    grouped_unknowns = _group_unknowns(case_state.unknowns)
    for group_name in UNKNOWN_GROUP_ORDER:
        items = grouped_unknowns.get(group_name, [])
        if not items:
            continue
        lines.append(f"### {group_name}")
        for item in items:
            lines.append(f"- {item}")


def _collect_next_actions(case_state: CaseState, limit: int = 5) -> List[str]:
    actions: List[str] = []
    for candidate in case_state.next_actions:
        normalized = candidate.strip()
        if not normalized:
            continue
        if any(normalized in existing or existing in normalized for existing in actions):
            continue
        actions.append(normalized)
        if len(actions) >= limit:
            return actions

    for finding in case_state.findings:
        normalized = finding.suggested_next_action.strip()
        if not normalized:
            continue
        if any(normalized in existing or existing in normalized for existing in actions):
            continue
        actions.append(normalized)
        if len(actions) >= limit:
            break
    return actions


def _group_unknowns(items: List[str]) -> dict[str, List[str]]:
    grouped = {group_name: [] for group_name in UNKNOWN_GROUP_ORDER}
    for item in items:
        group_name = _classify_unknown(item)
        if item not in grouped[group_name]:
            grouped[group_name].append(item)
    return grouped


def _classify_unknown(item: str) -> str:
    if any(keyword in item for keyword in ["时间窗口", "机会成本", "非产品", "成功指标", "停止条件", "验证", "损失"]):
        return "决策与验证"
    if any(keyword in item for keyword in ["产品", "平台", "角色", "采购方", "使用方", "管理方"]):
        return "场景信息"
    if any(keyword in item for keyword in ["流程", "频率", "范围", "案例", "基线", "数据", "现状", "绕路", "替代方案"]):
        return "现状与证据"
    return "其他"


def _join_limited(items: List[str], limit: int) -> str:
    visible_items = items[:limit]
    rendered = "；".join(visible_items)
    if len(items) > limit:
        rendered = f"{rendered}；另有 {len(items) - limit} 项"
    return rendered


def _append_case_id(lines: List[str], case_state: CaseState) -> None:
    if case_state.metadata.get("show_case_id"):
        lines.append(f"- 案例编号：`{case_state.case_id}`")


def _render_context_value(key: str, value: object) -> str:
    if isinstance(value, list):
        return "，".join(_render_context_value(key, item) for item in value)
    if isinstance(value, str):
        key_mapping = CONTEXT_VALUE_LABELS.get(key, {})
        return key_mapping.get(value, value)
    return str(value)
