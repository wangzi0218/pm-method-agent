from __future__ import annotations

import re
from typing import Dict, List


COMMON_ROLE_TERMS = [
    "前台",
    "诊所前台",
    "店长",
    "门店店长",
    "门店负责人",
    "诊所管理者",
    "管理者",
    "管理员",
    "负责人",
    "核心医生",
    "医生",
    "护士",
    "运营",
    "内容运营",
    "增长运营",
    "运营人员",
    "审批专员",
    "审核专员",
    "审核同学",
    "店员",
    "商家",
    "部门负责人",
    "新用户",
    "老用户",
    "患者",
    "老板",
    "老板/经营者",
    "院长",
    "采购负责人",
    "采购",
]

ROLE_SUFFIXES = [
    "前台",
    "店长",
    "负责人",
    "管理者",
    "管理员",
    "医生",
    "护士",
    "运营",
    "专员",
    "主管",
    "经理",
    "老板",
    "院长",
    "用户",
    "患者",
    "客服",
    "店员",
    "顾问",
    "助理",
]

ROLE_SIGNAL_PATTERNS = [
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提出(?:了)?需求",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提(?:了)?需求",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提(?:的|了这个事)",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})反馈",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})在使用(?:产品|系统|服务)?",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})使用(?:产品|系统|服务)?",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})在日常操作里",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})每天在用",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})对结果负责",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})会对结果负责",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})负责结果",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})盯结果",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})拍板",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})更关注",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})关心",
    r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})希望",
]

ROLE_RELATION_PATTERNS = {
    "proposers": [
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提出(?:了)?需求",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提(?:了)?需求",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提(?:了)?这个需求",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提(?:的|了这个事)",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})反馈",
        r"这个需求是(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提出来的",
        r"这个需求是(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})提出的需求",
    ],
    "users": [
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})在使用(?:产品|系统|服务)?",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})使用(?:产品|系统|服务)?",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})会使用(?:产品|系统|服务)?",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})在[^，。；]{0,8}操作",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})操作(?:这个动作|这一步|这个流程|提醒动作|流程)?",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})自己.*操作",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})在日常操作里",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})在用",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})每天在用",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})一线在用",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})在处理",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})直接操作",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})直接使用",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})来处理",
    ],
    "outcome_owners": [
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})对结果负责",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})会对结果负责",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})负责结果",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})盯结果",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})背结果",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})拍板",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})更关注",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})会看结果",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})看结果",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})决定是否上线",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})决定要不要上线",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})决定是否做",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})决定要不要做",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})决定是否采购",
    ],
}

RELATION_NEGATION_PATTERNS = {
    "users": [
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不直接操作",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不操作",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不直接使用",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不使用",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不在用",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不直接处理",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不是使用者",
    ],
    "outcome_owners": [
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不对结果负责",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不负责结果",
        r"(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})不拍板",
    ],
}

NEGATED_ROLE_PATTERNS = [
    r"不是(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})",
    r"不再由(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})",
    r"不再是(?P<role>[\u4e00-\u9fffA-Za-z]{1,12})",
]

ROLE_CLEANUP_PREFIXES = [
    "核心不是",
    "核心是",
    "不是",
    "是",
    "一线",
    "这是",
    "最近",
    "当前",
    "主要",
    "这个需求是",
    "这个事是",
    "这件事是",
    "该需求是",
    "这个需求由",
    "这个事由",
    "这件事由",
    "这个需求",
    "这个事",
    "这件事",
    "该需求",
    "需求是",
    "每一个诊所的",
    "每个诊所的",
    "一个诊所的",
    "个诊所的",
    "诊所的",
    "当前这个项目",
    "当前项目",
    "这个项目",
    "这个产品",
    "用户主要的场景还是通过",
    "主要的场景还是通过",
]

ROLE_INVALID_PARTS = [
    "经常",
    "漏掉",
    "提醒",
    "影响",
    "处理",
    "通过",
    "提供",
    "能力",
    "问题",
    "流程",
    "场景",
    "网页端",
    "小程序",
    "app",
    "App",
    "不直接",
    "不操作",
    "不使用",
    "不",
]

ROLE_NORMALIZATION = {
    "老板/经营者": "老板",
    "运营人员": "运营",
    "内容运营": "运营",
    "增长运营": "运营",
    "诊所前台": "前台",
    "前台员工": "前台",
    "前台工作人员": "前台",
    "门店店长": "店长",
    "审核同学": "审核专员",
}

ROLE_GENERAL_SUFFIXES = [
    "前台",
    "店长",
    "医生",
    "护士",
    "院长",
    "负责人",
    "管理者",
    "管理员",
    "运营",
]

ROLE_CONTEXT_PATTERNS = {
    "患者": [
        r"患者端",
        r"面向患者",
        r"患者在(?:使用|操作|查看|预约|下单|购药|填写)",
        r"患者(?:使用|操作|查看|预约|下单|购药|填写)",
        r"患者可以",
        r"患者自己",
    ],
}


def extract_roles_from_text(text: str) -> List[str]:
    roles: List[str] = []
    normalized_text = text.strip()
    if not normalized_text:
        return roles

    term_positions = []
    for role in COMMON_ROLE_TERMS:
        index = normalized_text.find(role)
        if index >= 0:
            term_positions.append((index, role))
    for _, role in sorted(term_positions, key=lambda item: (item[0], len(item[1]))):
        _append_role(roles, role)

    for pattern in ROLE_SIGNAL_PATTERNS:
        for match in re.finditer(pattern, normalized_text):
            for candidate in _split_role_phrase(match.group("role")):
                _append_role(roles, candidate)

    suffix_pattern = "|".join(re.escape(item) for item in ROLE_SUFFIXES)
    for match in re.finditer(rf"[\u4e00-\u9fffA-Za-z]{{1,12}}(?:{suffix_pattern})", normalized_text):
        for candidate in _split_role_phrase(match.group(0)):
            _append_role(roles, candidate)

    roles = filter_roles_for_text(roles, normalized_text)
    negated_roles = extract_negated_roles(normalized_text)
    return [role for role in roles if role not in negated_roles]


def normalize_role_name(role: str) -> str:
    return _cleanup_role_candidate(role)


def filter_roles_for_text(roles: List[str], text: str) -> List[str]:
    filtered: List[str] = []
    normalized_text = text.strip()
    for role in roles:
        if not _role_is_supported_by_text(role, normalized_text):
            continue
        if role not in filtered:
            filtered.append(role)
    return filtered


def merge_roles_from_context(context_profile: Dict[str, object], text: str = "") -> List[str]:
    roles: List[str] = []
    context_roles = context_profile.get("target_user_roles", [])
    if isinstance(context_roles, list):
        for role in context_roles:
            _append_role(roles, str(role))
    for role in extract_roles_from_text(text):
        _append_role(roles, role)
    return roles


def extract_role_relationships(text: str) -> Dict[str, List[str]]:
    relationships = {
        "proposers": [],
        "users": [],
        "outcome_owners": [],
    }
    normalized_text = text.strip()
    if not normalized_text:
        return relationships

    for relation_key, patterns in ROLE_RELATION_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, normalized_text):
                for candidate in _split_role_phrase(match.group("role")):
                    _append_role(relationships[relation_key], candidate)
    negated_roles = extract_negated_roles(normalized_text)
    if negated_roles:
        for relation_key, items in relationships.items():
            relationships[relation_key] = [item for item in items if item not in negated_roles]
    negated_by_relation = _extract_negated_relation_roles(normalized_text)
    for relation_key, negated_items in negated_by_relation.items():
        if not negated_items:
            continue
        relationships[relation_key] = [
            item for item in relationships[relation_key] if item not in negated_items
        ]
    for role in extract_roles_from_text(normalized_text):
        if role in negated_by_relation["outcome_owners"]:
            continue
        if role not in relationships["outcome_owners"] and _role_has_outcome_signal(role, normalized_text):
            relationships["outcome_owners"].append(role)
    return relationships


def merge_role_relationships(existing: Dict[str, object], text: str = "") -> Dict[str, List[str]]:
    merged = {
        "proposers": [],
        "users": [],
        "outcome_owners": [],
    }
    if isinstance(existing, dict):
        for key in merged:
            items = existing.get(key, [])
            if isinstance(items, list):
                for item in items:
                    _append_role(merged[key], str(item))

    extracted = extract_role_relationships(text)
    for key, items in extracted.items():
        for item in items:
            _append_role(merged[key], item)
    return merged


def extract_negated_roles(text: str) -> List[str]:
    negated_roles: List[str] = []
    normalized_text = text.strip()
    if not normalized_text:
        return negated_roles
    for pattern in NEGATED_ROLE_PATTERNS:
        for match in re.finditer(pattern, normalized_text):
            for candidate in _split_role_phrase(match.group("role")):
                if candidate and candidate not in negated_roles:
                    negated_roles.append(candidate)
    return negated_roles


def _extract_negated_relation_roles(text: str) -> Dict[str, List[str]]:
    negated = {
        "proposers": [],
        "users": [],
        "outcome_owners": [],
    }
    normalized_text = text.strip()
    if not normalized_text:
        return negated
    for relation_key, patterns in RELATION_NEGATION_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, normalized_text):
                for candidate in _split_role_phrase(match.group("role")):
                    if candidate and candidate not in negated[relation_key]:
                        negated[relation_key].append(candidate)
    return negated


def _role_has_outcome_signal(role: str, text: str) -> bool:
    escaped = re.escape(role)
    return any(
        re.search(pattern.format(role=escaped), text)
        for pattern in [
            r"{role}[^，。；]{{0,8}}对结果负责",
            r"{role}[^，。；]{{0,8}}会对结果负责",
            r"{role}[^，。；]{{0,8}}负责结果",
            r"{role}[^，。；]{{0,8}}盯结果",
            r"{role}[^，。；]{{0,8}}背结果",
            r"{role}[^，。；]{{0,8}}拍板",
            r"{role}[^，。；]{{0,8}}更关注",
            r"{role}[^，。；]{{0,8}}会看结果",
            r"{role}[^，。；]{{0,8}}看结果",
            r"{role}[^，。；]{{0,8}}决定是否上线",
            r"{role}[^，。；]{{0,8}}决定要不要上线",
            r"{role}[^，。；]{{0,8}}决定是否做",
            r"{role}[^，。；]{{0,8}}决定要不要做",
            r"{role}[^，。；]{{0,8}}决定是否采购",
        ]
    )


def _append_role(target: List[str], role: str) -> None:
    normalized = _cleanup_role_candidate(role)
    if not normalized:
        return
    for suffix in ROLE_GENERAL_SUFFIXES:
        if normalized == suffix and any(existing.endswith(suffix) and existing != suffix for existing in target):
            return
        if normalized.endswith(suffix) and normalized != suffix and suffix in target:
            target.remove(suffix)
    if normalized not in target:
        target.append(normalized)


def _cleanup_role_candidate(candidate: str) -> str:
    normalized = candidate.strip()
    if not normalized:
        return ""

    for prefix in ROLE_CLEANUP_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()

    normalized = normalized.strip("，。；：、,.!?！？()（）[]【】 ")
    normalized = ROLE_NORMALIZATION.get(normalized, normalized)
    for suffix in ["在操作", "在用", "在处理", "在负责", "操作", "在"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
    if normalized.endswith("会") and any(normalized[:-1].endswith(suffix) for suffix in ROLE_SUFFIXES):
        normalized = normalized[:-1]

    if len(normalized) < 2:
        return ""
    if len(normalized) > 6:
        return ""
    if any(marker in normalized for marker in ["产品", "项目", "场景", "需求", "服务", "系统", "网页端", "小程序", "App"]):
        return ""
    if any(marker in normalized for marker in ROLE_INVALID_PARTS):
        return ""
    return normalized


def _split_role_phrase(raw_text: str) -> List[str]:
    normalized = raw_text.strip()
    if not normalized:
        return []
    fragments = re.split(r"(?:或者|和|及|与|、|/|或)", normalized)
    results: List[str] = []
    for fragment in fragments:
        cleaned = _cleanup_role_candidate(fragment)
        if cleaned and cleaned not in results:
            results.append(cleaned)
    return results


def _role_is_supported_by_text(role: str, text: str) -> bool:
    patterns = ROLE_CONTEXT_PATTERNS.get(role, [])
    if not patterns:
        return True
    return any(re.search(pattern, text) for pattern in patterns)
