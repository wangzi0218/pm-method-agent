from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from pm_method_agent.models import WorkspaceState


WORKSPACE_STORE_DIRNAME = ".pm_method_agent/workspaces"
RECENT_CASE_LIMIT = 10
USER_PROFILE_KEYS = [
    "preferred_output_style",
    "preferred_language",
    "decision_style",
    "frequent_product_domains",
    "common_constraints",
]


@dataclass
class LocalWorkspaceStore:
    root_dir: Path

    def save(self, workspace_state: WorkspaceState) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._workspace_path(workspace_state.workspace_id).write_text(
            json.dumps(workspace_state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, workspace_id: str) -> WorkspaceState:
        workspace_path = self._workspace_path(workspace_id)
        if not workspace_path.exists():
            raise FileNotFoundError(f"Workspace '{workspace_id}' does not exist.")
        payload = json.loads(workspace_path.read_text(encoding="utf-8"))
        return WorkspaceState.from_dict(payload)

    def exists(self, workspace_id: str) -> bool:
        return self._workspace_path(workspace_id).exists()

    def _workspace_path(self, workspace_id: str) -> Path:
        return self.root_dir / f"{workspace_id}.json"


def default_workspace_store(base_dir: Optional[str] = None) -> LocalWorkspaceStore:
    root_dir = Path(base_dir or ".").resolve() / WORKSPACE_STORE_DIRNAME
    return LocalWorkspaceStore(root_dir=root_dir)


def get_or_create_workspace(
    workspace_id: str = "default",
    store: Optional[LocalWorkspaceStore] = None,
) -> WorkspaceState:
    active_store = store or default_workspace_store()
    if active_store.exists(workspace_id):
        return active_store.load(workspace_id)
    workspace = WorkspaceState(workspace_id=workspace_id)
    active_store.save(workspace)
    return workspace


def save_workspace(
    workspace_state: WorkspaceState,
    store: Optional[LocalWorkspaceStore] = None,
) -> WorkspaceState:
    active_store = store or default_workspace_store()
    active_store.save(workspace_state)
    return workspace_state


def activate_workspace_case(
    workspace_state: WorkspaceState,
    case_id: str,
) -> WorkspaceState:
    workspace_state.active_case_id = case_id
    if case_id in workspace_state.recent_case_ids:
        workspace_state.recent_case_ids.remove(case_id)
    workspace_state.recent_case_ids.insert(0, case_id)
    workspace_state.recent_case_ids = workspace_state.recent_case_ids[:RECENT_CASE_LIMIT]
    return workspace_state


def get_workspace_approval_preferences(workspace_state: WorkspaceState) -> Dict[str, object]:
    raw_preferences = workspace_state.metadata.get("approval_preferences")
    if not isinstance(raw_preferences, dict):
        return {"auto_approve_actions": []}
    return {
        "auto_approve_actions": _normalize_string_list(raw_preferences.get("auto_approve_actions")),
    }


def get_workspace_user_profile(workspace_state: WorkspaceState) -> Dict[str, object]:
    raw_profile = workspace_state.metadata.get("user_profile")
    if not isinstance(raw_profile, dict):
        return {}
    normalized: Dict[str, object] = {}
    for key in USER_PROFILE_KEYS:
        value = raw_profile.get(key)
        if key in {"frequent_product_domains", "common_constraints"}:
            items = _normalize_string_list(value)
            if items:
                normalized[key] = items
            continue
        rendered = str(value).strip() if value is not None else ""
        if rendered:
            normalized[key] = rendered
    return normalized


def update_workspace_approval_preferences(
    workspace_state: WorkspaceState,
    *,
    auto_approve_actions: Optional[list[str]] = None,
) -> WorkspaceState:
    workspace_state.metadata["approval_preferences"] = {
        "auto_approve_actions": _normalize_string_list(auto_approve_actions),
    }
    return workspace_state


def update_workspace_user_profile(
    workspace_state: WorkspaceState,
    *,
    preferred_output_style: Optional[str] = None,
    preferred_language: Optional[str] = None,
    decision_style: Optional[str] = None,
    frequent_product_domains: Optional[list[str]] = None,
    common_constraints: Optional[list[str]] = None,
) -> WorkspaceState:
    current = get_workspace_user_profile(workspace_state)
    updates = {
        "preferred_output_style": preferred_output_style,
        "preferred_language": preferred_language,
        "decision_style": decision_style,
    }
    for key, value in updates.items():
        rendered = str(value).strip() if value is not None else ""
        if rendered:
            current[key] = rendered
    domain_items = _normalize_string_list(frequent_product_domains)
    if domain_items:
        current["frequent_product_domains"] = domain_items
    constraint_items = _normalize_string_list(common_constraints)
    if constraint_items:
        current["common_constraints"] = constraint_items
    if current:
        workspace_state.metadata["user_profile"] = current
    else:
        workspace_state.metadata.pop("user_profile", None)
    return workspace_state


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        rendered = str(item).strip()
        if rendered and rendered not in normalized:
            normalized.append(rendered)
    return normalized
