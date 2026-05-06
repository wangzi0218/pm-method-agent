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
