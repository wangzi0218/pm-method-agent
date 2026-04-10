from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pm_method_agent.rule_loader import load_rule_set


@dataclass
class PromptComposition:
    identity: str
    behavior_rules: List[str] = field(default_factory=list)
    tool_constraints: List[str] = field(default_factory=list)
    output_discipline: List[str] = field(default_factory=list)
    project_instructions: List[str] = field(default_factory=list)
    custom_append: List[str] = field(default_factory=list)
    agent_role: str = ""
    task_instruction: str = ""
    rule_sources: List[str] = field(default_factory=list)

    def render(self) -> str:
        sections: List[str] = []
        sections.append("[身份描述]")
        sections.append(self.identity.strip())

        if self.agent_role.strip():
            sections.append("")
            sections.append("[角色职责]")
            sections.append(self.agent_role.strip())

        if self.behavior_rules:
            sections.append("")
            sections.append("[行为规则]")
            sections.extend(f"- {item}" for item in self.behavior_rules if item.strip())

        if self.tool_constraints:
            sections.append("")
            sections.append("[工具约束]")
            sections.extend(f"- {item}" for item in self.tool_constraints if item.strip())

        if self.output_discipline:
            sections.append("")
            sections.append("[输出纪律]")
            sections.extend(f"- {item}" for item in self.output_discipline if item.strip())

        if self.project_instructions:
            sections.append("")
            sections.append("[项目规则]")
            sections.extend(f"- {item}" for item in self.project_instructions if item.strip())

        if self.custom_append:
            sections.append("")
            sections.append("[追加要求]")
            sections.extend(f"- {item}" for item in self.custom_append if item.strip())

        if self.task_instruction.strip():
            sections.append("")
            sections.append("[任务目标]")
            sections.append(self.task_instruction.strip())

        return "\n".join(sections).strip()

    def metadata(self) -> Dict[str, object]:
        return {
            "layers": {
                "identity": bool(self.identity.strip()),
                "agent_role": bool(self.agent_role.strip()),
                "behavior_rules": len([item for item in self.behavior_rules if item.strip()]),
                "tool_constraints": len([item for item in self.tool_constraints if item.strip()]),
                "output_discipline": len([item for item in self.output_discipline if item.strip()]),
                "project_instructions": len([item for item in self.project_instructions if item.strip()]),
                "custom_append": len([item for item in self.custom_append if item.strip()]),
                "task_instruction": bool(self.task_instruction.strip()),
            },
            "priority_order": [
                "behavior_rules",
                "tool_constraints",
                "output_discipline",
                "project_instructions",
                "custom_append",
                "task_instruction",
            ],
            "rule_sources": self.rule_sources,
        }


def build_prompt_composition(
    *,
    identity: str,
    behavior_rules: Optional[List[str]] = None,
    tool_constraints: Optional[List[str]] = None,
    output_discipline: Optional[List[str]] = None,
    agent_role: str = "",
    task_instruction: str = "",
    project_instructions: Optional[List[str]] = None,
    custom_append: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
) -> PromptComposition:
    env_overrides = load_prompt_layer_overrides_from_env()
    loaded_rules = load_rule_set(base_dir=base_dir)
    return PromptComposition(
        identity=identity,
        behavior_rules=loaded_rules.behavior_rules + list(behavior_rules or []),
        tool_constraints=loaded_rules.tool_constraints + list(tool_constraints or []),
        output_discipline=loaded_rules.output_discipline + list(output_discipline or []),
        project_instructions=(
            loaded_rules.project_instructions
            + list(project_instructions or [])
            + env_overrides["project_instructions"]
        ),
        custom_append=loaded_rules.custom_append + list(custom_append or []) + env_overrides["custom_append"],
        agent_role=agent_role,
        task_instruction=task_instruction,
        rule_sources=list(loaded_rules.sources),
    )


def load_prompt_layer_overrides_from_env() -> Dict[str, List[str]]:
    return {
        "project_instructions": _split_prompt_env("PMMA_PROMPT_PROJECT"),
        "custom_append": _split_prompt_env("PMMA_PROMPT_APPEND"),
    }


def _split_prompt_env(key: str) -> List[str]:
    raw_value = os.getenv(key, "").strip()
    if not raw_value:
        return []
    normalized = raw_value.replace("\r\n", "\n")
    items = [item.strip() for item in normalized.split("\n") if item.strip()]
    return items
