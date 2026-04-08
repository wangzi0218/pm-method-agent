from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol
from urllib import request


DEFAULT_OPENAI_COMPATIBLE_PATH = "/chat/completions"


@dataclass
class OpenAICompatibleConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 30.0
    api_path: str = DEFAULT_OPENAI_COMPATIBLE_PATH
    provider_name: str = "openai-compatible"
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMRequest:
    messages: List[LLMMessage]
    response_format: str = "json"
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str
    provider: str = ""
    model: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)


class LLMAdapter(Protocol):
    def generate(self, request_payload: LLMRequest) -> LLMResponse:
        ...


TransportFn = Callable[[str, Dict[str, str], bytes, float], str]


class OpenAICompatibleAdapter:
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        transport: Optional[TransportFn] = None,
    ) -> None:
        self._config = config
        self._transport = transport or _default_transport

    def generate(self, request_payload: LLMRequest) -> LLMResponse:
        url = _build_endpoint_url(self._config.base_url, self._config.api_path)
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self._config.headers)
        body_payload = {
            "model": self._config.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request_payload.messages
            ],
        }
        if request_payload.response_format == "json":
            body_payload["response_format"] = {"type": "json_object"}
        body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
        raw_response = self._transport(url, headers, body, self._config.timeout_seconds)
        payload = json.loads(raw_response)
        return LLMResponse(
            content=_extract_content(payload),
            provider=self._config.provider_name,
            model=str(payload.get("model", self._config.model)),
            metadata={"raw_response": payload},
        )


def load_openai_compatible_config_from_env() -> Optional[OpenAICompatibleConfig]:
    if not _env_flag("PMMA_LLM_ENABLED"):
        return None

    base_url = os.getenv("PMMA_LLM_BASE_URL", "").strip()
    api_key = os.getenv("PMMA_LLM_API_KEY", "").strip()
    model = os.getenv("PMMA_LLM_MODEL", "").strip()
    if not base_url or not api_key or not model:
        return None

    timeout_seconds = 30.0
    timeout_raw = os.getenv("PMMA_LLM_TIMEOUT", "").strip()
    if timeout_raw:
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 30.0

    headers: Dict[str, str] = {}
    extra_headers_raw = os.getenv("PMMA_LLM_EXTRA_HEADERS_JSON", "").strip()
    if extra_headers_raw:
        try:
            extra_headers_payload = json.loads(extra_headers_raw)
            if isinstance(extra_headers_payload, dict):
                headers = {
                    str(key): str(value)
                    for key, value in extra_headers_payload.items()
                    if str(key).strip()
                }
        except json.JSONDecodeError:
            headers = {}

    return OpenAICompatibleConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        api_path=os.getenv("PMMA_LLM_API_PATH", DEFAULT_OPENAI_COMPATIBLE_PATH).strip()
        or DEFAULT_OPENAI_COMPATIBLE_PATH,
        provider_name=os.getenv("PMMA_LLM_PROVIDER", "openai-compatible").strip()
        or "openai-compatible",
        headers=headers,
    )


def _build_endpoint_url(base_url: str, api_path: str) -> str:
    normalized_base_url = base_url.rstrip("/")
    normalized_api_path = api_path if api_path.startswith("/") else f"/{api_path}"
    if normalized_base_url.endswith(normalized_api_path):
        return normalized_base_url
    return f"{normalized_base_url}{normalized_api_path}"


def _default_transport(url: str, headers: Dict[str, str], body: bytes, timeout_seconds: float) -> str:
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8")


def _extract_content(payload: Dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "".join(chunks)
    return ""


def _env_flag(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in {"1", "true", "yes", "on"}
