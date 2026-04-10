from __future__ import annotations

import json
from typing import List

from pm_method_agent.models import CaseState, WorkspaceState
from pm_method_agent.prompting import PromptComposition
from pm_method_agent.rule_loader import LoadedRuleSet
from pm_method_agent.runtime_config import get_llm_runtime_status
from pm_method_agent.runtime_policy import RuntimePolicy

STAGE_LABELS = {
    "intake": "输入接收",
    "pre-framing": "前置收敛",
    "context-alignment": "场景对齐",
    "problem-definition": "问题定义",
    "decision-challenge": "决策挑战",
    "validation-design": "验证设计",
    "blocked": "已阻塞",
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

RESOLUTION_KIND_LABELS = {
    "accepted-recommendation": "采纳建议",
    "overrode-recommendation": "覆盖建议",
}

OUTPUT_KIND_LABELS = {
    "review-card": "审查卡",
    "context-question-card": "场景补充卡",
    "stage-block-card": "阶段阻塞卡",
    "decision-gate-card": "决策关口卡",
    "continue-guidance-card": "继续卡",
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


def build_case_history_payload(case_state: CaseState) -> dict:
    return {
        "case_id": case_state.case_id,
        "workflow_state": case_state.workflow_state,
        "stage": case_state.stage,
        "conversation_turns": case_state.metadata.get("conversation_turns", []),
        "stage_history": case_state.metadata.get("stage_history", []),
        "answered_questions": case_state.metadata.get("answered_questions", []),
        "resolved_gates": case_state.metadata.get("resolved_gates", []),
        "last_resume_stage": case_state.metadata.get("last_resume_stage"),
        "last_gate_choice": case_state.metadata.get("last_gate_choice"),
        "last_reply_parser": case_state.metadata.get("last_reply_parser"),
    }


def render_case_history(case_state: CaseState, output_format: str = "markdown") -> str:
    history_payload = build_case_history_payload(case_state)
    if output_format == "json":
        return json.dumps(history_payload, ensure_ascii=False, indent=2)
    if output_format != "markdown":
        raise ValueError("Unsupported format. Use 'markdown' or 'json'.")
    return _render_history_markdown(history_payload)


def build_workspace_cases_payload(workspace_state: WorkspaceState, recent_cases: list[CaseState]) -> dict:
    return {
        "workspace_id": workspace_state.workspace_id,
        "active_case_id": workspace_state.active_case_id,
        "active_project_profile_id": workspace_state.active_project_profile_id,
        "recent_cases": [
            {
                "case_id": case.case_id,
                "stage": case.stage,
                "workflow_state": case.workflow_state,
                "output_kind": case.output_kind,
                "summary": case.normalized_summary or _short_text(case.raw_input, limit=36),
            }
            for case in recent_cases
        ],
    }


def render_workspace_overview(workspace_state: WorkspaceState, recent_cases: list[CaseState]) -> str:
    payload = build_workspace_cases_payload(workspace_state, recent_cases)
    lines: List[str] = []
    lines.append("# PM Method Agent 工作区")
    lines.append("")
    lines.append(f"- 工作区：`{payload['workspace_id']}`")
    active_case_id = str(payload.get("active_case_id") or "").strip()
    lines.append(f"- 当前案例：`{active_case_id or '未设置'}`")
    if payload.get("active_project_profile_id"):
        lines.append(f"- 当前项目背景：`{payload['active_project_profile_id']}`")
    lines.append("")
    lines.append("## 最近案例")
    recent_items = payload.get("recent_cases", [])
    if not recent_items:
        lines.append("- 暂无")
        return "\n".join(lines)
    for index, item in enumerate(recent_items, start=1):
        stage = _label_for(STAGE_LABELS, str(item.get("stage", "")))
        workflow_state = _label_for(STAGE_LABELS, str(item.get("workflow_state", "")))
        is_active = "（当前）" if item.get("case_id") == active_case_id else ""
        lines.append(f"- {index}. `{item.get('case_id')}` {is_active} / {stage} / {workflow_state}")
        lines.append(f"  判断：{item.get('summary', '')}")
    return "\n".join(lines)


def build_rule_diagnostics_payload(
    *,
    base_dir: str,
    rule_set: LoadedRuleSet,
    prompt_composition: PromptComposition,
    runtime_policy: RuntimePolicy,
    show_prompt: bool = False,
) -> dict:
    return {
        "base_dir": base_dir,
        "rule_sources": list(prompt_composition.rule_sources or rule_set.sources),
        "behavior_rules": list(prompt_composition.behavior_rules),
        "tool_constraints": list(prompt_composition.tool_constraints),
        "output_discipline": list(prompt_composition.output_discipline),
        "project_instructions": list(prompt_composition.project_instructions),
        "custom_append": list(prompt_composition.custom_append),
        "runtime_policy": {
            "blocked_intents": list(runtime_policy.blocked_intents),
            "blocked_actions": list(runtime_policy.blocked_actions),
            "allow_new_cases": runtime_policy.allow_new_cases,
            "allow_case_switching": runtime_policy.allow_case_switching,
            "allow_project_profile_updates": runtime_policy.allow_project_profile_updates,
            "sources": list(runtime_policy.sources),
        },
        "prompt_layers": prompt_composition.metadata(),
        "prompt_preview": prompt_composition.render() if show_prompt else "",
    }


def render_rule_diagnostics(
    *,
    base_dir: str,
    rule_set: LoadedRuleSet,
    prompt_composition: PromptComposition,
    runtime_policy: RuntimePolicy,
    output_format: str = "markdown",
    show_prompt: bool = False,
) -> str:
    payload = build_rule_diagnostics_payload(
        base_dir=base_dir,
        rule_set=rule_set,
        prompt_composition=prompt_composition,
        runtime_policy=runtime_policy,
        show_prompt=show_prompt,
    )
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if output_format != "markdown":
        raise ValueError("Unsupported format. Use 'markdown' or 'json'.")

    lines: List[str] = []
    lines.append("# PM Method Agent 规则概览")
    lines.append("")
    lines.append(f"- 生效目录：`{payload['base_dir']}`")
    lines.append(f"- 规则来源：`{len(payload['rule_sources'])}`")
    lines.append("")
    lines.append("## 规则来源")
    if payload["rule_sources"]:
        for source in payload["rule_sources"]:
            lines.append(f"- {source}")
    else:
        lines.append("- 暂无")
    lines.append("")
    _append_rule_section(lines, "项目规则", payload["project_instructions"])
    lines.append("")
    _append_rule_section(lines, "行为规则", payload["behavior_rules"])
    lines.append("")
    _append_rule_section(lines, "工具约束", payload["tool_constraints"])
    lines.append("")
    _append_rule_section(lines, "输出纪律", payload["output_discipline"])
    lines.append("")
    _append_rule_section(lines, "追加要求", payload["custom_append"])
    lines.append("")
    lines.append("## 运行时策略")
    runtime_policy_payload = payload["runtime_policy"]
    lines.append(f"- 禁用意图：{_render_inline_list(runtime_policy_payload['blocked_intents'])}")
    lines.append(f"- 禁用动作：{_render_inline_list(runtime_policy_payload['blocked_actions'])}")
    lines.append(
        f"- 允许新建案例：{'是' if runtime_policy_payload['allow_new_cases'] else '否'}"
    )
    lines.append(
        f"- 允许切换案例：{'是' if runtime_policy_payload['allow_case_switching'] else '否'}"
    )
    lines.append(
        f"- 允许更新项目背景：{'是' if runtime_policy_payload['allow_project_profile_updates'] else '否'}"
    )
    if show_prompt and payload["prompt_preview"]:
        lines.append("")
        lines.append("## Prompt 预览")
        lines.append("```text")
        lines.append(payload["prompt_preview"])
        lines.append("```")
    return "\n".join(lines)


def _render_markdown(case_state: CaseState) -> str:
    if case_state.output_kind == "context-question-card":
        return _render_context_question_card(case_state)
    if case_state.output_kind == "continue-guidance-card":
        return _render_continue_guidance_card(case_state)
    if case_state.output_kind in {"stage-block-card", "decision-gate-card"}:
        return _render_block_card(case_state)

    lines: List[str] = []
    lines.append("# PM Method Agent 审查卡")
    lines.append("")
    _append_case_id(lines, case_state)
    lines.append(f"- 当前阶段：`{_label_for(STAGE_LABELS, case_state.stage)}`")
    lines.append(f"- 运行状态：`{_label_for(STAGE_LABELS, case_state.workflow_state)}`")
    lines.append(f"- 增强模式：`{_runtime_summary(case_state)}`")
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
        _append_role_relationships(lines, case_state)
    else:
        lines.append("- 未提供")
    lines.append("")
    lines.append("## 输入")
    lines.append(case_state.raw_input)
    lines.append("")
    lines.append("## 当前判断")
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
                f"- {_polish_gate_question(gate.question)} "
                f"(建议={recommended_option}，阻塞={'是' if gate.blocking else '否'})"
            )
            lines.append(f"  选项：{' / '.join(option_labels)}")
            lines.append(f"  原因：{_polish_gate_reason(gate.reason)}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 建议先做")
    for action in _collect_next_actions(case_state):
        lines.append(f"- {action}")
    lines.append("")
    _append_unknowns(lines, case_state)
    return "\n".join(lines)


def _append_rule_section(lines: List[str], title: str, items: List[str]) -> None:
    lines.append(f"## {title}")
    if items:
        for item in items:
            lines.append(f"- {item}")
        return
    lines.append("- 暂无")


def _render_inline_list(items: List[str]) -> str:
    if not items:
        return "无"
    return " / ".join(f"`{item}`" for item in items)


def _render_history_markdown(history_payload: dict) -> str:
    lines: List[str] = []
    lines.append("# PM Method Agent 会话历史")
    lines.append("")
    lines.append(f"- 案例编号：`{history_payload['case_id']}`")
    lines.append(f"- 当前阶段：`{_label_for(STAGE_LABELS, history_payload['stage'])}`")
    lines.append(f"- 当前状态：`{_label_for(STAGE_LABELS, history_payload['workflow_state'])}`")
    if history_payload.get("last_resume_stage"):
        lines.append(
            f"- 最近恢复阶段：`{_label_for(STAGE_LABELS, str(history_payload['last_resume_stage']))}`"
        )
    if history_payload.get("last_gate_choice"):
        lines.append(
            f"- 最近关口选择：`{OPTION_LABELS.get(history_payload['last_gate_choice'], history_payload['last_gate_choice'])}`"
        )
    if history_payload.get("last_reply_parser"):
        lines.append(f"- 最近解释方式：`{history_payload['last_reply_parser']}`")
    lines.append("")

    lines.append("## 会话回合")
    for turn in history_payload.get("conversation_turns", []):
        lines.append(f"- [{turn.get('turn_kind', 'turn')}] {turn.get('role', 'unknown')}：{turn.get('content', '')}")
    if not history_payload.get("conversation_turns"):
        lines.append("- 暂无")
    lines.append("")

    lines.append("## 阶段变更")
    for item in history_payload.get("stage_history", []):
        from_stage = _label_for(STAGE_LABELS, str(item.get("from_stage")))
        to_stage = _label_for(STAGE_LABELS, str(item.get("to_stage")))
        resume_stage = _label_for(STAGE_LABELS, str(item.get("resume_stage", "-")))
        gate_choice = item.get("gate_choice")
        gate_note = ""
        if gate_choice:
            gate_note = f"，选择={OPTION_LABELS.get(gate_choice, gate_choice)}"
        lines.append(
            f"- {from_stage} -> {to_stage} "
            f"(触发={item.get('trigger', 'unknown')}，恢复点={resume_stage}{gate_note})"
        )
    if not history_payload.get("stage_history"):
        lines.append("- 暂无")
    lines.append("")

    lines.append("## 已回答问题")
    for item in history_payload.get("answered_questions", []):
        lines.append(f"- {item}")
    if not history_payload.get("answered_questions"):
        lines.append("- 暂无")
    lines.append("")

    lines.append("## 已处理关口")
    for item in history_payload.get("resolved_gates", []):
        choice = item.get("user_choice")
        choice_label = OPTION_LABELS.get(choice, choice or "未识别")
        resolution_kind = item.get("resolution_kind")
        resolution_label = RESOLUTION_KIND_LABELS.get(resolution_kind, resolution_kind or "未标记")
        lines.append(
            f"- {item.get('gate_id')} / {item.get('stage')} / 选择={choice_label} / 处理={resolution_label}"
        )
    if not history_payload.get("resolved_gates"):
        lines.append("- 暂无")
    return "\n".join(lines)


def _render_context_question_card(case_state: CaseState) -> str:
    lines: List[str] = []
    lines.append("# PM Method Agent 场景补充卡")
    lines.append("")
    _append_case_id(lines, case_state)
    lines.append(f"- 当前阶段：`{_label_for(STAGE_LABELS, case_state.stage)}`")
    lines.append(f"- 增强模式：`{_runtime_summary(case_state)}`")
    lines.append("")
    lines.append("## 当前判断")
    lines.append(case_state.normalized_summary or "信息还不够，建议先补几项基础信息。")
    lines.append("")
    lines.append("## 先补原因")
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
    lines.append(f"- 增强模式：`{_runtime_summary(case_state)}`")
    lines.append("")
    lines.append("## 当前判断")
    lines.append(case_state.normalized_summary or "当前阶段暂不建议继续推进。")
    lines.append("")
    lines.append("## 当前卡点")
    lines.append(case_state.blocking_reason or "当前条件还不够，先别急着往下走。")
    lines.append("")
    if case_state.findings:
        lines.append("## 关键判断")
        for finding in case_state.findings:
            _append_finding(lines, finding)
        lines.append("")
    lines.append("## 继续前确认")
    if case_state.decision_gates:
        for gate in case_state.decision_gates:
            recommended_option = OPTION_LABELS.get(gate.recommended_option, gate.recommended_option)
            option_labels = [OPTION_LABELS.get(option, option) for option in gate.options]
            lines.append(
                f"- {_polish_gate_question(gate.question)} "
                f"(建议={recommended_option}，阻塞={'是' if gate.blocking else '否'})"
            )
            lines.append(f"  选项：{' / '.join(option_labels)}")
            lines.append(f"  原因：{_polish_gate_reason(gate.reason)}")
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


def _render_continue_guidance_card(case_state: CaseState) -> str:
    if case_state.metadata.get("continue_card_kind") == "pre-framing" and case_state.pre_framing_result:
        return _render_pre_framing_card(case_state)

    lines: List[str] = []
    lines.append("# PM Method Agent 继续卡")
    lines.append("")
    _append_case_id(lines, case_state)
    lines.append(f"- 增强模式：`{_runtime_summary(case_state)}`")
    lines.append(f"- 当前重点：`{_continue_card_focus(case_state)}`")
    lines.append("")
    lines.append("## 当前进展")
    lines.append(case_state.normalized_summary or "基础背景已经补上，可以开始往问题本身收拢了。")
    lines.append("")
    lines.append("## 已对齐")
    if case_state.context_profile:
        for key, value in case_state.context_profile.items():
            label = CONTEXT_KEY_LABELS.get(key, key)
            rendered = _render_context_value(key, value)
            lines.append(f"- {label}：{rendered}")
        _append_role_relationships(lines, case_state)
    else:
        lines.append("- 还没有明确的基础背景。")
    lines.append("")
    lines.append("## 接下来更值得补")
    for item in _collect_background_follow_up(case_state):
        lines.append(f"- {item}")
    return "\n".join(lines)


def _render_pre_framing_card(case_state: CaseState) -> str:
    result = case_state.pre_framing_result
    assert result is not None

    lines: List[str] = []
    lines.append("# PM Method Agent 继续卡")
    lines.append("")
    _append_case_id(lines, case_state)
    lines.append(f"- 当前阶段：`{_label_for(STAGE_LABELS, case_state.stage)}`")
    lines.append(f"- 增强模式：`{_runtime_summary(case_state)}`")
    lines.append("")
    lines.append("## 当前判断")
    lines.append(case_state.normalized_summary or "先把这句话收一收，再继续推进。")
    lines.append("")
    lines.append("## 更像哪几类问题")
    for direction in result.candidate_directions:
        recommended = "，更建议先看" if direction.direction_id == result.recommended_direction_id else ""
        lines.append(f"- {direction.label}{recommended}")
        lines.append(f"  说明：{direction.summary}")
        if direction.assumptions:
            lines.append(f"  假设：{_join_limited(direction.assumptions, limit=2)}")
    lines.append("")
    lines.append("## 先确认这几件事")
    for question in result.priority_questions:
        lines.append(f"- {question}")
    lines.append("")
    lines.append("## 更建议先沿哪条继续")
    recommended = _find_recommended_direction(case_state)
    lines.append(f"- {recommended}")
    lines.append("")
    lines.append("## 补完后继续")
    next_stage = case_state.metadata.get("next_stage", "problem-definition")
    lines.append(f"- `{_label_for(STAGE_LABELS, str(next_stage))}`")
    return "\n".join(lines)


def _label_for(mapping: dict, key: str) -> str:
    return mapping.get(key, key)


def _append_finding(lines: List[str], finding) -> None:
    claim = _polish_display_text(finding.claim)
    lines.append(
        f"- [{_label_for(DIMENSION_LABELS, finding.dimension)}] {claim} "
        f"(证据={_label_for(EVIDENCE_LEVEL_LABELS, finding.evidence_level)}，"
        f"风险={_label_for(RISK_LABELS, finding.risk_if_wrong)})"
    )
    if finding.evidence:
        evidence = _join_limited([_polish_display_text(item) for item in finding.evidence], limit=1)
        lines.append(f"  信号：{evidence}")
    if finding.unknowns:
        unknowns = _join_limited([_polish_display_text(item) for item in finding.unknowns], limit=2)
        lines.append(f"  要补：{unknowns}")


def _append_unknowns(lines: List[str], case_state: CaseState) -> None:
    lines.append("## 建议补充")
    grouped_unknowns = _group_unknowns(case_state.unknowns)
    for group_name in UNKNOWN_GROUP_ORDER:
        items = grouped_unknowns.get(group_name, [])
        if not items:
            continue
        lines.append(f"### {group_name}")
        for item in items:
            lines.append(f"- {_polish_display_text(item)}")


def _append_role_relationships(lines: List[str], case_state: CaseState) -> None:
    relationships = case_state.metadata.get("role_relationships", {})
    if not isinstance(relationships, dict):
        return
    relation_labels = {
        "proposers": "提出者",
        "users": "实际使用者",
        "outcome_owners": "结果责任人",
    }
    for key, label in relation_labels.items():
        items = relationships.get(key, [])
        if isinstance(items, list) and items:
            lines.append(f"- {label}：{'，'.join(str(item) for item in items)}")


def _collect_next_actions(case_state: CaseState, limit: int = 5) -> List[str]:
    actions: List[str] = []
    for candidate in case_state.next_actions:
        normalized = _polish_display_text(candidate.strip())
        if not normalized:
            continue
        if any(normalized in existing or existing in normalized for existing in actions):
            continue
        actions.append(normalized)
        if len(actions) >= limit:
            return actions

    for finding in case_state.findings:
        normalized = _polish_display_text(finding.suggested_next_action.strip())
        if not normalized:
            continue
        if any(normalized in existing or existing in normalized for existing in actions):
            continue
        actions.append(normalized)
        if len(actions) >= limit:
            break
    return actions


def _polish_display_text(text: str) -> str:
    polished = text.strip()
    if not polished:
        return ""

    replacements = [
        ("输入已经接近问题描述了", "方向已经差不多了"),
        ("输入接近问题描述", "方向已经差不多了"),
        ("问题描述已初步成型", "方向已经差不多了"),
        ("建议先把", "先把"),
        ("建议先", "先"),
        ("建议后面", "后面"),
        ("当前主要是", "现在主要是"),
        ("当前还没有", "现在还没有"),
        ("当前没有", "现在没有"),
        ("当前更像", "这轮更像"),
        ("后面的判断容易跑偏", "后面判断容易跑偏"),
        ("后面的判断风险会偏高", "后面判断风险会偏高"),
        ("后面评估时还要把", "后面评估时还得把"),
        ("后面评估时，把", "后面评估时，把"),
        ("继续往下看", "继续往下走"),
        ("补充现状流程、失败案例和现有替代做法", "补上现状流程、失败案例和现有替代做法"),
        ("补充为什么现在做，以及延后会损失什么", "补上为什么现在做，以及延后会损失什么"),
        ("补充角色关系，并区分提出者、使用者和结果责任人", "补上角色关系，并区分提出者、使用者和结果责任人"),
        ("先把这句话拆成“现象 / 解释 / 方案假设”三层", "先把这句话拆成“现象 / 解释 / 方案假设”三层来看"),
        ("补看", "再看"),
    ]
    for source, target in replacements:
        polished = polished.replace(source, target)

    while "  " in polished:
        polished = polished.replace("  ", " ")
    return polished


def _polish_gate_question(question: str) -> str:
    polished = question.strip()
    replacements = [
        ("问题是否已经定义清楚，可以进入方案讨论？", "按现在的信息，能不能直接进入方案讨论？"),
        ("基于现有信息，当前值得投入产品能力吗？", "按现在的信息，这件事要不要继续往产品方案走？"),
    ]
    for source, target in replacements:
        polished = polished.replace(source, target)
    return polished


def _polish_gate_reason(reason: str) -> str:
    polished = _polish_display_text(reason.strip())
    replacements = [
        ("输入里已经混入方案，现状证据也还不够。", "输入里已经混进方案了，现状证据也还不够。"),
        ("基础场景信息已经具备，当前也没有更优的非产品路径信号，可以继续做验证。", "基础场景信息已经够用了，也没看到更优的非产品路径，可以继续往验证走。"),
        ("当前更像组织流程类问题，先看非产品路径会更稳一些。", "这轮更像组织流程类问题，先看非产品路径会更稳。"),
        ("当前紧迫性不足，而且资源也偏紧，先暂缓会更稳妥。", "现在紧迫性还不够，资源也偏紧，先暂缓会更稳。"),
        ("基础场景信息还不够，先别急着直接进入产品化。", "基础场景信息还不够，先别急着往产品方案走。"),
        ("已有信号表明非产品路径已经试过且效果不稳，可以继续往验证设计走。", "已经有信号说明非产品路径试过了，而且效果不稳，可以继续往验证设计走。"),
    ]
    for source, target in replacements:
        polished = polished.replace(source, target)
    return polished


def _short_text(text: str, limit: int = 40) -> str:
    normalized = " ".join(text.strip().split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def _collect_background_follow_up(case_state: CaseState) -> List[str]:
    relationships = case_state.metadata.get("role_relationships", {})
    suggestions: List[str] = []
    if not isinstance(relationships, dict):
        relationships = {}

    if not relationships.get("proposers"):
        suggestions.append("这次是谁先把这个问题提出来的，还可以再说明确一点。")
    if not relationships.get("users"):
        suggestions.append("这件事平时是谁在具体操作，和提出需求的人是不是同一类人？")
    if not relationships.get("outcome_owners"):
        suggestions.append("最后谁会对结果负责，还可以再明确一点。")
    suggestions.extend(
        [
            "当前流程是怎么跑的，最好补一段真实过程。",
            "这个问题最近大概多久出现一次，影响到什么结果。",
            "如果这轮先不做，最现实的代价是什么。",
        ]
    )

    deduped: List[str] = []
    for item in suggestions:
        if item not in deduped:
            deduped.append(item)
    return deduped[:4]


def _continue_card_focus(case_state: CaseState) -> str:
    if case_state.metadata.get("continue_card_kind") == "pre-framing":
        return "先收理解方向"
    relationships = case_state.metadata.get("role_relationships", {})
    if isinstance(relationships, dict):
        if not relationships.get("users"):
            return "补操作角色"
        if not relationships.get("outcome_owners"):
            return "补责任关系"
    return "补问题细节"


def _find_recommended_direction(case_state: CaseState) -> str:
    result = case_state.pre_framing_result
    if result is None:
        return "先补最关键的背景和现状。"
    for direction in result.candidate_directions:
        if direction.direction_id == result.recommended_direction_id:
            return direction.label
    if result.candidate_directions:
        return result.candidate_directions[0].label
    return "先补最关键的背景和现状。"


def _runtime_summary(case_state: CaseState) -> str:
    runtime = case_state.metadata.get("llm_runtime")
    if isinstance(runtime, dict):
        summary = runtime.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    fallback_runtime = get_llm_runtime_status()
    summary = fallback_runtime.get("summary", "本地规则")
    return str(summary)


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
