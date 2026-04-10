from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from pm_method_agent.models import WorkspaceState


WORKSPACE_STORE_DIRNAME = ".pm_method_agent/workspaces"
RECENT_CASE_LIMIT = 10


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


def update_workspace_approval_preferences(
    workspace_state: WorkspaceState,
    *,
    auto_approve_actions: Optional[list[str]] = None,
) -> WorkspaceState:
    workspace_state.metadata["approval_preferences"] = {
        "auto_approve_actions": _normalize_string_list(auto_approve_actions),
    }
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
