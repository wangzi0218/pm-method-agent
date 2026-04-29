from __future__ import annotations

import re
from typing import TYPE_CHECKING, List


if TYPE_CHECKING:
    from pm_method_agent.models import CaseState
    from pm_method_agent.reply_interpreter import ReplyAnalysis


MEMORY_TARGET_LABELS = {
    "project-profile": "项目背景",
    "user-profile": "使用偏好",
    "case-memory": "当前案例",
}


def suggest_memory_write_hints(
    message: str,
    *,
    reply_analysis: "ReplyAnalysis | None" = None,
    active_case: "CaseState | None" = None,
) -> list[dict[str, str]]:
    text = str(message).strip()
    if not text:
        return []

    user_score = _score_user_preference(text)
    project_score = _score_project_background(text, reply_analysis)
    case_score = _score_case_memory(text, reply_analysis, active_case)

    target = ""
    if user_score >= max(project_score, case_score) and user_score >= 4:
        target = "user-profile"
    elif project_score >= case_score and project_score >= 4:
        target = "project-profile"
    elif case_score >= 3:
        target = "case-memory"

    if not target:
        return []

    return [
        {
            "target": target,
            "label": MEMORY_TARGET_LABELS[target],
            "summary": _render_target_summary(target),
            "action_hint": _render_action_hint(target),
            "source_excerpt": _short_text(text, limit=30),
        }
    ]


def _score_user_preference(text: str) -> int:
    lowered = text.lower()
    score = 0
    if any(marker in text for marker in ["我更喜欢", "我习惯", "我希望你", "你直接", "你就直接"]):
        score += 3
    if any(marker in text for marker in ["先给结论", "先说结论", "先结论后展开", "先讲结论", "先说重点"]):
        score += 2
    if any(marker in text for marker in ["简洁", "短一点", "别太长", "口语一点", "别太正式", "中文"]):
        score += 2
    if any(marker in lowered for marker in ["card", "cards", "markdown"]):
        score += 1
    if any(marker in text for marker in ["卡片", "列表", "分点", "结构化"]):
        score += 1
    return score


def _score_project_background(text: str, reply_analysis: "ReplyAnalysis | None") -> int:
    lowered = text.lower()
    score = 0
    if any(
        marker in text
        for marker in [
            "这个项目",
            "这个产品",
            "这是一个",
            "属于",
            "我们团队",
            "我们这边",
            "我们一般",
            "我们默认",
            "长期",
            "一直",
            "通用",
        ]
    ):
        score += 2
    if any(marker in text for marker in ["主要通过", "主要使用", "平时主要", "核心场景", "面向"]):
        score += 2
    if any(marker in text for marker in ["默认", "一直", "长期", "通用", "标准", "习惯上"]):
        score += 2
    if any(
        marker in lowered
        for marker in ["上线", "预算", "资源", "周期", "履约率", "到诊率", "留存", "转化", "gmv", "dau", "合规"]
    ):
        score += 2
    if _has_context_updates(reply_analysis):
        score += 1
    return score


def _score_case_memory(
    text: str,
    reply_analysis: "ReplyAnalysis | None",
    active_case: "CaseState | None",
) -> int:
    score = 0
    if any(marker in text for marker in ["这次", "这轮", "最近", "昨天", "今天", "本周", "这件事", "这个需求"]):
        score += 2
    if re.search(r"\d+\s*(次|个|天|周|月|%)", text):
        score += 2
    if any(category in _reply_categories(reply_analysis) for category in ["evidence", "decision"]):
        score += 1
    if active_case is not None:
        score += 1
    return score


def _has_context_updates(reply_analysis: "ReplyAnalysis | None") -> bool:
    if reply_analysis is None:
        return False
    context_updates = getattr(reply_analysis, "context_updates", {})
    return isinstance(context_updates, dict) and bool(context_updates)


def _reply_categories(reply_analysis: "ReplyAnalysis | None") -> List[str]:
    if reply_analysis is None:
        return []
    categories = getattr(reply_analysis, "categories", [])
    if not isinstance(categories, list):
        return []
    return [str(item).strip() for item in categories if str(item).strip()]


def _render_target_summary(target: str) -> str:
    if target == "project-profile":
        return "更像后面会反复用到的前提。"
    if target == "user-profile":
        return "更像你的稳定协作偏好。"
    return "更像只对这次分析有效的信息。"


def _render_action_hint(target: str) -> str:
    if target == "project-profile":
        return "适合记进项目背景。"
    if target == "user-profile":
        return "适合记进使用偏好。"
    return "先留在当前案例里就行。"


def _short_text(text: str, limit: int = 30) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(limit - 1, 1)].rstrip() + "…"
