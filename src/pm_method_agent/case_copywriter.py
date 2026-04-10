from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional, Protocol

from pm_method_agent.llm_adapter import (
    LLMAdapter,
    LLMMessage,
    LLMRequest,
    OpenAICompatibleAdapter,
    load_openai_compatible_config_from_env,
)
from pm_method_agent.models import CaseState


@dataclass
class CaseCopyUpdate:
    normalized_summary: str = ""
    blocking_reason: str = ""
    next_actions: list[str] | None = None


class CaseCopywriter(Protocol):
    def enhance(self, case_state: CaseState) -> CaseCopyUpdate:
        ...


class LLMCaseCopywriter:
    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    def enhance(self, case_state: CaseState) -> CaseCopyUpdate:
        if case_state.output_kind not in {
            "continue-guidance-card",
            "stage-block-card",
            "decision-gate-card",
            "review-card",
        }:
            return CaseCopyUpdate()

        request = _build_copy_request(case_state)
        response = self._adapter.generate(request)
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError:
            return CaseCopyUpdate()
        return _normalize_copy_payload(payload)


def build_case_copywriter_from_env() -> Optional[CaseCopywriter]:
    if os.getenv("PMMA_LLM_COPYWRITER_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    config = load_openai_compatible_config_from_env()
    if config is None:
        return None
    return LLMCaseCopywriter(adapter=OpenAICompatibleAdapter(config=config))


def apply_case_copywriting(
    case_state: CaseState,
    copywriter: Optional[CaseCopywriter] = None,
) -> CaseState:
    active_copywriter = copywriter or build_case_copywriter_from_env()
    if active_copywriter is None:
        return case_state

    update = active_copywriter.enhance(case_state)
    if update.normalized_summary:
        case_state.normalized_summary = update.normalized_summary
    if update.blocking_reason:
        case_state.blocking_reason = update.blocking_reason
    if update.next_actions:
        case_state.next_actions = list(update.next_actions)
    if update.normalized_summary or update.blocking_reason or update.next_actions:
        case_state.metadata["copywriter"] = "llm"
    return case_state


def _build_copy_request(case_state: CaseState) -> LLMRequest:
    instruction = (
        "你是 PM Method Agent 的中文卡片文案增强器。"
        "你只能润色文案，不允许改变阶段、关口、结构和决策含义。"
        "请输出 JSON，字段仅允许：normalized_summary、blocking_reason、next_actions。"
        "normalized_summary 和 blocking_reason 各最多一句。"
        "next_actions 最多 5 条，每条一句。"
        "语气要求：自然、克制、像协作中的产品同事，不要报告腔，不要网梗，不要客服话术。"
        "优先写成用户一眼能接住的话，不要故作正式。"
        "尽量少用这些说法：当前、建议先、需要补充、问题描述已初步成型、继续推进、值得投入产品能力。"
        "可以参考这类改写："
        "把“问题描述已初步成型，但还需要补充更多证据和角色关系的细节”改成“方向已经差不多了，但还得把证据和角色关系补上”。"
        "把“当前先按非产品路径推进，建议先试流程、培训或管理方案”改成“这轮先按非产品路径看，先试流程、培训或管理方案”。"
        "把“当前还没有识别到你对这个决策关口的明确选择”改成“这轮还没看到你对这个关口的明确选择”。"
        "不要输出 JSON 以外的内容。"
    )
    payload = {
        "output_kind": case_state.output_kind,
        "stage": case_state.stage,
        "workflow_state": case_state.workflow_state,
        "raw_input": case_state.raw_input,
        "normalized_summary": case_state.normalized_summary,
        "blocking_reason": case_state.blocking_reason,
        "next_actions": case_state.next_actions[:5],
        "findings": [
            {
                "dimension": finding.dimension,
                "claim": finding.claim,
                "suggested_next_action": finding.suggested_next_action,
            }
            for finding in case_state.findings[:6]
        ],
        "decision_gates": [
            {
                "question": gate.question,
                "recommended_option": gate.recommended_option,
                "reason": gate.reason,
                "blocking": gate.blocking,
            }
            for gate in case_state.decision_gates[:3]
        ],
    }
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=instruction),
            LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ],
        response_format="json",
        metadata={"task": "case-copywriting"},
    )


def _normalize_copy_payload(payload: object) -> CaseCopyUpdate:
    if not isinstance(payload, dict):
        return CaseCopyUpdate()

    normalized_summary = ""
    if isinstance(payload.get("normalized_summary"), str):
        normalized_summary = _polish_copy_text(payload["normalized_summary"].strip())

    blocking_reason = ""
    if isinstance(payload.get("blocking_reason"), str):
        blocking_reason = _polish_copy_text(payload["blocking_reason"].strip())

    next_actions = None
    if isinstance(payload.get("next_actions"), list):
        next_actions = []
        for item in payload["next_actions"][:5]:
            if not isinstance(item, str):
                continue
            polished = _polish_copy_text(item.strip())
            if polished and polished not in next_actions:
                next_actions.append(polished)
        if not next_actions:
            next_actions = None

    return CaseCopyUpdate(
        normalized_summary=normalized_summary,
        blocking_reason=blocking_reason,
        next_actions=next_actions,
    )


def _polish_copy_text(text: str) -> str:
    polished = text.strip()
    if not polished:
        return ""

    replacements = [
        ("问题描述已初步成型", "方向已经差不多了"),
        ("输入接近问题描述", "方向已经差不多了"),
        ("输入已经接近问题描述了", "方向已经差不多了"),
        ("还需要补充", "还得补"),
        ("需要补充", "还得补"),
        ("建议先", "先"),
        ("当前先按", "这轮先按"),
        ("非产品路径推进", "非产品路径看"),
        ("当前还没有", "这轮还没"),
        ("当前更像", "这轮更像"),
        ("继续推进", "继续往下走"),
        ("可以继续做验证", "可以继续往验证走"),
    ]
    for source, target in replacements:
        polished = polished.replace(source, target)

    while "  " in polished:
        polished = polished.replace("  ", " ")
    return polished
