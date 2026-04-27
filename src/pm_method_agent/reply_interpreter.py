from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Protocol

from pm_method_agent.llm_adapter import (
    LLMAdapter,
    LLMMessage,
    LLMRequest,
    OpenAICompatibleAdapter,
    load_openai_compatible_config_from_env,
)
from pm_method_agent.models import CaseState
from pm_method_agent.prompting import build_prompt_composition
from pm_method_agent.question_resolution import (
    normalize_question_matches,
    resolve_pending_question_matches,
)
from pm_method_agent.role_extraction import (
    extract_role_relationships,
    extract_roles_from_text,
    filter_roles_for_text,
    normalize_role_name,
)


SUPPORTED_BUSINESS_MODELS = {"tob", "toc", "internal"}
SUPPORTED_PLATFORMS = {"pc", "mobile-web", "native-app", "mini-program", "multi-platform"}
SUPPORTED_GATE_CHOICES = {"defer", "try-non-product-first", "productize-now"}
SUPPORTED_REPLY_CATEGORIES = {"context", "evidence", "decision", "constraint", "other"}
SUPPORTED_ROLE_RELATIONSHIP_KEYS = {"proposers", "users", "outcome_owners"}


@dataclass
class ReplyAnalysis:
    context_updates: Dict[str, object]
    role_relationships: Dict[str, List[str]]
    categories: List[str]
    inferred_gate_choice: Optional[str]
    parser_name: str
    answered_pending_questions: List[str] = field(default_factory=list)
    partial_pending_questions: List[str] = field(default_factory=list)
    parser_confidence: str = "medium"
    fallback_used: bool = False
    fallback_reason: str = ""
    raw_payload: Dict[str, object] = field(default_factory=dict)


class ReplyInterpreter(Protocol):
    def analyze_reply(
        self,
        reply_text: str,
        previous_case: Optional[CaseState] = None,
    ) -> ReplyAnalysis:
        ...


class HeuristicReplyInterpreter:
    def analyze_reply(
        self,
        reply_text: str,
        previous_case: Optional[CaseState] = None,
    ) -> ReplyAnalysis:
        text = reply_text.strip()
        extracted: Dict[str, object] = {}
        lowered = text.lower()

        business_model = _infer_business_model(text, lowered)
        if business_model:
            extracted["business_model"] = business_model

        platform_hints: List[str] = []
        if any(keyword in lowered for keyword in ["桌面端", "pc", "网页端", "web", "浏览器", "管理后台", "后台", "管理台"]):
            platform_hints.append("pc")
        if any(keyword in lowered for keyword in ["移动网页", "mobile web", "h5", "h 5"]):
            platform_hints.append("mobile-web")
        if any(keyword in lowered for keyword in ["原生应用", "app", "移动端", "客户端", "安卓", "ios"]):
            platform_hints.append("native-app")
        if "小程序" in text or "企微" in text or "企业微信" in text:
            platform_hints.append("mini-program")
        if "多端" in text:
            platform_hints.append("multi-platform")

        deduped_platform_hints: List[str] = []
        for item in platform_hints:
            if item not in deduped_platform_hints:
                deduped_platform_hints.append(item)
        if "multi-platform" in deduped_platform_hints or len(deduped_platform_hints) > 1:
            extracted["primary_platform"] = "multi-platform"
        elif deduped_platform_hints:
            extracted["primary_platform"] = deduped_platform_hints[0]

        inferred_roles = extract_roles_from_text(text)
        role_relationships = extract_role_relationships(text)
        if inferred_roles:
            extracted["target_user_roles"] = filter_roles_for_text(inferred_roles, text)

        pending_questions = previous_case.pending_questions if previous_case else []
        merged_context = _merge_context_updates(previous_case.context_profile if previous_case else {}, extracted)
        answered_matches = resolve_pending_question_matches(
            pending_questions,
            merged_context=merged_context,
            role_relationships=role_relationships,
            inferred_gate_choice=_infer_gate_choice(lowered),
            reply_text=text,
        )

        return ReplyAnalysis(
            context_updates=extracted,
            role_relationships=role_relationships,
            categories=_classify_reply_categories(text, extracted),
            inferred_gate_choice=_infer_gate_choice(lowered),
            parser_name="heuristic",
            answered_pending_questions=answered_matches,
            parser_confidence="medium",
            raw_payload={"reply_text": text, "answered_pending_questions": answered_matches},
        )


class LLMReplyInterpreter:
    def __init__(
        self,
        adapter: LLMAdapter,
        fallback: Optional[ReplyInterpreter] = None,
    ) -> None:
        self._adapter = adapter
        self._fallback = fallback or HeuristicReplyInterpreter()

    def analyze_reply(
        self,
        reply_text: str,
        previous_case: Optional[CaseState] = None,
    ) -> ReplyAnalysis:
        request = _build_interpretation_request(reply_text, previous_case)
        try:
            response = self._adapter.generate(request)
            payload = json.loads(response.content)
        except Exception as exc:
            return _build_fallback_reply_analysis(
                self._fallback.analyze_reply(reply_text, previous_case=previous_case),
                parser_name="llm-fallback",
                reason=_render_fallback_reason(exc),
            )

        context_updates = _normalize_context_updates(payload.get("context_updates", {}))
        if "target_user_roles" in context_updates:
            context_updates["target_user_roles"] = filter_roles_for_text(
                list(context_updates["target_user_roles"]),
                reply_text.strip(),
            )
        categories = _normalize_categories(payload.get("categories", []))
        gate_choice = _normalize_gate_choice(payload.get("inferred_gate_choice"))
        role_relationships = _normalize_role_relationships(payload.get("role_relationships", {}))
        pending_questions = previous_case.pending_questions if previous_case else []
        answered_matches = _normalize_pending_question_matches(
            payload.get("answered_pending_questions", []),
            pending_questions,
        )
        partial_matches = _normalize_pending_question_matches(
            payload.get("partial_pending_questions", []),
            pending_questions,
            exclude=answered_matches,
        )

        if (
            not context_updates
            and not categories
            and not gate_choice
            and not any(role_relationships.values())
            and not answered_matches
            and not partial_matches
        ):
            return _build_fallback_reply_analysis(
                self._fallback.analyze_reply(reply_text, previous_case=previous_case),
                parser_name="llm-fallback",
                reason="llm-empty-result",
            )

        if not categories:
            categories = _classify_reply_categories(reply_text.strip(), context_updates)

        return ReplyAnalysis(
            context_updates=context_updates,
            role_relationships=_merge_role_relationship_payloads(
                extract_role_relationships(reply_text.strip()),
                role_relationships,
            ),
            categories=categories,
            inferred_gate_choice=gate_choice,
            parser_name="llm",
            answered_pending_questions=answered_matches,
            partial_pending_questions=partial_matches,
            parser_confidence=str(payload.get("parser_confidence", "medium")),
            raw_payload=payload if isinstance(payload, dict) else {},
        )


class HybridReplyInterpreter:
    def __init__(
        self,
        llm_interpreter: ReplyInterpreter,
        fallback: Optional[ReplyInterpreter] = None,
    ) -> None:
        self._llm_interpreter = llm_interpreter
        self._fallback = fallback or HeuristicReplyInterpreter()

    def analyze_reply(
        self,
        reply_text: str,
        previous_case: Optional[CaseState] = None,
    ) -> ReplyAnalysis:
        heuristic_result = self._fallback.analyze_reply(reply_text, previous_case=previous_case)
        llm_result = self._llm_interpreter.analyze_reply(reply_text, previous_case=previous_case)

        return ReplyAnalysis(
            context_updates=_finalize_context_updates(
                _merge_context_updates(
                    heuristic_result.context_updates,
                    llm_result.context_updates,
                ),
                reply_text,
            ),
            role_relationships=_merge_role_relationship_payloads_with_priority(
                heuristic_result.role_relationships,
                llm_result.role_relationships,
                reply_text,
            ),
            categories=_merge_categories(heuristic_result.categories, llm_result.categories),
            inferred_gate_choice=llm_result.inferred_gate_choice or heuristic_result.inferred_gate_choice,
            parser_name="hybrid-fallback" if llm_result.fallback_used else "hybrid",
            answered_pending_questions=_merge_question_matches(
                heuristic_result.answered_pending_questions,
                llm_result.answered_pending_questions,
            ),
            partial_pending_questions=_merge_question_matches(
                heuristic_result.partial_pending_questions,
                llm_result.partial_pending_questions,
                exclude=_merge_question_matches(
                    heuristic_result.answered_pending_questions,
                    llm_result.answered_pending_questions,
                ),
            ),
            parser_confidence=heuristic_result.parser_confidence if llm_result.fallback_used else llm_result.parser_confidence,
            fallback_used=llm_result.fallback_used,
            fallback_reason=llm_result.fallback_reason,
            raw_payload=_build_hybrid_raw_payload(heuristic_result, llm_result),
        )


def build_reply_interpreter_from_env() -> ReplyInterpreter:
    config = load_openai_compatible_config_from_env()
    if config is None:
        return HeuristicReplyInterpreter()
    heuristic = HeuristicReplyInterpreter()
    llm = LLMReplyInterpreter(adapter=OpenAICompatibleAdapter(config=config), fallback=heuristic)
    return HybridReplyInterpreter(llm_interpreter=llm, fallback=heuristic)


def _infer_business_model(text: str, lowered: str) -> Optional[str]:
    if any(keyword in lowered for keyword in ["tob", "企业产品", "b端", "b 端", "saas", "商家端"]):
        return "tob"
    if any(keyword in lowered for keyword in ["internal", "内部产品", "内部工具", "中后台", "后台系统"]):
        return "internal"
    if any(keyword in lowered for keyword in ["toc", "消费者产品", "c端", "c 端", "用户端"]):
        return "toc"

    consumer_signals = [
        "内容社区",
        "社区app",
        "社区 app",
        "社区产品",
        "发帖",
        "首帖",
        "注册后",
        "新用户",
    ]
    if any(signal in lowered for signal in consumer_signals):
        return "toc"

    del text
    return None


def _build_interpretation_request(reply_text: str, previous_case: Optional[CaseState]) -> LLMRequest:
    context_profile = previous_case.context_profile if previous_case else {}
    pending_questions = previous_case.pending_questions if previous_case else []
    decision_gates = previous_case.decision_gates if previous_case else []
    gate_summary = [
        {
            "gate_id": gate.gate_id,
            "question": gate.question,
            "options": gate.options,
            "recommended_option": gate.recommended_option,
        }
        for gate in decision_gates
    ]
    prompt = build_prompt_composition(
        identity="你是 PM Method Agent 的回复解释器，负责把用户当前回复收敛成可继续执行的结构化结果。",
        agent_role="你只负责解释这一轮回复，不负责改动阶段推进、决策关口或最终卡片结构。",
        behavior_rules=[
            "优先忠实提取用户明确表达的内容，不要主动脑补隐藏前提。",
            "当角色关系不明确时，宁可留空，也不要强行补全。",
            "涉及提出者、使用者、结果责任人时，要区分角色职责，不要混在一起。",
        ],
        tool_constraints=[
            "你不能越权改变 stage、workflow_state、output_kind 或 decision_gates。",
            "你只输出结构化解释结果，不承担 runtime 控制职责。",
        ],
        output_discipline=[
            "必须输出 JSON，不要输出 JSON 以外的内容。",
            "context_updates 仅允许包含 business_model、primary_platform、target_user_roles。",
            "role_relationships 仅允许包含 proposers、users、outcome_owners，且值为字符串数组。",
            "categories 仅允许包含 context、evidence、decision、constraint、other。",
            "inferred_gate_choice 仅允许为 defer、try-non-product-first、productize-now 或 null。",
            "answered_pending_questions 和 partial_pending_questions 仅允许从 pending_questions 中挑选原题或等价表达。",
        ],
        task_instruction="请把当前回复整理为可供会话服务层继续推进的结构化结果。",
    )
    user_payload = {
        "current_context_profile": context_profile,
        "pending_questions": pending_questions,
        "decision_gates": gate_summary,
        "reply_text": reply_text.strip(),
    }
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=prompt.render()),
            LLMMessage(role="user", content=json.dumps(user_payload, ensure_ascii=False)),
        ],
        response_format="json",
        metadata={
            "task": "interpret-session-reply",
            "prompt_layers": prompt.metadata(),
        },
    )


def _normalize_context_updates(payload: object) -> Dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    normalized: Dict[str, object] = {}

    business_model = payload.get("business_model")
    if isinstance(business_model, str) and business_model in SUPPORTED_BUSINESS_MODELS:
        normalized["business_model"] = business_model

    primary_platform = payload.get("primary_platform")
    if isinstance(primary_platform, str) and primary_platform in SUPPORTED_PLATFORMS:
        normalized["primary_platform"] = primary_platform

    target_user_roles = payload.get("target_user_roles")
    if isinstance(target_user_roles, list):
        normalized_roles = []
        for role in target_user_roles:
            if not isinstance(role, str):
                continue
            normalized_role = normalize_role_name(role.strip())
            if normalized_role and normalized_role not in normalized_roles:
                normalized_roles.append(normalized_role)
        if normalized_roles:
            normalized["target_user_roles"] = normalized_roles
    return normalized


def _normalize_categories(payload: object) -> List[str]:
    if not isinstance(payload, list):
        return []
    normalized = []
    for item in payload:
        if isinstance(item, str) and item in SUPPORTED_REPLY_CATEGORIES and item not in normalized:
            normalized.append(item)
    return normalized


def _normalize_gate_choice(payload: object) -> Optional[str]:
    if isinstance(payload, str) and payload in SUPPORTED_GATE_CHOICES:
        return payload
    return None


def _normalize_role_relationships(payload: object) -> Dict[str, List[str]]:
    normalized = {
        "proposers": [],
        "users": [],
        "outcome_owners": [],
    }
    if not isinstance(payload, dict):
        return normalized
    for key, items in payload.items():
        if key not in SUPPORTED_ROLE_RELATIONSHIP_KEYS or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, str):
                continue
            rendered = normalize_role_name(item.strip())
            if rendered and rendered not in normalized[key]:
                normalized[key].append(rendered)
    return normalized


def _normalize_pending_question_matches(
    payload: object,
    pending_questions: List[str],
    *,
    exclude: Optional[List[str]] = None,
) -> List[str]:
    normalized = normalize_question_matches(payload, pending_questions)
    if not exclude:
        return normalized
    return [item for item in normalized if item not in exclude]


def _build_fallback_reply_analysis(
    fallback_result: ReplyAnalysis,
    *,
    parser_name: str,
    reason: str,
) -> ReplyAnalysis:
    raw_payload = dict(fallback_result.raw_payload)
    raw_payload["fallback_reason"] = reason
    raw_payload["fallback_parser"] = fallback_result.parser_name
    return replace(
        fallback_result,
        parser_name=parser_name,
        parser_confidence="low",
        fallback_used=True,
        fallback_reason=reason,
        raw_payload=raw_payload,
    )


def _render_fallback_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__


def _build_hybrid_raw_payload(
    heuristic_result: ReplyAnalysis,
    llm_result: ReplyAnalysis,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "heuristic": heuristic_result.raw_payload,
        "llm": llm_result.raw_payload,
    }
    if llm_result.fallback_used:
        payload["fallback_reason"] = llm_result.fallback_reason
        payload["fallback_parser"] = str(llm_result.raw_payload.get("fallback_parser", "")).strip() or llm_result.parser_name
    return payload


def _merge_question_matches(
    primary: List[str],
    secondary: List[str],
    *,
    exclude: Optional[List[str]] = None,
) -> List[str]:
    merged: List[str] = []
    for item in list(primary) + list(secondary):
        if not isinstance(item, str) or not item.strip():
            continue
        rendered = item.strip()
        if exclude and rendered in exclude:
            continue
        if rendered not in merged:
            merged.append(rendered)
    return merged


def _merge_context_updates(primary: Dict[str, object], secondary: Dict[str, object]) -> Dict[str, object]:
    merged = dict(primary)
    for key, value in secondary.items():
        if key == "target_user_roles":
            primary_roles = list(merged.get(key, [])) if isinstance(merged.get(key), list) else []
            secondary_roles = list(value) if isinstance(value, list) else []
            for role in secondary_roles:
                if role not in primary_roles:
                    primary_roles.append(role)
            if primary_roles:
                merged[key] = primary_roles
            continue
        merged[key] = value
    return merged


def _finalize_context_updates(context_updates: Dict[str, object], reply_text: str) -> Dict[str, object]:
    finalized = dict(context_updates)
    roles = finalized.get("target_user_roles")
    if isinstance(roles, list):
        filtered_roles = filter_roles_for_text(list(roles), reply_text.strip())
        if filtered_roles:
            finalized["target_user_roles"] = filtered_roles
        else:
            finalized.pop("target_user_roles", None)
    return finalized


def _merge_role_relationship_payloads(
    primary: Dict[str, List[str]],
    secondary: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    merged = _normalize_role_relationships(primary)
    extra = _normalize_role_relationships(secondary)
    for key, items in extra.items():
        for item in items:
            if item not in merged[key]:
                merged[key].append(item)
    return merged


def _merge_role_relationship_payloads_with_priority(
    primary: Dict[str, List[str]],
    secondary: Dict[str, List[str]],
    reply_text: str,
) -> Dict[str, List[str]]:
    merged = _normalize_role_relationships(primary)
    extra = _normalize_role_relationships(secondary)
    for key, items in extra.items():
        if merged[key]:
            continue
        if not _can_backfill_relation_from_llm(key, items, reply_text):
            continue
        for item in items:
            if item not in merged[key]:
                merged[key].append(item)
    return merged


def _can_backfill_relation_from_llm(key: str, items: List[str], reply_text: str) -> bool:
    if not items:
        return False
    if key == "proposers":
        return len(items) == 1 and all(_has_explicit_proposer_signal_for_role(item, reply_text) for item in items)
    if key == "users":
        return len(items) <= 2 and all(_has_explicit_user_signal(item, reply_text) for item in items)
    if key == "outcome_owners":
        return len(items) == 1 and all(_has_explicit_outcome_signal(item, reply_text) for item in items)
    return False


def _has_explicit_proposer_signal(reply_text: str) -> bool:
    lowered = reply_text.lower()
    return any(
        keyword in lowered
        for keyword in [
            "提出",
            "提的",
            "提出来",
            "反馈",
            "建议",
            "希望增加",
            "希望做",
            "想增加",
            "想做",
        ]
    )


def _has_explicit_proposer_signal_for_role(role: str, reply_text: str) -> bool:
    if not _has_explicit_proposer_signal(reply_text):
        return False
    escaped = re.escape(role)
    return any(
        re.search(pattern.format(role=escaped), reply_text)
        for pattern in [
            r"{role}提出(?:了)?需求",
            r"{role}提出(?:了)?这个想法",
            r"{role}提出(?:了)?这个方向",
            r"{role}提(?:了)?需求",
            r"{role}提(?:的|了这个事|了这个需求)",
            r"{role}反馈",
            r"这个需求是{role}提出来的",
            r"这个需求是{role}提出的需求",
        ]
    )


def _has_explicit_user_signal(role: str, reply_text: str) -> bool:
    if _has_explicit_non_user_signal(role, reply_text):
        return False
    escaped = re.escape(role)
    return any(
        re.search(pattern.format(role=escaped), reply_text)
        for pattern in [
            r"{role}在使用(?:产品|系统|服务)?",
            r"{role}使用(?:产品|系统|服务)?",
            r"{role}会使用(?:产品|系统|服务)?",
            r"{role}在[^，。；]{{0,8}}操作",
            r"{role}操作(?:这个动作|这一步|这个流程|提醒动作|流程)?",
            r"{role}自己.*操作",
            r"{role}在日常操作里",
            r"{role}在用",
            r"{role}每天在用",
            r"{role}一线在用",
            r"{role}在处理",
            r"{role}直接操作",
            r"{role}直接使用",
            r"{role}来处理",
            r"{role}是实际使用者",
            r"{role}是实际使用的人",
            r"{role}是使用者",
        ]
    )


def _has_explicit_non_user_signal(role: str, reply_text: str) -> bool:
    escaped = re.escape(role)
    return any(
        re.search(pattern.format(role=escaped), reply_text)
        for pattern in [
            r"{role}不直接操作",
            r"{role}不操作",
            r"{role}不直接使用",
            r"{role}不使用",
            r"{role}不在用",
            r"{role}不直接处理",
            r"{role}不是使用者",
        ]
    )


def _has_explicit_outcome_signal(role: str, reply_text: str) -> bool:
    escaped = re.escape(role)
    return any(
        re.search(pattern.format(role=escaped), reply_text)
        for pattern in [
            r"{role}对结果负责",
            r"{role}会对结果负责",
            r"{role}负责结果",
            r"{role}盯结果",
            r"{role}背结果",
            r"{role}拍板",
            r"{role}更关注",
            r"{role}会看结果",
            r"{role}看结果",
            r"{role}决定是否上线",
            r"{role}决定要不要上线",
            r"{role}决定是否做",
            r"{role}决定要不要做",
            r"{role}决定是否采购",
        ]
    )


def _merge_categories(primary: List[str], secondary: List[str]) -> List[str]:
    merged: List[str] = []
    for item in list(primary) + list(secondary):
        if item in SUPPORTED_REPLY_CATEGORIES and item not in merged:
            merged.append(item)
    return merged


def _classify_reply_categories(text: str, context_updates: Dict[str, object]) -> List[str]:
    categories = []
    if context_updates or any(keyword in text for keyword in ["角色", "用户", "产品", "平台", "面向"]):
        categories.append("context")
    if any(
        keyword in text
        for keyword in ["现在", "目前", "最近", "两周", "高峰期", "流程", "漏", "案例", "数据", "基线", "发生"]
    ) or any(character.isdigit() for character in text):
        categories.append("evidence")
    if any(keyword in text for keyword in ["继续产品化", "继续做", "暂缓", "先不做", "优先", "还是继续", "先试"]):
        categories.append("decision")
    if any(keyword in text for keyword in ["合规", "预算", "周期", "资源", "设备", "权限", "上线", "本周", "本月"]):
        categories.append("constraint")
    if not categories:
        categories.append("other")
    return categories


def _infer_gate_choice(lowered_text: str) -> Optional[str]:
    if any(
        keyword in lowered_text
        for keyword in [
            "不急着继续产品化",
            "先看流程",
            "先看流程约束",
            "先看流程能不能",
            "先做一轮非产品验证",
            "先做非产品验证",
            "先试流程",
            "先试培训",
            "先试非产品",
            "先走流程",
            "先走培训",
            "先试",
            "流程优先",
            "培训优先",
        ]
    ):
        return "try-non-product-first"
    if any(
        keyword in lowered_text
        for keyword in [
            "暂缓",
            "先不做",
            "先不立项",
            "不立项",
            "先不上线",
            "不上线",
            "上线先别急",
            "先观察",
            "观察两周",
            "先观察两周",
            "再决定要不要做产品",
            "先做点轻验证",
            "做点轻验证",
            "轻验证",
            "设计可以先看",
            "先看设计",
            "defer",
            "不用现在做",
            "不一定有资源",
            "没有资源支持",
            "短期没有资源支持",
            "短期也没有资源支持",
            "资源比较紧张",
            "资源紧张",
            "nice to have",
            "nice-to-have",
            "先放放",
            "先放一放",
            "放一放",
            "目标不在这里",
            "这阶段目标不在这里",
            "以后再说",
            "没那么重要",
        ]
    ):
        return "defer"
    if any(keyword in lowered_text for keyword in ["继续产品化", "继续做", "还是继续", "继续推进", "productize"]):
        return "productize-now"
    if any(keyword in lowered_text for keyword in ["非产品", "流程提醒", "培训", "try non product"]):
        return "try-non-product-first"
    return None
