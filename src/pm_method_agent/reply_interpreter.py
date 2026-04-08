from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from pm_method_agent.llm_adapter import (
    LLMAdapter,
    LLMMessage,
    LLMRequest,
    OpenAICompatibleAdapter,
    load_openai_compatible_config_from_env,
)
from pm_method_agent.models import CaseState


SUPPORTED_BUSINESS_MODELS = {"tob", "toc", "internal"}
SUPPORTED_PLATFORMS = {"pc", "mobile-web", "native-app", "mini-program", "multi-platform"}
SUPPORTED_GATE_CHOICES = {"defer", "try-non-product-first", "productize-now"}
SUPPORTED_REPLY_CATEGORIES = {"context", "evidence", "decision", "constraint", "other"}
KNOWN_ROLES = ["前台", "管理者", "管理员", "运营", "新用户", "患者", "审批专员", "部门负责人"]


@dataclass
class ReplyAnalysis:
    context_updates: Dict[str, object]
    categories: List[str]
    inferred_gate_choice: Optional[str]
    parser_name: str
    parser_confidence: str = "medium"
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
        del previous_case
        text = reply_text.strip()
        extracted: Dict[str, object] = {}
        lowered = text.lower()

        if any(keyword in lowered for keyword in ["tob", "企业产品"]):
            extracted["business_model"] = "tob"
        elif any(keyword in lowered for keyword in ["toc", "消费者产品"]):
            extracted["business_model"] = "toc"
        elif "内部产品" in text or "internal" in lowered:
            extracted["business_model"] = "internal"

        if any(keyword in lowered for keyword in ["桌面端", "pc"]):
            extracted["primary_platform"] = "pc"
        elif any(keyword in lowered for keyword in ["移动网页", "mobile web", "h5"]):
            extracted["primary_platform"] = "mobile-web"
        elif any(keyword in lowered for keyword in ["原生应用", "app", "移动端"]):
            extracted["primary_platform"] = "native-app"
        elif "小程序" in text:
            extracted["primary_platform"] = "mini-program"
        elif "多端" in text:
            extracted["primary_platform"] = "multi-platform"

        inferred_roles: List[str] = []
        for role in KNOWN_ROLES:
            if role in text and role not in inferred_roles:
                inferred_roles.append(role)
        if inferred_roles:
            extracted["target_user_roles"] = inferred_roles

        return ReplyAnalysis(
            context_updates=extracted,
            categories=_classify_reply_categories(text, extracted),
            inferred_gate_choice=_infer_gate_choice(lowered),
            parser_name="heuristic",
            parser_confidence="medium",
            raw_payload={"reply_text": text},
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
        response = self._adapter.generate(request)
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError:
            return self._fallback.analyze_reply(reply_text, previous_case=previous_case)

        context_updates = _normalize_context_updates(payload.get("context_updates", {}))
        categories = _normalize_categories(payload.get("categories", []))
        gate_choice = _normalize_gate_choice(payload.get("inferred_gate_choice"))

        if not context_updates and not categories and not gate_choice:
            return self._fallback.analyze_reply(reply_text, previous_case=previous_case)

        if not categories:
            categories = _classify_reply_categories(reply_text.strip(), context_updates)

        return ReplyAnalysis(
            context_updates=context_updates,
            categories=categories,
            inferred_gate_choice=gate_choice,
            parser_name="llm",
            parser_confidence=str(payload.get("parser_confidence", "medium")),
            raw_payload=payload if isinstance(payload, dict) else {},
        )


def build_reply_interpreter_from_env() -> ReplyInterpreter:
    config = load_openai_compatible_config_from_env()
    if config is None:
        return HeuristicReplyInterpreter()
    return LLMReplyInterpreter(adapter=OpenAICompatibleAdapter(config=config))


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
    instruction = (
        "你是 PM Method Agent 的回复解释器。"
        "请把用户回复整理为 JSON，字段包括："
        "context_updates、categories、inferred_gate_choice、parser_confidence。"
        "context_updates 仅允许包含 business_model、primary_platform、target_user_roles。"
        "categories 仅允许包含 context、evidence、decision、constraint、other。"
        "inferred_gate_choice 仅允许为 defer、try-non-product-first、productize-now 或 null。"
        "不要输出 JSON 以外的内容。"
    )
    user_payload = {
        "current_context_profile": context_profile,
        "pending_questions": pending_questions,
        "decision_gates": gate_summary,
        "reply_text": reply_text.strip(),
    }
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=instruction),
            LLMMessage(role="user", content=json.dumps(user_payload, ensure_ascii=False)),
        ],
        response_format="json",
        metadata={"task": "interpret-session-reply"},
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
            if isinstance(role, str) and role.strip() and role.strip() not in normalized_roles:
                normalized_roles.append(role.strip())
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
    if any(keyword in lowered_text for keyword in ["暂缓", "先不做", "defer"]):
        return "defer"
    if any(
        keyword in lowered_text
        for keyword in [
            "不急着继续产品化",
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
    if any(keyword in lowered_text for keyword in ["继续产品化", "继续做", "还是继续", "继续推进", "productize"]):
        return "productize-now"
    if any(keyword in lowered_text for keyword in ["非产品", "流程提醒", "培训", "try non product"]):
        return "try-non-product-first"
    return None
