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
from pm_method_agent.question_resolution import question_family_key


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
    _apply_local_follow_up_display_copy(case_state)
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
            "如果用户这轮已经答到一半，优先顺着那半步继续问，不要装作没看到。",
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
        "partial_pending_questions": list(case_state.metadata.get("last_partial_pending_questions", [])),
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


def _apply_local_follow_up_display_copy(case_state: CaseState) -> None:
    partial_questions = _partial_pending_questions(case_state)
    if not partial_questions:
        return

    display_questions = _build_partial_display_questions(case_state, partial_questions)
    if display_questions:
        case_state.metadata[FOLLOW_UP_DISPLAY_QUESTIONS_KEY] = display_questions


def _partial_pending_questions(case_state: CaseState) -> list[str]:
    raw_items = case_state.metadata.get("last_partial_pending_questions", [])
    if not isinstance(raw_items, list):
        return []
    current_questions = [str(item).strip() for item in case_state.pending_questions if str(item).strip()]
    matched: list[str] = []
    for item in raw_items:
        normalized = str(item).strip()
        if not normalized:
            continue
        for current in current_questions:
            if current == normalized or question_family_key(current) == question_family_key(normalized):
                if current not in matched:
                    matched.append(current)
                break
    return matched


def _build_partial_display_questions(case_state: CaseState, partial_questions: list[str]) -> list[str]:
    latest_note = _latest_note(case_state)
    rewritten: list[str] = []
    for question in partial_questions[:3]:
        rewritten_question = _rewrite_partial_question(question, latest_note)
        if rewritten_question and rewritten_question not in rewritten:
            rewritten.append(rewritten_question)

    for question in case_state.pending_questions[:3]:
        if question in partial_questions:
            continue
        polished = _polish_text(str(question).strip())
        if polished and polished not in rewritten:
            rewritten.append(polished)
        if len(rewritten) >= 3:
            break
    return rewritten[:3]


def summarize_partial_question(question: str, latest_note: str) -> str:
    family_key = question_family_key(question)
    note = latest_note.strip()
    metric_hint = _extract_metric_hint(note)
    role_hint = _extract_role_hint(note)
    if family_key == "success-metric":
        return "做到什么程度，你会觉得这轮值得继续？"
    if family_key == "guardrail-metric":
        if metric_hint:
            return f"除了{metric_hint}，你最不希望哪项指标被带坏？"
        return "你最不希望哪项指标被带坏？"
    if family_key == "stop-condition":
        return "出现什么情况，你会先停下来？"
    if family_key == "baseline-metric":
        if metric_hint:
            return f"{metric_hint}现在的基线值大概是多少？"
        return "现在的基线值大概是多少？"
    if family_key == "why-now":
        return "为什么偏偏是现在更值得做？"
    if family_key == "opportunity-cost":
        return "如果先不做，最可能丢掉什么？"
    if family_key == "non-product-path":
        return "不改产品的话，先靠流程或运营能不能兜住一部分？"
    if family_key == "business-model":
        return "这更像企业产品、消费者产品，还是内部场景？"
    if family_key == "primary-platform":
        return "这件事主要发生在网页、App、小程序，还是多端一起看？"
    if family_key == "role-triplet":
        return "谁提、谁在用、最后谁盯结果？"
    if family_key == "proposer":
        if role_hint:
            return f"最先把这件事提出来的人，是不是{role_hint}？"
        return "最先把这件事提出来的人是谁？"
    if family_key == "user":
        if role_hint:
            return f"平时真正在操作这一步的人，是不是{role_hint}？"
        return "平时真正在操作这一步的人，到底是谁？"
    if family_key == "outcome-owner":
        if role_hint:
            return f"最后盯这件事结果的人，是不是{role_hint}？"
        return "最后谁会盯这件事的结果？"
    if family_key == "role-alignment":
        return "他们想要的结果，是一致的还是有冲突？"
    if family_key == "process-flow":
        return "现在这步流程具体是怎么走的？"
    if family_key == "issue-frequency":
        return "这件事大概多久会发生一次，影响到多大范围？"
    if family_key == "existing-workaround":
        return "现在大家会怎么绕过去，或者先靠什么办法顶着？"
    if family_key == "validation-action":
        return "你想先用什么最小动作试一下？"
    if family_key == "validation-period":
        return "你觉得观察多久，才足够判断这件事值不值得继续？"
    return _polish_text(question).strip("：")


def _rewrite_partial_question(question: str, latest_note: str) -> str:
    family_key = question_family_key(question)
    note = latest_note.strip()
    metric_hint = _extract_metric_hint(note)
    role_hint = _extract_role_hint(note)
    if family_key == "success-metric":
        if metric_hint:
            return f"{metric_hint}方向已经提到了，再补一句：做到什么程度，你会觉得这轮值得继续？"
        return "目标方向已经有一点了，再补一句：做到什么程度，你会觉得这轮值得继续？"
    if family_key == "guardrail-metric":
        if metric_hint:
            return f"主指标已经碰到了，再补一句：除了{metric_hint}，你最不希望哪项指标被带坏？"
        return "主指标已经有方向了，再补一句：你最不希望哪项指标被带坏？"
    if family_key == "stop-condition":
        return "这轮已经有一点判断了，再补一句：出现什么情况，你会先停下来？"
    if family_key == "baseline-metric":
        if metric_hint:
            return f"{metric_hint}方向已经提到了，再补一个现在的基线值，大概数量级也可以。"
        return "方向已经提到了，再补一个现在的基线值，大概数量级也可以。"
    if family_key == "why-now":
        return "已经有一点理由了，再补一句：为什么偏偏是现在更值得做？"
    if family_key == "opportunity-cost":
        return "再补一句：如果先不做，最可能丢掉什么？"
    if family_key == "non-product-path":
        return "你已经碰到方向了，再补一句：不改产品的话，先靠流程或运营能不能兜住一部分？"
    if family_key == "business-model":
        return "方向已经有一点了，再补一句：这更像企业产品、消费者产品，还是内部场景？"
    if family_key == "primary-platform":
        return "再补一句：这件事主要发生在网页、App、小程序，还是多端一起看？"
    if family_key == "role-triplet":
        return "这层已经碰到了，再补一句：谁提、谁在用、最后谁盯结果？"
    if family_key == "proposer":
        if role_hint:
            return f"已经提到{role_hint}了，再补一句：最先把这件事提出来的人是谁？"
        return "这点已经碰到了，再补一句：最先把这件事提出来的人是谁？"
    if family_key == "user":
        if role_hint:
            return f"已经提到{role_hint}了，再补一句：平时真正在操作这一步的人，到底是谁？"
        return "再补一句：平时真正在操作这一步的人，到底是谁？"
    if family_key == "outcome-owner":
        if role_hint:
            return f"已经提到{role_hint}了，再补一句：最后谁会盯这件事的结果？"
        return "再补一句：最后谁会盯这件事的结果？"
    if family_key == "role-alignment":
        return "角色已经提到一点了，再补一句：他们想要的结果，是一致的还是有冲突？"
    if family_key == "process-flow":
        return "已经提到现状了，再顺手补一句：现在这步流程具体是怎么走的？"
    if family_key == "issue-frequency":
        return "这点已经有点感觉了，再补一句：大概多久会发生一次，影响到多大范围？"
    if family_key == "existing-workaround":
        return "已经提到现状了，再补一句：现在大家会怎么绕过去，或者先靠什么办法顶着？"
    if family_key == "validation-action":
        return "方向已经有了，再补一句：你想先用什么最小动作试一下？"
    if family_key == "validation-period":
        return "再补一句：你觉得观察多久，才足够判断这件事值不值得继续？"
    if note:
        return f"顺着你刚才提到的这点，再补一句：{summarize_partial_question(question, latest_note)}"
    return f"顺着刚才那半步，再补一句：{summarize_partial_question(question, latest_note)}"


def _extract_metric_hint(note: str) -> str:
    if not note:
        return ""
    candidates = [
        "首帖率",
        "发帖率",
        "到诊率",
        "转化率",
        "留存",
        "活跃",
        "预约到诊",
        "提醒触达",
        "下单转化",
    ]
    for item in candidates:
        if item in note:
            return item
    return ""


def _extract_role_hint(note: str) -> str:
    if not note:
        return ""
    candidates = [
        "前台",
        "店长",
        "运营",
        "医生",
        "护士",
        "管理者",
        "用户",
        "新用户",
        "审核同学",
    ]
    for item in candidates:
        if item in note:
            return item
    return ""


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
