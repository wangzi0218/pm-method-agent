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
from pm_method_agent.prompting import build_prompt_composition


FOLLOW_UP_DISPLAY_FOCUS_KEY = "follow_up_display_focus"
FOLLOW_UP_DISPLAY_REASON_KEY = "follow_up_display_reason"
FOLLOW_UP_DISPLAY_QUESTIONS_KEY = "follow_up_display_questions"


@dataclass
class FollowUpCopyUpdate:
    focus_text: str = ""
    reason_text: str = ""
    display_questions: list[str] | None = None
    enhancer_name: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""


class FollowUpCopywriter(Protocol):
    def enhance(self, case_state: CaseState) -> FollowUpCopyUpdate:
        ...


class LLMFollowUpCopywriter:
    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    def enhance(self, case_state: CaseState) -> FollowUpCopyUpdate:
        if case_state.output_kind not in {"continue-guidance-card", "context-question-card"}:
            return FollowUpCopyUpdate()

        request = _build_follow_up_request(case_state)
        try:
            response = self._adapter.generate(request)
            payload = json.loads(response.content)
        except Exception as exc:
            return FollowUpCopyUpdate(
                enhancer_name="llm-fallback",
                fallback_used=True,
                fallback_reason=_render_fallback_reason(exc),
            )
        return _normalize_follow_up_payload(payload, case_state.pending_questions)


def build_follow_up_copywriter_from_env() -> Optional[FollowUpCopywriter]:
    if os.getenv("PMMA_LLM_FOLLOW_UP_COPYWRITER_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    config = load_openai_compatible_config_from_env()
    if config is None:
        return None
    return LLMFollowUpCopywriter(adapter=OpenAICompatibleAdapter(config=config))


def apply_follow_up_copywriting(
    case_state: CaseState,
    copywriter: Optional[FollowUpCopywriter] = None,
) -> CaseState:
    active_copywriter = copywriter or build_follow_up_copywriter_from_env()
    if active_copywriter is None:
        return case_state

    update = active_copywriter.enhance(case_state)
    if update.focus_text:
        case_state.metadata[FOLLOW_UP_DISPLAY_FOCUS_KEY] = update.focus_text
    if update.reason_text:
        case_state.metadata[FOLLOW_UP_DISPLAY_REASON_KEY] = update.reason_text
    if update.display_questions:
        case_state.metadata[FOLLOW_UP_DISPLAY_QUESTIONS_KEY] = list(update.display_questions)
    if update.enhancer_name:
        case_state.metadata["follow_up_copywriter"] = update.enhancer_name
        _record_llm_enhancement(
            case_state,
            component="follow-up-copywriter",
            engine=update.enhancer_name,
            fallback_used=update.fallback_used,
            fallback_reason=update.fallback_reason,
        )
    return case_state


def _build_follow_up_request(case_state: CaseState) -> LLMRequest:
    prompt = build_prompt_composition(
        identity="你是 PM Method Agent 的继续追问文案增强器，负责把继续卡和补充卡里的追问表达得更自然。",
        agent_role="你只能润色追问焦点、追问理由和展示问题，不允许改变阶段、关口、问题家族和主线判断。",
        behavior_rules=[
            "语气要像一起推进问题判断的产品同事，自然、克制、直接，不要汇报腔，不要客服腔。",
            "优先让用户一眼看懂“这轮先收什么”和“为什么先收这个”。",
            "追问句子要短，尽量像真实对话，不要把三件事硬挤进一句话。",
        ],
        tool_constraints=[
            "不能新增新的问题家族，不能改动问题顺序，不能改变原本的推进方向。",
            "如果原始问题偏结构化，你只能把它改得更顺口，不能换成别的问题。",
        ],
        output_discipline=[
            "必须输出 JSON，不要输出 JSON 以外的内容。",
            "字段仅允许：focus_text、reason_text、display_questions。",
            "focus_text 和 reason_text 各最多一句。",
            "display_questions 最多 3 条，且数量不能超过输入里的 pending_questions。",
        ],
        custom_append=[
            "可以把“先把场景对齐”改成“这轮先把场景说清”。",
            "可以把“这一步还有卡点，先补最影响推进的信息会更稳”改成“这一步还卡着，先补最影响判断的信息会更稳”。",
            "可以把“谁提出需求、谁使用产品、谁承担最终结果”改成更顺口的问法，但不能改变原意。",
        ],
        task_instruction="请在不改变问题家族和推进方向的前提下，润色当前追问表达。",
    )
    payload = {
        "output_kind": case_state.output_kind,
        "stage": case_state.stage,
        "workflow_state": case_state.workflow_state,
        "raw_input": case_state.raw_input,
        "normalized_summary": case_state.normalized_summary,
        "focus_text": str(case_state.metadata.get("follow_up_focus", "")).strip(),
        "reason_text": str(case_state.metadata.get("follow_up_reason", "")).strip(),
        "pending_questions": list(case_state.pending_questions[:3]),
        "context_profile": case_state.context_profile,
        "latest_note": _latest_note(case_state),
    }
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=prompt.render()),
            LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ],
        response_format="json",
        metadata={
            "task": "follow-up-copywriting",
            "prompt_layers": prompt.metadata(),
        },
    )


def _normalize_follow_up_payload(payload: object, original_questions: list[str]) -> FollowUpCopyUpdate:
    if not isinstance(payload, dict):
        return FollowUpCopyUpdate()

    focus_text = ""
    if isinstance(payload.get("focus_text"), str):
        focus_text = _polish_text(payload["focus_text"].strip())

    reason_text = ""
    if isinstance(payload.get("reason_text"), str):
        reason_text = _polish_text(payload["reason_text"].strip())

    display_questions = _normalize_display_questions(payload.get("display_questions"), original_questions)
    return FollowUpCopyUpdate(
        focus_text=focus_text,
        reason_text=reason_text,
        display_questions=display_questions,
        enhancer_name="llm",
    )


def _normalize_display_questions(payload: object, original_questions: list[str]) -> list[str] | None:
    if not original_questions:
        return None

    normalized: list[str] = []
    if isinstance(payload, list):
        for item in payload[: len(original_questions)]:
            if not isinstance(item, str):
                continue
            polished = _polish_text(item.strip())
            if polished and polished not in normalized:
                normalized.append(polished)

    for item in original_questions[:3]:
        polished = _polish_text(str(item).strip())
        if polished and polished not in normalized:
            normalized.append(polished)
        if len(normalized) >= min(len(original_questions), 3):
            break

    return normalized[: min(len(original_questions), 3)] or None


def _latest_note(case_state: CaseState) -> str:
    raw_buckets = case_state.metadata.get("session_note_buckets", {})
    if not isinstance(raw_buckets, dict):
        return ""
    for bucket_key in ["evidence_notes", "context_notes", "decision_notes", "constraint_notes", "other_notes"]:
        notes = raw_buckets.get(bucket_key, [])
        if not isinstance(notes, list):
            continue
        for item in reversed(notes):
            rendered = str(item).strip()
            if rendered:
                return rendered
    return ""


def _polish_text(text: str) -> str:
    polished = text.strip()
    if not polished:
        return ""
    replacements = [
        ("当前", "这轮"),
        ("建议先", "先"),
        ("需要补充", "还得补"),
        ("继续推进", "继续往下看"),
        ("是否", ""),
    ]
    for source, target in replacements:
        polished = polished.replace(source, target)
    while "  " in polished:
        polished = polished.replace("  ", " ")
    return polished.strip()


def _render_fallback_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__


def _record_llm_enhancement(
    case_state: CaseState,
    *,
    component: str,
    engine: str,
    fallback_used: bool,
    fallback_reason: str,
) -> None:
    enhancements = case_state.metadata.get("llm_enhancements")
    if not isinstance(enhancements, dict):
        enhancements = {}
    enhancements[component] = {
        "engine": engine,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
    }
    case_state.metadata["llm_enhancements"] = enhancements
