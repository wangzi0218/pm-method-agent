from __future__ import annotations

import json
from typing import Any, Dict


LLM_EMPTY_RESULT = "llm-empty-result"


class LLMContractError(ValueError):
    """Raised when a model response cannot satisfy the local component contract."""


def parse_llm_json_object(content: str, *, component: str) -> Dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMContractError(f"invalid-json: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise LLMContractError(f"contract-violation: {component} expected a JSON object")
    return payload


def empty_result_reason(component: str) -> str:
    return f"{LLM_EMPTY_RESULT}: {component} returned no usable fields"


def normalize_llm_failure_kind(reason: str) -> str:
    normalized = reason.strip().lower()
    if not normalized:
        return "unknown"
    if "empty-result" in normalized or "empty result" in normalized or "empty" in normalized:
        return "empty-result"
    if "json" in normalized or "decode" in normalized:
        return "invalid-json"
    if "timeout" in normalized or "timed out" in normalized or "gateway-timeout" in normalized:
        return "timeout"
    if any(keyword in normalized for keyword in ["network", "offline", "connection", "dns", "unreachable", "urlerror"]):
        return "network-error"
    if any(keyword in normalized for keyword in ["invalid", "contract", "schema", "校验", "契约"]):
        return "contract-violation"
    return "unknown"


def is_contract_fallback_reason(reason: str) -> bool:
    return normalize_llm_failure_kind(reason) in {"invalid-json", "empty-result", "contract-violation"}


def llm_component_label(component: str) -> str:
    labels = {
        "reply-interpreter": "回复理解",
        "pre-framing": "前置收敛",
        "copywriter": "文案增强",
        "follow-up-copywriter": "追问润色",
        "demo-seed": "示例生成",
    }
    return labels.get(component, component)


def llm_component_user_message(*, component_label: str, status: str, failure_kind: str) -> str:
    if status == "llm-assisted":
        return f"{component_label}已使用模型辅助，主线判断仍由方法运行时控制。"
    if status == "local":
        return f"{component_label}由本地规则完成。"
    reason_label = {
        "timeout": "模型响应超时",
        "network-error": "模型服务暂时不可达",
        "invalid-json": "模型返回内容无法解析",
        "empty-result": "模型没有返回可用结果",
        "contract-violation": "模型输出未通过契约校验",
        "unknown": "模型增强没有稳定完成",
    }.get(failure_kind, "模型增强没有稳定完成")
    return f"{component_label}已回到本地规则（{reason_label}），不影响继续分析。"
