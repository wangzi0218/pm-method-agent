from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pm_method_agent.rule_loader import load_rule_set


@dataclass
class RuntimePolicy:
    blocked_intents: List[str] = field(default_factory=list)
    blocked_actions: List[str] = field(default_factory=list)
    allow_new_cases: bool = True
    allow_case_switching: bool = True
    allow_project_profile_updates: bool = True
    sources: List[str] = field(default_factory=list)


@dataclass
class RuntimePolicyViolation:
    intent: str
    terminal_state: str
    reason: str


def load_runtime_policy(base_dir: Optional[str] = None) -> RuntimePolicy:
    loaded_rules = load_rule_set(base_dir=base_dir)
    raw_policy = loaded_rules.runtime_policy if isinstance(loaded_rules.runtime_policy, dict) else {}

    return RuntimePolicy(
        blocked_intents=_normalize_string_list(raw_policy.get("blocked_intents")),
        blocked_actions=_normalize_string_list(raw_policy.get("blocked_actions")),
        allow_new_cases=_normalize_bool(raw_policy.get("allow_new_cases"), default=True),
        allow_case_switching=_normalize_bool(raw_policy.get("allow_case_switching"), default=True),
        allow_project_profile_updates=_normalize_bool(
            raw_policy.get("allow_project_profile_updates"),
            default=True,
        ),
        sources=list(loaded_rules.sources),
    )


def check_runtime_policy(
    policy: RuntimePolicy,
    *,
    intent: str,
) -> Optional[RuntimePolicyViolation]:
    if intent in policy.blocked_intents:
        return RuntimePolicyViolation(
            intent=intent,
            terminal_state="cancelled",
            reason="当前项目规则里，这类操作被禁用了。",
        )
    if intent == "new-case" and not policy.allow_new_cases:
        return RuntimePolicyViolation(
            intent=intent,
            terminal_state="blocked",
            reason="当前项目规则要求先在现有案例里继续，不允许直接新建案例。",
        )
    if intent == "switch-case" and not policy.allow_case_switching:
        return RuntimePolicyViolation(
            intent=intent,
            terminal_state="cancelled",
            reason="当前项目规则不允许在这里切换案例。",
        )
    if intent == "project-background" and not policy.allow_project_profile_updates:
        return RuntimePolicyViolation(
            intent=intent,
            terminal_state="blocked",
            reason="当前项目规则不允许直接改写项目背景。",
        )
    return None


def _normalize_string_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        rendered = item.strip()
        if rendered and rendered not in normalized:
            normalized.append(rendered)
    return normalized


def _normalize_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default
