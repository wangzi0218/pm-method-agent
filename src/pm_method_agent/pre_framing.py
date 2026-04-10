from __future__ import annotations

import json
from typing import Dict, List, Optional, Protocol

from pm_method_agent.llm_adapter import (
    LLMAdapter,
    LLMMessage,
    LLMRequest,
    OpenAICompatibleAdapter,
    load_openai_compatible_config_from_env,
)
from pm_method_agent.models import CaseState, PreFramingDirection, PreFramingResult
from pm_method_agent.prompting import build_prompt_composition


AMBIGUOUS_HINTS = [
    "是不是",
    "要不要",
    "该不该",
    "怎么处理",
    "值不值得",
    "感觉",
    "好像",
    "我在想",
    "处理一下",
]

SOLUTION_HINTS = [
    "增加",
    "新增",
    "加一个",
    "弹窗",
    "按钮",
    "页面",
    "引导",
    "浮层",
    "看板",
]

PROCESS_HINTS = [
    "漏",
    "提醒",
    "流程",
    "跟进",
    "复诊",
    "预约",
    "执行",
]

GROWTH_HINTS = [
    "发帖",
    "转化",
    "留存",
    "新手",
    "活跃",
    "增长",
]


class PreFramingGenerator(Protocol):
    def generate(
        self,
        case_state: CaseState,
        fallback_result: PreFramingResult,
    ) -> PreFramingResult:
        ...


class LLMPreFramingGenerator:
    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    def generate(
        self,
        case_state: CaseState,
        fallback_result: PreFramingResult,
    ) -> PreFramingResult:
        request = _build_pre_framing_request(case_state, fallback_result)
        response = self._adapter.generate(request)
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError:
            return fallback_result

        enhanced_result = _normalize_pre_framing_payload(payload, fallback_result)
        if not enhanced_result.candidate_directions:
            return fallback_result
        return enhanced_result


def should_trigger_pre_framing(case_state: CaseState) -> bool:
    text = case_state.raw_input.strip()
    lowered = text.lower()
    has_core_context = bool(case_state.context_profile.get("business_model")) and bool(
        case_state.context_profile.get("primary_platform")
    )

    if case_state.metadata.get("skip_pre_framing"):
        return False
    if case_state.stage not in {"intake", "pre-framing", "context-alignment"}:
        return False
    if len(text) < 16:
        return False
    if has_core_context and not _has_ambiguity_signal(text, lowered):
        return False

    score = 0
    if _has_ambiguity_signal(text, lowered):
        score += 2
    if _has_solution_signal(text):
        score += 2
    if _has_mixed_problem_signal(text):
        score += 1
    if not case_state.context_profile.get("business_model"):
        score += 1
    if not case_state.context_profile.get("primary_platform"):
        score += 1
    return score >= 3


def build_pre_framing_result(
    case_state: CaseState,
    generator: Optional[PreFramingGenerator] = None,
) -> PreFramingResult:
    fallback_result = _build_heuristic_pre_framing_result(case_state)
    active_generator = generator or build_pre_framing_generator_from_env()
    if active_generator is None:
        return fallback_result
    return active_generator.generate(case_state=case_state, fallback_result=fallback_result)


def build_pre_framing_generator_from_env() -> Optional[PreFramingGenerator]:
    config = load_openai_compatible_config_from_env()
    if config is None:
        return None
    return LLMPreFramingGenerator(adapter=OpenAICompatibleAdapter(config=config))


def _build_heuristic_pre_framing_result(case_state: CaseState) -> PreFramingResult:
    text = case_state.raw_input.strip()
    context_profile = case_state.context_profile
    business_model = str(context_profile.get("business_model", "")).strip()
    directions: List[PreFramingDirection] = []

    if _has_solution_signal(text):
        directions.append(
            PreFramingDirection(
                direction_id="D-001",
                label="方案先行，问题边界还没站稳",
                summary="这句话里已经混进了方案表达，先把现象和方案拆开会更稳。",
                assumptions=[
                    "当前团队已经带着一个默认解法在想",
                    "真正的现象层问题还没有单独说清",
                ],
                confidence="medium",
            )
        )

    if any(keyword in text for keyword in PROCESS_HINTS) or business_model == "tob":
        directions.append(
            PreFramingDirection(
                direction_id=f"D-{len(directions) + 1:03d}",
                label="流程执行或责任链不稳定",
                summary="问题可能更像流程执行不稳定，或者关键动作没有稳定落到某个角色。",
                assumptions=[
                    "当前关键动作仍依赖人工记忆或临场判断",
                    "提出者、执行者和结果责任人之间还没有完全对齐",
                ],
                confidence="medium",
            )
        )

    if any(keyword in text for keyword in GROWTH_HINTS) or business_model == "toc":
        directions.append(
            PreFramingDirection(
                direction_id=f"D-{len(directions) + 1:03d}",
                label="关键行为门槛或动机不足",
                summary="问题可能不在界面本身，而在用户为什么没有完成关键行为。",
                assumptions=[
                    "当前目标行为前存在额外理解或操作门槛",
                    "想做的方案未必直接打在真实阻塞点上",
                ],
                confidence="medium",
            )
        )

    directions.append(
        PreFramingDirection(
            direction_id=f"D-{len(directions) + 1:03d}",
            label="现象已经被感知，但证据还不够稳",
            summary="这件事可能真实存在，但还需要先补发生环节、频率和影响，再决定怎么推进。",
            assumptions=[
                "目前更多是经验感受，还没有形成稳定证据",
                "继续往下判断前，还缺一段真实现状和影响描述",
            ],
            confidence="low" if len(directions) > 1 else "medium",
        )
    )

    directions = _dedupe_directions(directions)[:3]
    priority_questions = _build_priority_questions(text, context_profile)[:3]
    recommended_direction_id = directions[0].direction_id if directions else ""

    return PreFramingResult(
        triggered=True,
        reason=_build_reason(text, context_profile),
        candidate_directions=directions,
        priority_questions=priority_questions,
        recommended_direction_id=recommended_direction_id,
    )


def _build_pre_framing_request(
    case_state: CaseState,
    fallback_result: PreFramingResult,
) -> LLMRequest:
    prompt = build_prompt_composition(
        identity="你是 PM Method Agent 的前置收敛增强器，负责在正式分析前收窄理解方向。",
        agent_role="你只增强候选方向和优先追问，不改变主线阶段，也不替代主协调器做最终判断。",
        behavior_rules=[
            "只在现有输入和启发式结果基础上增强，不要凭空扩写新的业务事实。",
            "候选方向要彼此可区分，不要换种说法重复同一件事。",
            "优先帮助用户更快收窄问题，不要写成长篇分析。",
        ],
        tool_constraints=[
            "你不能改动阶段推进、决策关口或 case 的主线状态。",
        ],
        output_discipline=[
            "必须输出 JSON，不要输出 JSON 以外的内容。",
            "字段包括 reason、candidate_directions、priority_questions、recommended_direction_id。",
            "candidate_directions 最多 3 项，每项字段包括 direction_id、label、summary、assumptions、confidence。",
            "priority_questions 最多 3 项。",
            "语气要自然、克制、像协作中的产品同事，不要写成汇报材料。",
        ],
        task_instruction="请基于用户输入和已有启发式结果，增强前置收敛方向和追问。",
    )
    payload = {
        "raw_input": case_state.raw_input,
        "context_profile": case_state.context_profile,
        "fallback_result": fallback_result.to_dict(),
    }
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=prompt.render()),
            LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ],
        response_format="json",
        metadata={
            "task": "pre-framing-enhancement",
            "prompt_layers": prompt.metadata(),
        },
    )


def _normalize_pre_framing_payload(
    payload: object,
    fallback_result: PreFramingResult,
) -> PreFramingResult:
    if not isinstance(payload, dict):
        return fallback_result

    directions_payload = payload.get("candidate_directions", [])
    directions: List[PreFramingDirection] = []
    if isinstance(directions_payload, list):
        for index, item in enumerate(directions_payload[:3], start=1):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            summary = str(item.get("summary", "")).strip()
            if not label or not summary:
                continue
            assumptions_payload = item.get("assumptions", [])
            assumptions = []
            if isinstance(assumptions_payload, list):
                for assumption in assumptions_payload[:3]:
                    if isinstance(assumption, str) and assumption.strip():
                        assumptions.append(assumption.strip())
            confidence = str(item.get("confidence", "medium")).strip() or "medium"
            direction_id = str(item.get("direction_id", "")).strip() or f"D-{index:03d}"
            directions.append(
                PreFramingDirection(
                    direction_id=direction_id,
                    label=label,
                    summary=summary,
                    assumptions=assumptions,
                    confidence=confidence,
                )
            )

    if not directions:
        return fallback_result

    priority_questions_payload = payload.get("priority_questions", [])
    priority_questions: List[str] = []
    if isinstance(priority_questions_payload, list):
        for item in priority_questions_payload[:3]:
            if isinstance(item, str) and item.strip() and item.strip() not in priority_questions:
                priority_questions.append(item.strip())
    if not priority_questions:
        priority_questions = list(fallback_result.priority_questions)

    recommended_direction_id = str(payload.get("recommended_direction_id", "")).strip()
    valid_direction_ids = {item.direction_id for item in directions}
    if recommended_direction_id not in valid_direction_ids:
        recommended_direction_id = directions[0].direction_id

    return PreFramingResult(
        triggered=True,
        reason=str(payload.get("reason", "")).strip() or fallback_result.reason,
        candidate_directions=directions,
        priority_questions=priority_questions,
        recommended_direction_id=recommended_direction_id,
    )


def _has_ambiguity_signal(text: str, lowered: str) -> bool:
    if any(keyword in text for keyword in AMBIGUOUS_HINTS):
        return True
    return any(keyword in lowered for keyword in ["should we", "worth", "maybe", "not sure"])


def _has_solution_signal(text: str) -> bool:
    return any(keyword in text for keyword in SOLUTION_HINTS)


def _has_mixed_problem_signal(text: str) -> bool:
    has_problem = any(keyword in text for keyword in ["漏", "影响", "问题", "不顺", "抱怨", "担心", "下降"])
    return has_problem and (_has_solution_signal(text) or _has_ambiguity_signal(text, text.lower()))


def _build_reason(text: str, context_profile: Dict[str, object]) -> str:
    if _has_solution_signal(text) and _has_ambiguity_signal(text, text.lower()):
        return "输入里同时混着方案倾向和不确定判断，先把理解方向收一收会更稳。"
    if not context_profile.get("business_model") or not context_profile.get("primary_platform"):
        return "当前既缺一部分场景信息，也存在不止一种问题理解，先收一收方向再补背景更合适。"
    return "这句话还存在几种都说得通的理解，先别急着往下收敛。"


def _build_priority_questions(text: str, context_profile: Dict[str, object]) -> List[str]:
    questions: List[str] = []
    if any(keyword in text for keyword in PROCESS_HINTS):
        questions.append("漏掉或卡住的动作，具体发生在流程的哪个环节？")
        questions.append("平时到底是谁在执行这个动作，谁会对结果负责？")
    if any(keyword in text for keyword in GROWTH_HINTS):
        questions.append("目标用户没有完成关键行为，最可能卡在哪一步？")
    if _has_solution_signal(text):
        questions.append("你现在最想解决的现象是什么，和想到的方案先分开说。")
    if not context_profile.get("business_model"):
        questions.append("这件事发生在企业产品、消费者产品还是内部工具里？")
    if not context_profile.get("primary_platform"):
        questions.append("当前主要发生在哪个平台或终端里？")
    questions.append("最近为什么开始觉得这件事更值得处理了？")
    return _dedupe_strings(questions)


def _dedupe_directions(items: List[PreFramingDirection]) -> List[PreFramingDirection]:
    deduped: List[PreFramingDirection] = []
    seen_labels = set()
    for item in items:
        if item.label in seen_labels:
            continue
        seen_labels.add(item.label)
        deduped.append(item)
    return deduped


def _dedupe_strings(items: List[str]) -> List[str]:
    deduped: List[str] = []
    for item in items:
        rendered = item.strip()
        if rendered and rendered not in deduped:
            deduped.append(rendered)
    return deduped
