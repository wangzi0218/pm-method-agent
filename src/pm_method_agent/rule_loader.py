from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


RULE_MARKDOWN_FILENAMES = [
    "AGENTS.md",
    "PMMA.md",
    "agent.md",
]

RULE_DIRECTORY_FILENAMES = [
    ".pmma/rules.md",
    ".pmma/project-rules.md",
]

RULE_POLICY_FILENAMES = [
    ".pmma/policy.json",
]


@dataclass
class LoadedRuleSet:
    behavior_rules: List[str] = field(default_factory=list)
    tool_constraints: List[str] = field(default_factory=list)
    output_discipline: List[str] = field(default_factory=list)
    project_instructions: List[str] = field(default_factory=list)
    custom_append: List[str] = field(default_factory=list)
    runtime_policy: Dict[str, object] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)


def load_rule_set(base_dir: Optional[str] = None) -> LoadedRuleSet:
    resolved_base_dir = Path(base_dir or os.getenv("PMMA_RULES_BASE_DIR", ".")).resolve()
    loaded = LoadedRuleSet()

    user_rule_path = _resolve_user_rule_path()
    if user_rule_path is not None and user_rule_path.exists():
        _merge_rule_set(loaded, _load_markdown_rules(user_rule_path), source=str(user_rule_path))

    for directory in _iter_directories_from_root(resolved_base_dir):
        for filename in RULE_MARKDOWN_FILENAMES:
            candidate = directory / filename
            if candidate.exists() and candidate.is_file():
                _merge_rule_set(loaded, _load_markdown_rules(candidate), source=str(candidate))
        for filename in RULE_DIRECTORY_FILENAMES:
            candidate = directory / filename
            if candidate.exists() and candidate.is_file():
                _merge_rule_set(loaded, _load_markdown_rules(candidate), source=str(candidate))
        for filename in RULE_POLICY_FILENAMES:
            candidate = directory / filename
            if candidate.exists() and candidate.is_file():
                _merge_rule_set(loaded, _load_policy_rules(candidate), source=str(candidate))

    return loaded


def _resolve_user_rule_path() -> Optional[Path]:
    explicit = os.getenv("PMMA_USER_RULES_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    home = Path.home()
    candidate = home / ".pmma" / "user-rules.md"
    return candidate


def _iter_directories_from_root(base_dir: Path) -> List[Path]:
    directories = list(reversed([base_dir, *base_dir.parents]))
    deduped: List[Path] = []
    for item in directories:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _merge_rule_set(target: LoadedRuleSet, incoming: LoadedRuleSet, *, source: str) -> None:
    if source and source not in target.sources:
        target.sources.append(source)
    for key in [
        "behavior_rules",
        "tool_constraints",
        "output_discipline",
        "project_instructions",
        "custom_append",
    ]:
        current_items = getattr(target, key)
        for item in getattr(incoming, key):
            if item not in current_items:
                current_items.append(item)
    if incoming.runtime_policy:
        target.runtime_policy.update(incoming.runtime_policy)


def _load_markdown_rules(path: Path) -> LoadedRuleSet:
    content = path.read_text(encoding="utf-8")
    section_map = {
        "behavior_rules": ["行为规则", "行为约束"],
        "tool_constraints": ["工具约束", "工具规则", "危险动作"],
        "output_discipline": ["输出纪律", "输出要求", "输出规范"],
        "project_instructions": ["项目规则", "仓库规则", "目录规则", "团队规则"],
        "custom_append": ["追加要求", "临时要求"],
    }
    if any(marker in content for markers in section_map.values() for marker in markers):
        return _parse_sectioned_markdown(content, section_map)
    fallback_items = _extract_markdown_items(content)
    return LoadedRuleSet(project_instructions=fallback_items)


def _parse_sectioned_markdown(content: str, section_map: Dict[str, List[str]]) -> LoadedRuleSet:
    loaded = LoadedRuleSet()
    current_key = "project_instructions"
    in_code_block = False
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not stripped:
            continue
        heading_text = _extract_markdown_heading_text(stripped)
        if heading_text:
            matched_key = _match_section_key(heading_text, section_map)
            if matched_key:
                current_key = matched_key
                continue
        item = _extract_markdown_item(stripped)
        if not item:
            continue
        bucket = getattr(loaded, current_key)
        if item not in bucket:
            bucket.append(item)
    return loaded


def _load_policy_rules(path: Path) -> LoadedRuleSet:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return LoadedRuleSet()
    if not isinstance(payload, dict):
        return LoadedRuleSet()
    loaded = LoadedRuleSet()
    for key in [
        "behavior_rules",
        "tool_constraints",
        "output_discipline",
        "project_instructions",
        "custom_append",
    ]:
        items = payload.get(key, [])
        if not isinstance(items, list):
            continue
        bucket = getattr(loaded, key)
        for item in items:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if normalized and normalized not in bucket:
                bucket.append(normalized)
    runtime_policy = payload.get("runtime_policy", {})
    if isinstance(runtime_policy, dict):
        loaded.runtime_policy = dict(runtime_policy)
    return loaded


def _extract_markdown_items(content: str) -> List[str]:
    items: List[str] = []
    in_code_block = False
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not stripped or stripped.startswith("#"):
            continue
        item = _extract_markdown_item(stripped)
        if item and item not in items:
            items.append(item)
    return items


def _extract_markdown_heading_text(stripped: str) -> str:
    if stripped.startswith("#"):
        return stripped.lstrip("#").strip()
    section_match = re.fullmatch(r"\[(.+?)\]", stripped)
    if section_match:
        return section_match.group(1).strip()
    return ""


def _match_section_key(heading_text: str, section_map: Dict[str, List[str]]) -> str:
    for key, headings in section_map.items():
        if any(marker in heading_text for marker in headings):
            return key
    return ""


def _extract_markdown_item(stripped: str) -> str:
    if stripped.startswith(("- ", "* ")):
        return stripped[2:].strip()
    ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
    if ordered_match:
        return ordered_match.group(1).strip()
    if stripped.startswith(">"):
        return stripped.lstrip(">").strip()
    return stripped.strip()
