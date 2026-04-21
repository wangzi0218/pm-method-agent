from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from pm_method_agent.llm_adapter import load_openai_compatible_config_from_env


_LOADED_ENV_ROOTS: set[str] = set()


def ensure_local_env_loaded(base_dir: Optional[str] = None) -> None:
    if _env_flag("PMMA_DISABLE_ENV_AUTOLOAD"):
        return
    root = Path(base_dir or ".").resolve()
    root_key = str(root)
    if root_key in _LOADED_ENV_ROOTS:
        return

    existing_env_keys = set(os.environ.keys())
    for filename in [".env", ".env.local"]:
        file_path = root / filename
        if not file_path.exists() or not file_path.is_file():
            continue
        for key, value in _read_env_file(file_path).items():
            if key in existing_env_keys:
                continue
            os.environ[key] = value

    _LOADED_ENV_ROOTS.add(root_key)


def get_llm_runtime_status(base_dir: Optional[str] = None) -> Dict[str, object]:
    ensure_local_env_loaded(base_dir=base_dir)
    config = load_openai_compatible_config_from_env()
    components: list[str] = []
    if config is not None:
        components.extend(["reply-interpreter", "pre-framing"])
        if _env_flag("PMMA_LLM_COPYWRITER_ENABLED"):
            components.append("copywriter")
        if _env_flag("PMMA_LLM_FOLLOW_UP_COPYWRITER_ENABLED"):
            components.append("follow-up-copywriter")

    mode = "hybrid" if components else "local-only"
    return {
        "mode": mode,
        "components": components,
        "provider": getattr(config, "provider_name", "") if config is not None else "",
        "model": getattr(config, "model", "") if config is not None else "",
        "summary": _build_runtime_summary(mode=mode, components=components),
    }


def _read_env_file(path: Path) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            continue
        normalized_value = value.strip().strip('"').strip("'")
        parsed[normalized_key] = normalized_value
    return parsed


def _env_flag(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in {"1", "true", "yes", "on"}


def _build_runtime_summary(mode: str, components: list[str]) -> str:
    if mode == "local-only":
        return "本地规则"
    labels = {
        "reply-interpreter": "回复解释",
        "pre-framing": "前置收敛",
        "copywriter": "文案增强",
        "follow-up-copywriter": "追问润色",
    }
    rendered_components = "、".join(labels.get(item, item) for item in components)
    return f"LLM 混合（{rendered_components}）"
