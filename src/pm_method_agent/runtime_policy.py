from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from pm_method_agent.rule_loader import load_rule_set


@dataclass
class RuntimePolicy:
    base_dir: str = ""
    blocked_intents: List[str] = field(default_factory=list)
    blocked_actions: List[str] = field(default_factory=list)
    approval_required_actions: List[str] = field(default_factory=list)
    command_allowlist_prefixes: List[str] = field(default_factory=list)
    blocked_command_patterns: List[str] = field(default_factory=list)
    approval_required_command_patterns: List[str] = field(default_factory=list)
    allowed_write_roots: List[str] = field(default_factory=list)
    blocked_write_paths: List[str] = field(default_factory=list)
    approval_required_write_paths: List[str] = field(default_factory=list)
    allow_new_cases: bool = True
    allow_case_switching: bool = True
    allow_project_profile_updates: bool = True
    sources: List[str] = field(default_factory=list)


@dataclass
class RuntimePolicyViolation:
    terminal_state: str
    reason: str
    violation_kind: str = "blocked"
    intent: str = ""
    action_name: str = ""
    command_preview: str = ""
    write_path: str = ""


def load_runtime_policy(base_dir: Optional[str] = None) -> RuntimePolicy:
    resolved_base_dir = str(Path(base_dir or ".").resolve())
    loaded_rules = load_rule_set(base_dir=base_dir)
    raw_policy = loaded_rules.runtime_policy if isinstance(loaded_rules.runtime_policy, dict) else {}

    return RuntimePolicy(
        base_dir=resolved_base_dir,
        blocked_intents=_normalize_string_list(raw_policy.get("blocked_intents")),
        blocked_actions=_normalize_string_list(raw_policy.get("blocked_actions")),
        approval_required_actions=_normalize_string_list(raw_policy.get("approval_required_actions")),
        command_allowlist_prefixes=_normalize_string_list(raw_policy.get("command_allowlist_prefixes")),
        blocked_command_patterns=_normalize_string_list(raw_policy.get("blocked_command_patterns")),
        approval_required_command_patterns=_normalize_string_list(
            raw_policy.get("approval_required_command_patterns")
        ),
        allowed_write_roots=_normalize_path_list(
            raw_policy.get("allowed_write_roots"),
            base_dir=resolved_base_dir,
        ),
        blocked_write_paths=_normalize_string_list(raw_policy.get("blocked_write_paths")),
        approval_required_write_paths=_normalize_string_list(raw_policy.get("approval_required_write_paths")),
        allow_new_cases=_normalize_bool(raw_policy.get("allow_new_cases"), default=True),
        allow_case_switching=_normalize_bool(raw_policy.get("allow_case_switching"), default=True),
        allow_project_profile_updates=_normalize_bool(
            raw_policy.get("allow_project_profile_updates"),
            default=True,
        ),
        sources=list(loaded_rules.sources),
    )


def runtime_policy_to_dict(policy: RuntimePolicy) -> dict:
    return {
        "base_dir": policy.base_dir,
        "blocked_intents": list(policy.blocked_intents),
        "blocked_actions": list(policy.blocked_actions),
        "approval_required_actions": list(policy.approval_required_actions),
        "command_allowlist_prefixes": list(policy.command_allowlist_prefixes),
        "blocked_command_patterns": list(policy.blocked_command_patterns),
        "approval_required_command_patterns": list(policy.approval_required_command_patterns),
        "allowed_write_roots": list(policy.allowed_write_roots),
        "blocked_write_paths": list(policy.blocked_write_paths),
        "approval_required_write_paths": list(policy.approval_required_write_paths),
        "allow_new_cases": policy.allow_new_cases,
        "allow_case_switching": policy.allow_case_switching,
        "allow_project_profile_updates": policy.allow_project_profile_updates,
        "sources": list(policy.sources),
    }


def check_runtime_policy(
    policy: RuntimePolicy,
    *,
    intent: str,
) -> Optional[RuntimePolicyViolation]:
    if intent in policy.blocked_intents:
        return RuntimePolicyViolation(
            terminal_state="cancelled",
            reason="当前项目规则里，这类操作被禁用了。",
            violation_kind="blocked",
            intent=intent,
        )
    if intent == "new-case" and not policy.allow_new_cases:
        return RuntimePolicyViolation(
            terminal_state="blocked",
            reason="当前项目规则要求先在现有案例里继续，不允许直接新建案例。",
            violation_kind="blocked",
            intent=intent,
        )
    if intent == "switch-case" and not policy.allow_case_switching:
        return RuntimePolicyViolation(
            terminal_state="cancelled",
            reason="当前项目规则不允许在这里切换案例。",
            violation_kind="blocked",
            intent=intent,
        )
    if intent == "project-background" and not policy.allow_project_profile_updates:
        return RuntimePolicyViolation(
            terminal_state="blocked",
            reason="当前项目规则不允许直接改写项目背景。",
            violation_kind="blocked",
            intent=intent,
        )
    return None


def check_runtime_action_policy(
    policy: RuntimePolicy,
    *,
    action_name: str,
) -> Optional[RuntimePolicyViolation]:
    if _matches_policy_items(action_name, policy.blocked_actions):
        return RuntimePolicyViolation(
            terminal_state="blocked",
            reason=f"当前项目规则不允许执行这个动作：{action_name}。",
            violation_kind="blocked",
            action_name=action_name,
        )
    if _matches_policy_items(action_name, policy.approval_required_actions):
        return RuntimePolicyViolation(
            terminal_state="blocked",
            reason=f"这个动作在当前项目规则里需要先人工确认：{action_name}。",
            violation_kind="approval-required",
            action_name=action_name,
        )
    return None


def check_runtime_command_policy(
    policy: RuntimePolicy,
    *,
    command_args: List[str],
) -> Optional[RuntimePolicyViolation]:
    normalized_args = [item.strip() for item in command_args if item.strip()]
    if not normalized_args:
        return None
    command_preview = " ".join(normalized_args)
    if _matches_command_patterns(normalized_args, policy.blocked_command_patterns):
        return RuntimePolicyViolation(
            terminal_state="blocked",
            reason=f"当前项目规则不允许执行这个命令：{command_preview}。",
            violation_kind="blocked",
            command_preview=command_preview,
        )
    if _matches_command_patterns(normalized_args, policy.approval_required_command_patterns):
        return RuntimePolicyViolation(
            terminal_state="blocked",
            reason=f"这个命令在当前项目规则里需要先人工确认：{command_preview}。",
            violation_kind="approval-required",
            command_preview=command_preview,
        )
    if policy.command_allowlist_prefixes and not _matches_command_prefixes(
        normalized_args,
        policy.command_allowlist_prefixes,
    ):
        return RuntimePolicyViolation(
            terminal_state="blocked",
            reason=f"当前项目规则不允许执行这个命令：{command_preview}。",
            violation_kind="blocked",
            command_preview=command_preview,
        )
    return None


def check_runtime_write_policy(
    policy: RuntimePolicy,
    *,
    write_paths: List[str],
) -> Optional[RuntimePolicyViolation]:
    for raw_path in write_paths:
        normalized_path = _normalize_candidate_path(raw_path, base_dir=policy.base_dir)
        if _matches_path_patterns(normalized_path, policy.blocked_write_paths, base_dir=policy.base_dir):
            return RuntimePolicyViolation(
                terminal_state="blocked",
                reason=f"当前项目规则不允许写入这个路径：{normalized_path}。",
                violation_kind="blocked",
                write_path=normalized_path,
            )
        if _matches_path_patterns(
            normalized_path,
            policy.approval_required_write_paths,
            base_dir=policy.base_dir,
        ):
            return RuntimePolicyViolation(
                terminal_state="blocked",
                reason=f"这个路径在当前项目规则里需要先人工确认：{normalized_path}。",
                violation_kind="approval-required",
                write_path=normalized_path,
            )
        if policy.allowed_write_roots and not _is_under_allowed_roots(
            normalized_path,
            policy.allowed_write_roots,
        ):
            return RuntimePolicyViolation(
                terminal_state="blocked",
                reason=f"当前项目规则不允许写入这个路径：{normalized_path}。",
                violation_kind="blocked",
                write_path=normalized_path,
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


def _matches_policy_items(name: str, patterns: List[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatchcase(name, pattern):
            return True
    return False


def _matches_command_patterns(command_args: List[str], patterns: List[str]) -> bool:
    if not patterns:
        return False
    command_preview = " ".join(command_args)
    head = command_args[0]
    for pattern in patterns:
        if fnmatch.fnmatchcase(command_preview, pattern):
            return True
        if " " not in pattern and fnmatch.fnmatchcase(head, pattern):
            return True
    return False


def _matches_command_prefixes(command_args: List[str], prefixes: List[str]) -> bool:
    for prefix in prefixes:
        prefix_tokens = [item for item in prefix.strip().split(" ") if item]
        if not prefix_tokens:
            continue
        if command_args[: len(prefix_tokens)] == prefix_tokens:
            return True
    return False


def _normalize_path_list(value: object, *, base_dir: str) -> List[str]:
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        path = _normalize_candidate_path(item, base_dir=base_dir)
        if path not in normalized:
            normalized.append(path)
    return normalized


def _normalize_candidate_path(path: str, *, base_dir: str) -> str:
    stripped = path.strip()
    if not stripped:
        return ""
    candidate = Path(stripped).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve())
    return str((Path(base_dir) / candidate).resolve())


def _is_under_allowed_roots(path: str, allowed_roots: List[str]) -> bool:
    candidate = Path(path)
    for root in allowed_roots:
        try:
            candidate.relative_to(Path(root))
            return True
        except ValueError:
            continue
    return False


def _matches_path_patterns(path: str, patterns: List[str], *, base_dir: str) -> bool:
    candidate = Path(path)
    for pattern in patterns:
        normalized_pattern = pattern.strip()
        if not normalized_pattern:
            continue
        resolved_pattern = normalized_pattern
        if not Path(normalized_pattern).is_absolute():
            resolved_pattern = str((Path(base_dir) / normalized_pattern).resolve())
        if fnmatch.fnmatchcase(path, resolved_pattern):
            return True
        try:
            relative_path = str(candidate.relative_to(Path(base_dir)))
        except ValueError:
            relative_path = path
        if fnmatch.fnmatchcase(relative_path, normalized_pattern):
            return True
    return False
