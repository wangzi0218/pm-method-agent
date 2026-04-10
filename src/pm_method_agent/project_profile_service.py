from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from pm_method_agent.models import ProjectProfile


PROJECT_PROFILE_STORE_DIRNAME = ".pm_method_agent/project_profiles"


@dataclass
class LocalProjectProfileStore:
    root_dir: Path

    def save(self, project_profile: ProjectProfile) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._profile_path(project_profile.project_profile_id).write_text(
            json.dumps(project_profile.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, project_profile_id: str) -> ProjectProfile:
        profile_path = self._profile_path(project_profile_id)
        if not profile_path.exists():
            raise FileNotFoundError(f"Project profile '{project_profile_id}' does not exist.")
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        return ProjectProfile.from_dict(payload)

    def _profile_path(self, project_profile_id: str) -> Path:
        return self.root_dir / f"{project_profile_id}.json"


def default_project_profile_store(base_dir: Optional[str] = None) -> LocalProjectProfileStore:
    root_dir = Path(base_dir or ".").resolve() / PROJECT_PROFILE_STORE_DIRNAME
    return LocalProjectProfileStore(root_dir=root_dir)


def create_project_profile(
    project_name: str,
    context_profile: Optional[Dict[str, object]] = None,
    stable_constraints: Optional[list[str]] = None,
    success_metrics: Optional[list[str]] = None,
    notes: Optional[list[str]] = None,
    project_profile_id: Optional[str] = None,
    store: Optional[LocalProjectProfileStore] = None,
) -> ProjectProfile:
    active_store = store or default_project_profile_store()
    profile = ProjectProfile(
        project_profile_id=project_profile_id or _generate_project_profile_id(),
        project_name=project_name.strip(),
        context_profile=dict(context_profile or {}),
        stable_constraints=list(stable_constraints or []),
        success_metrics=list(success_metrics or []),
        notes=list(notes or []),
    )
    active_store.save(profile)
    return profile


def get_project_profile(
    project_profile_id: str,
    store: Optional[LocalProjectProfileStore] = None,
) -> ProjectProfile:
    active_store = store or default_project_profile_store()
    return active_store.load(project_profile_id)


def update_project_profile(
    project_profile_id: str,
    context_profile_updates: Optional[Dict[str, object]] = None,
    stable_constraints: Optional[list[str]] = None,
    success_metrics: Optional[list[str]] = None,
    notes: Optional[list[str]] = None,
    project_name: Optional[str] = None,
    store: Optional[LocalProjectProfileStore] = None,
) -> ProjectProfile:
    active_store = store or default_project_profile_store()
    project_profile = active_store.load(project_profile_id)
    if project_name and project_name.strip():
        project_profile.project_name = project_name.strip()
    project_profile.context_profile = merge_project_profile_context(
        project_profile,
        context_profile_updates,
        source_text="\n".join(notes or []),
    )
    for item in stable_constraints or []:
        normalized = item.strip()
        if normalized and normalized not in project_profile.stable_constraints:
            project_profile.stable_constraints.append(normalized)
    for item in success_metrics or []:
        normalized = item.strip()
        if normalized and normalized not in project_profile.success_metrics:
            project_profile.success_metrics.append(normalized)
    for item in notes or []:
        normalized = item.strip()
        if normalized and normalized not in project_profile.notes:
            project_profile.notes.append(normalized)
    active_store.save(project_profile)
    return project_profile


def merge_project_profile_context(
    project_profile: Optional[ProjectProfile],
    context_profile_updates: Optional[Dict[str, object]],
    source_text: str = "",
) -> Dict[str, object]:
    merged = dict(project_profile.context_profile if project_profile else {})
    if not context_profile_updates:
        return merged
    for key, value in context_profile_updates.items():
        if key in {"target_user_roles", "constraints"}:
            next_items = []
            if _should_replace_list_context(key, source_text):
                for item in list(value):
                    if item not in next_items:
                        next_items.append(item)
            else:
                current_items = list(merged.get(key, []))
                for item in list(value):
                    if item not in current_items:
                        current_items.append(item)
                next_items = current_items
            merged[key] = next_items
            continue
        merged[key] = value
    return merged


def _generate_project_profile_id() -> str:
    return f"profile-{uuid4().hex[:8]}"


def _should_replace_list_context(key: str, source_text: str) -> bool:
    if key != "target_user_roles":
        return False
    return _has_explicit_correction_signal(source_text)


def _has_explicit_correction_signal(source_text: str) -> bool:
    text = source_text.strip()
    if not text:
        return False
    correction_patterns = [
        "不是",
        "而是",
        "其实是",
        "其实不是",
        "更准确说",
        "准确说",
        "刚确认",
        "修正一下",
        "改成",
    ]
    return any(pattern in text for pattern in correction_patterns)
