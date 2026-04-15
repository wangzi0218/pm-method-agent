from __future__ import annotations

import json
from typing import List

from pm_method_agent.models import AnalyzerFinding, CaseState, RuntimeSession, WorkspaceState
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


def build_case_runtime_payload(case_state: CaseState) -> dict:
    llm_runtime = case_state.metadata.get("llm_runtime")
    llm_enhancements = case_state.metadata.get("llm_enhancements", {})
    if not isinstance(llm_runtime, dict):
        llm_runtime = get_llm_runtime_status()
    if not isinstance(llm_enhancements, dict):
        llm_enhancements = {}
    fallback_components = _collect_llm_fallback_components(llm_enhancements)
    return {
        "summary": _runtime_summary(case_state),
        "llm_runtime": llm_runtime,
        "llm_enhancements": llm_enhancements,
        "fallback_components": fallback_components,
        "fallback_count": len(fallback_components),
        "fallback_active": bool(fallback_components),
    }


def build_case_history_payload(case_state: CaseState) -> dict:
    case_runtime = build_case_runtime_payload(case_state)
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
        "case_runtime": case_runtime,
        "llm_enhancements": case_runtime.get("llm_enhancements", {}),
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


def build_runtime_session_payload(runtime_session: RuntimeSession) -> dict:
    return runtime_session.to_dict()


def render_runtime_session(runtime_session: RuntimeSession, output_format: str = "markdown") -> str:
    payload = build_runtime_session_payload(runtime_session)
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if output_format != "markdown":
        raise ValueError("Unsupported format. Use 'markdown' or 'json'.")

    compression_state = payload.get("compression_state") or {}
    context_budget = payload.get("context_budget") or {}
    working_memory = payload.get("working_memory") or []
    summary_memory = payload.get("summary_memory") or []
    raw_history = payload.get("raw_history") or []
    last_terminal = payload.get("last_terminal_event") or {}

    lines: List[str] = []
    lines.append("# PM Method Agent Runtime Session")
    lines.append("")
    lines.append(f"- 会话编号：`{payload.get('session_id', '')}`")
    lines.append(f"- 工作区：`{payload.get('workspace_id', '')}`")
    lines.append(f"- 当前案例：`{payload.get('active_case_id', '') or '未设置'}`")
    lines.append(f"- 运行状态：`{payload.get('runtime_status', '') or 'idle'}`")
    lines.append(f"- 当前循环：`{payload.get('current_loop_state', '') or 'idle'}`")
    lines.append(f"- 轮次计数：`{payload.get('turn_count', 0)}`")
    lines.append(f"- 最近恢复点：`{payload.get('resume_from', '') or '无'}`")
    lines.append("")
    lines.append("## 上下文预算")
    lines.append(f"- 原始历史预算：`{context_budget.get('raw_history_budget', 0)}`")
    lines.append(f"- 工作记忆预算：`{context_budget.get('working_memory_budget', 0)}`")
    lines.append(f"- 摘要记忆预算：`{context_budget.get('summary_memory_budget', 0)}`")
    lines.append("")
    lines.append("## 压缩状态")
    lines.append(f"- 状态：`{compression_state.get('status', 'not-needed')}`")
    lines.append(f"- 已压缩轮次：`{compression_state.get('compressed_turns', 0)}`")
    lines.append(f"- 最近压缩到：`{compression_state.get('last_compression_turn', 0)}`")
    lines.append(f"- 原始历史保留：`{compression_state.get('raw_history_size', len(raw_history))}`")
    lines.append(f"- 工作记忆条目：`{compression_state.get('working_memory_size', len(working_memory))}`")
    lines.append(f"- 摘要记忆条目：`{compression_state.get('summary_memory_size', len(summary_memory))}`")
    if compression_state.get("last_summary_id"):
        lines.append(f"- 最近摘要编号：`{compression_state.get('last_summary_id')}`")
    lines.append("")
    lines.append("## 最近终止事件")
    if last_terminal:
        lines.append(f"- 终止语义：`{last_terminal.get('terminal_state', '')}`")
        lines.append(f"- 动作：`{last_terminal.get('action', '')}`")
        lines.append(f"- 输出类型：`{last_terminal.get('output_kind', '') or '无'}`")
        lines.append(f"- 工作流状态：`{last_terminal.get('workflow_state', '') or '无'}`")
    else:
        lines.append("- 暂无")
    lines.append("")
    lines.append("## 工作记忆")
    if working_memory:
        for item in working_memory:
            lines.append(
                f"- 第 {item.get('turn_count', '?')} 轮 / `{item.get('intent', '') or 'unknown'}` / "
                f"`{item.get('terminal_state', '') or 'unknown'}` / {item.get('message_preview', '') or '暂无'}"
            )
    else:
        lines.append("- 暂无")
    lines.append("")
    lines.append("## 摘要记忆")
    if summary_memory:
        for item in summary_memory:
            lines.append(
                f"- `{item.get('summary_id', '')}` / 第 {item.get('from_turn', '?')} 到 {item.get('to_turn', '?')} 轮 / "
                f"{item.get('turns', 0)} 轮"
            )
            highlights = item.get("highlights") or []
            if highlights:
                lines.append(f"  重点：{'；'.join(str(text) for text in highlights)}")
    else:
        lines.append("- 暂无")
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
            "approval_required_actions": list(runtime_policy.approval_required_actions),
            "auto_approve_actions": list(runtime_policy.auto_approve_actions),
            "auto_expire_approval_actions": list(runtime_policy.auto_expire_approval_actions),
            "manual_approval_only_actions": list(runtime_policy.manual_approval_only_actions),
            "command_allowlist_prefixes": list(runtime_policy.command_allowlist_prefixes),
            "blocked_command_patterns": list(runtime_policy.blocked_command_patterns),
            "approval_required_command_patterns": list(runtime_policy.approval_required_command_patterns),
            "allowed_read_roots": list(runtime_policy.allowed_read_roots),
            "blocked_read_paths": list(runtime_policy.blocked_read_paths),
            "approval_required_read_paths": list(runtime_policy.approval_required_read_paths),
            "allowed_write_roots": list(runtime_policy.allowed_write_roots),
            "blocked_write_paths": list(runtime_policy.blocked_write_paths),
            "approval_required_write_paths": list(runtime_policy.approval_required_write_paths),
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
        f"- 需要人工确认的动作：{_render_inline_list(runtime_policy_payload['approval_required_actions'])}"
    )
    lines.append(
        f"- 自动批准动作：{_render_inline_list(runtime_policy_payload['auto_approve_actions'])}"
    )
    lines.append(
        f"- 自动过期动作：{_render_inline_list(runtime_policy_payload['auto_expire_approval_actions'])}"
    )
    lines.append(
        f"- 必须人工处理的动作：{_render_inline_list(runtime_policy_payload['manual_approval_only_actions'])}"
    )
    lines.append(
        f"- 命令白名单前缀：{_render_inline_list(runtime_policy_payload['command_allowlist_prefixes'])}"
    )
    lines.append(
        f"- 禁用命令：{_render_inline_list(runtime_policy_payload['blocked_command_patterns'])}"
    )
    lines.append(
        f"- 需要人工确认的命令："
        f"{_render_inline_list(runtime_policy_payload['approval_required_command_patterns'])}"
    )
    lines.append(
        f"- 允许读取根目录：{_render_inline_list(runtime_policy_payload['allowed_read_roots'])}"
    )
    lines.append(
        f"- 禁用读取路径：{_render_inline_list(runtime_policy_payload['blocked_read_paths'])}"
    )
    lines.append(
        f"- 需要人工确认的读取路径："
        f"{_render_inline_list(runtime_policy_payload['approval_required_read_paths'])}"
    )
    lines.append(
        f"- 允许写入根目录：{_render_inline_list(runtime_policy_payload['allowed_write_roots'])}"
    )
    lines.append(
        f"- 禁用写入路径：{_render_inline_list(runtime_policy_payload['blocked_write_paths'])}"
    )
    lines.append(
        f"- 需要人工确认的写入路径："
        f"{_render_inline_list(runtime_policy_payload['approval_required_write_paths'])}"
    )
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
    lines.append("# PM Method Agent 分析卡")
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
    lines.append("## 我现在的判断")
    lines.append(case_state.normalized_summary or "暂无")
    lines.append("")
    lines.append("## 我主要看到这几个点")
    for finding in _collect_render_findings(case_state):
        _append_finding(lines, finding)
    lines.append("")
    lines.append("## 这一步还想先确认")
    _append_gate_items(lines, case_state)
    lines.append("")
    lines.append("## 更建议先做")
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
    fallback_components = _render_llm_fallback_components(history_payload.get("llm_enhancements", {}))
    if fallback_components:
        lines.append(f"- 最近模型回退：`{fallback_components}`")
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


def _render_llm_fallback_components(payload: object) -> str:
    return " / ".join(_collect_llm_fallback_components(payload))


def _collect_llm_fallback_components(payload: object) -> List[str]:
    if not isinstance(payload, dict):
        return []
    components: List[str] = []
    for component, item in payload.items():
        if not isinstance(item, dict) or not item.get("fallback_used"):
            continue
        rendered = str(component).strip()
        if rendered and rendered not in components:
            components.append(rendered)
    return components


def _render_context_question_card(case_state: CaseState) -> str:
    lines: List[str] = []
    lines.append("# PM Method Agent 场景补充卡")
    lines.append("")
    _append_case_id(lines, case_state)
    lines.append(f"- 当前阶段：`{_label_for(STAGE_LABELS, case_state.stage)}`")
    lines.append(f"- 增强模式：`{_runtime_summary(case_state)}`")
    lines.append("")
    lines.append("## 我现在的判断")
    lines.append(case_state.normalized_summary or "信息还不够，建议先补几项基础信息。")
    lines.append("")
    lines.append("## 为什么先补")
    lines.append(case_state.blocking_reason or "这几个信息会直接影响后面的判断口径。")
    lines.append("")
    lines.append("## 先补这几项")
    for question in case_state.pending_questions:
        lines.append(f"- {question}")
    lines.append("")
    lines.append("## 补完后我再继续")
    next_stage = case_state.metadata.get("next_stage", "problem-definition")
    lines.append(f"- 我会先继续到`{_label_for(STAGE_LABELS, str(next_stage))}`。")
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
    lines.append("## 我现在的判断")
    lines.append(case_state.normalized_summary or "当前阶段暂不建议继续推进。")
    lines.append("")
    lines.append("## 这一步先卡在这里")
    lines.append(case_state.blocking_reason or "当前条件还不够，先别急着往下走。")
    lines.append("")
    if case_state.findings:
        lines.append("## 我主要看到这几个点")
        for finding in case_state.findings:
            _append_finding(lines, finding)
        lines.append("")
    lines.append("## 继续前还想先确认")
    _append_gate_items(lines, case_state, empty_message="当前没有需要立刻拍板的决策点。")
    lines.append("")
    lines.append("## 更建议先做")
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
    lines.append("## 我先按这几个方向理解")
    for index, direction in enumerate(result.candidate_directions):
        prefix = "更像" if direction.direction_id == result.recommended_direction_id else "也可能是"
        rendered = f"{prefix}「{direction.label}」：{direction.summary}"
        if index > 0 and direction.assumptions:
            rendered = f"{rendered} {_render_pre_framing_assumption(direction)}"
        lines.append(f"- {rendered}")
    lines.append("")
    lines.append("## 现在更值得先补")
    for question in result.priority_questions:
        lines.append(f"- {question}")
    lines.append("")
    lines.append("## 如果先按这个方向继续")
    recommended = _find_recommended_direction(case_state)
    next_stage = case_state.metadata.get("next_stage", "problem-definition")
    lines.append(f"- 我会先按「{recommended}」往下看。")
    lines.append(f"- {_render_pre_framing_follow_up(str(next_stage))}")
    return "\n".join(lines)


def _render_pre_framing_assumption(direction) -> str:
    assumptions = [item.strip() for item in direction.assumptions if item.strip()]
    if not assumptions:
        return ""
    return f"我先留一个备选判断：{assumptions[0]}。"


def _render_pre_framing_follow_up(next_stage: str) -> str:
    if next_stage == "context-alignment":
        return "这轮补完后，我先把场景信息对齐，再继续往下看。"
    if next_stage == "problem-definition":
        return "这轮补完后，我再继续把问题本身收稳。"
    return f"这轮补完后，我再继续往`{_label_for(STAGE_LABELS, next_stage)}`走。"


def _label_for(mapping: dict, key: str) -> str:
    return mapping.get(key, key)


def _append_finding(lines: List[str], finding) -> None:
    claim = _polish_display_text(finding.claim)
    lines.append(f"- [{_label_for(DIMENSION_LABELS, finding.dimension)}] {claim}")
    compact = _should_render_finding_compact(finding)
    summary = _render_finding_strength_line(
        finding.evidence_level,
        finding.risk_if_wrong,
        compact=compact,
    )
    if summary:
        lines.append(f"  {summary}")
    if finding.evidence and not compact:
        evidence = _join_limited([_polish_display_text(item) for item in finding.evidence], limit=1)
        lines.append(f"  我看到的信号：{evidence}")
    if finding.unknowns:
        unknown_limit = 1 if compact else 2
        unknowns = _join_limited([_polish_display_text(item) for item in finding.unknowns], limit=unknown_limit)
        prefix = "  先顺手补：" if compact else "  还想补："
        lines.append(f"{prefix}{unknowns}")


def _collect_render_findings(case_state: CaseState) -> List[AnalyzerFinding]:
    findings = list(case_state.findings)
    compact_decision_facts = [
        item
        for item in findings
        if item.dimension == "decision-challenge" and _should_render_finding_compact(item)
    ]
    if len(compact_decision_facts) < 2:
        return findings

    merged_fact = AnalyzerFinding(
        dimension="decision-challenge",
        claim=_build_compact_decision_fact_claim(compact_decision_facts),
        claim_type="fact",
        evidence_level="medium",
        evidence=["场景基础信息中已标记当前存在多个需要一起看的场景前提。"],
        unknowns=_merge_finding_unknowns(compact_decision_facts),
        risk_if_wrong="medium",
        suggested_next_action="",
        owner="decision-challenge",
    )

    rendered: List[AnalyzerFinding] = []
    inserted = False
    for item in findings:
        if item in compact_decision_facts:
            if not inserted:
                rendered.append(merged_fact)
                inserted = True
            continue
        rendered.append(item)
    return rendered


def _build_compact_decision_fact_claim(findings: List[AnalyzerFinding]) -> str:
    clauses: List[str] = []
    for finding in findings:
        claim = _shorten_compact_decision_claim(_polish_display_text(finding.claim))
        if claim and claim not in clauses:
            clauses.append(claim)
    if not clauses:
        return "还有几个场景前提会直接影响后面的判断。"
    if len(clauses) == 1:
        return f"{clauses[0]}，这会直接影响后面的判断。"
    return f"还有几个场景前提会直接影响后面的判断：{'；'.join(clauses)}。"


def _merge_finding_unknowns(findings: List[AnalyzerFinding]) -> List[str]:
    merged: List[str] = []
    for finding in findings:
        for item in finding.unknowns:
            rendered = _polish_display_text(str(item).strip())
            if rendered and rendered not in merged:
                merged.append(rendered)
    return merged


def _shorten_compact_decision_claim(claim: str) -> str:
    shortened = claim.strip().strip("。")
    replacements = [
        ("这是企业产品场景，价值判断还要把组织流程、权限链和角色关系一起看", "这是企业产品场景"),
        ("现在主要是非桌面端场景，后面评估时还得把展示空间和操作打断成本一起算进去", "现在主要是非桌面端场景"),
    ]
    for source, target in replacements:
        shortened = shortened.replace(source, target)
    return shortened.strip("。")


def _should_render_finding_compact(finding) -> bool:
    if str(getattr(finding, "claim_type", "")) != "fact":
        return False
    evidence_items = list(getattr(finding, "evidence", []) or [])
    if not evidence_items:
        return False
    return all("场景基础信息中已标记" in str(item) for item in evidence_items)


def _render_finding_strength_line(evidence_level: str, risk_level: str, compact: bool = False) -> str:
    if compact:
        compact_map = {
            "low": "这条影响相对可控。",
            "medium": "这条会影响后面怎么判断，但不用单独放大。",
            "high": "这条会明显影响后面的判断口径。",
        }
        return compact_map.get(str(risk_level), "")
    evidence_map = {
        "none": "这条现在还没有明确证据，",
        "weak": "这条现在证据还比较弱，",
        "medium": "这条已经有一些依据，",
        "strong": "这条已经有比较扎实的依据，",
    }
    risk_map = {
        "low": "就算看偏了，影响也相对可控。",
        "medium": "如果看偏了，后面可能会多走一点弯路。",
        "high": "如果看偏了，后面很容易把力气花错地方。",
    }
    evidence_text = evidence_map.get(str(evidence_level), "")
    risk_text = risk_map.get(str(risk_level), "")
    if not evidence_text and not risk_text:
        return ""
    return f"{evidence_text}{risk_text}".strip()


def _append_unknowns(lines: List[str], case_state: CaseState) -> None:
    grouped_unknowns = _group_unknowns(_filter_unknowns_for_render(case_state))
    has_items = any(grouped_unknowns.get(group_name) for group_name in UNKNOWN_GROUP_ORDER)
    if not has_items:
        return
    lines.append("## 后面还值得补")
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


def _append_gate_items(lines: List[str], case_state: CaseState, empty_message: str = "这一步暂时没有额外确认项。") -> None:
    if not case_state.decision_gates:
        lines.append(f"- {empty_message}")
        return
    for gate in case_state.decision_gates:
        recommended_option = OPTION_LABELS.get(gate.recommended_option, gate.recommended_option)
        option_labels = [OPTION_LABELS.get(option, option) for option in gate.options]
        lines.append(f"- {_polish_gate_question(gate.question)}")
        lines.append(f"  倾向：{recommended_option}{'；这一步会卡住' if gate.blocking else ''}")
        lines.append(f"  可选：{' / '.join(option_labels)}")
        lines.append(f"  这么判断：{_polish_gate_reason(gate.reason)}")


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


def _filter_unknowns_for_render(case_state: CaseState) -> List[str]:
    rendered_actions = _collect_next_actions(case_state, limit=8)
    filtered: List[str] = []
    for item in case_state.unknowns:
        normalized = _polish_display_text(str(item).strip())
        if not normalized:
            continue
        if _is_unknown_covered_by_actions(normalized, rendered_actions):
            continue
        if normalized not in filtered:
            filtered.append(normalized)
    return filtered


def _is_unknown_covered_by_actions(unknown: str, actions: List[str]) -> bool:
    compact_unknown = _semantic_compact_text(unknown)
    for action in actions:
        compact_action = _semantic_compact_text(action)
        if compact_unknown and (compact_unknown in compact_action or compact_action in compact_unknown):
            return True
        if _action_unknown_semantically_overlap(unknown, action):
            return True
    return False


def _action_unknown_semantically_overlap(unknown: str, action: str) -> bool:
    semantic_pairs = [
        (["当前流程", "流程是怎么运行"], ["现状流程", "流程"]),
        (["替代方案", "绕路方式"], ["替代做法", "四类路径", "非产品路径", "粗比较"]),
        (["目标和约束是否一致", "目标是否一致", "协作边界"], ["目标差异", "角色关系", "协作边界"]),
        (["时间窗口", "机会成本"], ["为什么现在做", "机会成本"]),
        (["产品类型", "企业产品", "消费者产品", "内部产品"], ["产品类型"]),
        (["主要交付和使用平台", "主要使用平台"], ["主要平台"]),
        (["成功指标", "护栏指标", "停止条件"], ["成功指标", "护栏指标", "停止条件"]),
        (["最小验证动作", "基线指标"], ["最小验证动作", "真实案例", "可证伪假设"]),
        (["非产品解法"], ["非产品路径", "四类路径", "粗比较"]),
        (["关键角色", "提出需求的人", "实际使用的人", "最终业务结果"], ["核心角色", "角色关系", "提出者", "使用者", "结果责任人"]),
    ]
    for unknown_markers, action_markers in semantic_pairs:
        if any(marker in unknown for marker in unknown_markers) and any(marker in action for marker in action_markers):
            return True
    return False


def _semantic_compact_text(text: str) -> str:
    compact = text.strip()
    replacements = [
        ("当前", ""),
        ("是否", ""),
        ("是什么", ""),
        ("怎么运行的", ""),
        ("是什么", ""),
        ("并和", ""),
        ("一起看", ""),
        ("先", ""),
        ("至少", ""),
        ("。", ""),
        ("，", ""),
        ("、", ""),
        (" ", ""),
    ]
    for source, target in replacements:
        compact = compact.replace(source, target)
    return compact


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
    visible_items = [item.strip() for item in items if item.strip()][:limit]
    return "；".join(visible_items)


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
