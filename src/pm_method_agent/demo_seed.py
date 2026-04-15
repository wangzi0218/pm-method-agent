from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from pm_method_agent.agent_shell import PMMethodAgentShell
from pm_method_agent.llm_adapter import (
    LLMAdapter,
    LLMMessage,
    LLMRequest,
    OpenAICompatibleAdapter,
    load_openai_compatible_config_from_env,
)
from pm_method_agent.prompting import build_prompt_composition


SUPPORTED_BUSINESS_MODELS = {"tob", "toc", "internal"}
SUPPORTED_PLATFORMS = {"pc", "mobile-web", "native-app", "mini-program", "multi-platform"}
UNCERTAINTY_MARKERS = ("还没想清楚", "不确定", "到底", "还是", "是不是", "要不要", "该不该", "先处理", "先解决")
SOLUTIONISH_MARKERS = (
    "优化",
    "提升",
    "改版",
    "升级",
    "入口",
    "页面",
    "看板",
    "后台",
    "弹窗",
    "按钮",
    "浮层",
    "引导",
    "功能",
    "希望",
    "自定义",
    "自动匹配",
    "想做个",
    "想做一个",
    "想改改",
    "想加一个",
    "想弄个",
    "想搞个",
    "搞个",
    "做个",
)
PRODUCT_PREFIXES = ("支付宝", "淘宝", "京东", "微信", "美团", "抖音")
HUMANISH_TITLE_MARKERS = ("有点", "老是", "没", "找不到", "看不懂", "掉", "乱", "卡", "烦")
OBSERVATION_MARKERS = ("最近", "现在", "已经", "反馈", "数据", "下降", "投诉", "发生在", "影响", "手动", "漏了", "有人说")
QUESTIONISH_MARKERS = ("具体是", "最好", "先看看", "能不能", "要不要先", "是不是先", "建议先", "可以先")


@dataclass
class DemoScenarioSpec:
    title: str
    business_model: str = ""
    primary_platform: str = ""
    product_domain: str = ""
    target_user_roles: List[str] = field(default_factory=list)
    initial_message: str = ""
    follow_up_messages: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "business_model": self.business_model,
            "primary_platform": self.primary_platform,
            "product_domain": self.product_domain,
            "target_user_roles": list(self.target_user_roles),
            "initial_message": self.initial_message,
            "follow_up_messages": list(self.follow_up_messages),
        }


@dataclass
class DemoScenarioGeneration:
    scenarios: List[DemoScenarioSpec]
    generator_name: str = "fallback"
    fallback_used: bool = False
    fallback_reason: str = ""
    theme: str = ""
    scenario_count_requested: int = 3

    def to_dict(self) -> dict[str, object]:
        return {
            "scenarios": [item.to_dict() for item in self.scenarios],
            "generator_name": self.generator_name,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "theme": self.theme,
            "scenario_count_requested": self.scenario_count_requested,
        }


@dataclass
class DemoSeedReplayResult:
    generation: DemoScenarioGeneration
    seeded_case_ids: List[str]
    latest_response: object

    def to_dict(self) -> dict[str, object]:
        return {
            "generation": self.generation.to_dict(),
            "seeded_case_ids": list(self.seeded_case_ids),
        }


class DemoScenarioGenerator(Protocol):
    def generate(self, *, theme: str = "", scenario_count: int = 3) -> DemoScenarioGeneration:
        ...


class StaticDemoScenarioGenerator:
    def generate(self, *, theme: str = "", scenario_count: int = 3) -> DemoScenarioGeneration:
        normalized_count = _normalize_scenario_count(scenario_count)
        scenarios = _select_default_demo_scenarios(theme=theme, scenario_count=normalized_count)
        return DemoScenarioGeneration(
            scenarios=scenarios,
            generator_name="fallback",
            fallback_used=False,
            fallback_reason="",
            theme=theme.strip(),
            scenario_count_requested=normalized_count,
        )


class LLMDemoScenarioGenerator:
    def __init__(
        self,
        adapter: LLMAdapter,
        fallback: Optional[DemoScenarioGenerator] = None,
    ) -> None:
        self._adapter = adapter
        self._fallback = fallback or StaticDemoScenarioGenerator()

    def generate(self, *, theme: str = "", scenario_count: int = 3) -> DemoScenarioGeneration:
        normalized_count = _normalize_scenario_count(scenario_count)
        request = _build_demo_seed_request(theme=theme, scenario_count=normalized_count)
        try:
            response = self._adapter.generate(request)
            payload = json.loads(response.content)
        except Exception as exc:
            return _build_demo_seed_fallback(
                self._fallback.generate(theme=theme, scenario_count=normalized_count),
                reason=_render_demo_seed_fallback_reason(exc),
            )

        scenarios = _normalize_demo_scenarios(payload.get("scenarios", []), scenario_count=normalized_count)
        if not scenarios:
            return _build_demo_seed_fallback(
                self._fallback.generate(theme=theme, scenario_count=normalized_count),
                reason="llm-empty-result",
            )
        return DemoScenarioGeneration(
            scenarios=scenarios,
            generator_name="llm",
            fallback_used=False,
            fallback_reason="",
            theme=theme.strip(),
            scenario_count_requested=normalized_count,
        )


def build_demo_scenario_generator_from_env() -> DemoScenarioGenerator:
    config = load_openai_compatible_config_from_env()
    if config is None:
        return StaticDemoScenarioGenerator()
    fallback = StaticDemoScenarioGenerator()
    return LLMDemoScenarioGenerator(
        adapter=OpenAICompatibleAdapter(config=config),
        fallback=fallback,
    )


def seed_workspace_demo(
    shell: PMMethodAgentShell,
    *,
    workspace_id: str,
    generator: Optional[DemoScenarioGenerator] = None,
    theme: str = "",
    scenario_count: int = 3,
) -> DemoSeedReplayResult:
    active_generator = generator or build_demo_scenario_generator_from_env()
    generation = active_generator.generate(theme=theme, scenario_count=scenario_count)
    seeded_case_ids: List[str] = []
    latest_response = None

    for index, scenario in enumerate(generation.scenarios):
        initial_message = scenario.initial_message.strip()
        if not initial_message:
            continue
        if index > 0:
            initial_message = f"再看一个：{initial_message}"
        latest_response = shell.handle_message(
            message=initial_message,
            workspace_id=workspace_id,
        )
        latest_case_id = _read_case_id_from_response(latest_response)
        for follow_up in scenario.follow_up_messages:
            follow_up_message = str(follow_up).strip()
            if not follow_up_message:
                continue
            latest_response = shell.handle_message(
                message=follow_up_message,
                workspace_id=workspace_id,
            )
            latest_case_id = _read_case_id_from_response(latest_response) or latest_case_id
        if latest_case_id and latest_case_id not in seeded_case_ids:
            seeded_case_ids.append(latest_case_id)

    if latest_response is None:
        raise ValueError("No demo scenarios were generated.")

    return DemoSeedReplayResult(
        generation=generation,
        seeded_case_ids=seeded_case_ids,
        latest_response=latest_response,
    )


def _build_demo_seed_request(*, theme: str, scenario_count: int) -> LLMRequest:
    prompt = build_prompt_composition(
        identity="你是 PM Method Agent 的演示场景生成器。",
        agent_role="生成适合网页 demo 和多轮体验的中文产品需求草稿，不直接输出解决方案。",
        behavior_rules=[
            "优先生成贴近真实业务协作的自然语言草稿，而不是规范化 PRD。",
            "示例要覆盖不同产品类型和平台，尽量包含 ToB 与 ToC 的差异。",
            "每个示例都要保留不确定性，让系统后续仍需要做问题定义和决策挑战。",
        ],
        output_discipline=[
            "只输出 JSON 对象。",
            "字段必须完整，不要额外解释。",
            "follow_up_messages 保持 1 到 2 句，每句都像真实补充回复。",
        ],
        custom_append=[
            "标题、初始输入、补充回复都必须使用中文。",
            "初始输入要像产品经理、运营或业务方随手发来的草稿，不要写成长文。",
            "不要把答案补全得太过头，要保留方法审查的空间。",
            "不要把标题写成立项名、方案名或功能名，尽量像人给同事起的临时备注。",
            "初始输入更像飞书、微信里的随手一句话，允许带一点模糊、犹豫和口语感。",
        ],
        task_instruction="生成一组适合 PM Method Agent 网页 demo 的示例案例。",
    )
    payload = {
        "theme": theme.strip(),
        "scenario_count": scenario_count,
        "schema": {
            "scenarios": [
                {
                    "title": "案例标题",
                    "business_model": "tob|toc|internal",
                    "primary_platform": "pc|mobile-web|native-app|mini-program|multi-platform",
                    "product_domain": "业务域",
                    "target_user_roles": ["关键角色 1", "关键角色 2"],
                    "initial_message": "第一句真实草稿",
                    "follow_up_messages": ["补充一句场景", "补充一句证据或目标"],
                }
            ]
        },
    }
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=prompt.render()),
            LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ],
        metadata={"prompt_layers": prompt.metadata()},
    )


def _normalize_demo_scenarios(payload: object, *, scenario_count: int) -> List[DemoScenarioSpec]:
    if not isinstance(payload, list):
        return []
    scenarios: List[DemoScenarioSpec] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        initial_message = str(item.get("initial_message", "")).strip()
        if not title or not initial_message:
            continue
        business_model = str(item.get("business_model", "")).strip().lower()
        if business_model not in SUPPORTED_BUSINESS_MODELS:
            business_model = ""
        primary_platform = str(item.get("primary_platform", "")).strip().lower()
        if primary_platform not in SUPPORTED_PLATFORMS:
            primary_platform = ""
        roles = _normalize_string_list(item.get("target_user_roles"), limit=4)
        product_domain = str(item.get("product_domain", "")).strip()
        raw_follow_ups = _normalize_string_list(item.get("follow_up_messages"), limit=2)
        normalized_title = _normalize_demo_title(
            title,
            initial_message=initial_message,
            follow_up_messages=raw_follow_ups,
            product_domain=product_domain,
        )
        normalized_initial_message = _normalize_demo_initial_message(
            str(item.get("initial_message", "")).strip(),
            title=normalized_title,
            product_domain=product_domain,
            business_model=business_model,
            primary_platform=primary_platform,
            roles=roles,
        )
        follow_ups = _normalize_demo_follow_ups(
            raw_follow_ups,
            title=normalized_title,
            product_domain=product_domain,
            business_model=business_model,
            primary_platform=primary_platform,
            roles=roles,
        )
        scenarios.append(
            DemoScenarioSpec(
                title=normalized_title,
                business_model=business_model,
                primary_platform=primary_platform,
                product_domain=product_domain,
                target_user_roles=roles,
                initial_message=normalized_initial_message,
                follow_up_messages=follow_ups,
            )
        )
        if len(scenarios) >= scenario_count:
            break
    return scenarios


def _normalize_string_list(payload: object, *, limit: int) -> List[str]:
    if not isinstance(payload, list):
        return []
    normalized: List[str] = []
    for item in payload:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_demo_title(
    title: str,
    *,
    initial_message: str,
    follow_up_messages: List[str],
    product_domain: str,
) -> str:
    normalized = _short_text(title, limit=24)
    for prefix in PRODUCT_PREFIXES:
        if normalized.startswith(prefix) and len(normalized) > len(prefix) + 2:
            normalized = normalized[len(prefix):].strip("：: -")
            break
    normalized = re.sub(r"(优化|提升|改版|升级)$", "", normalized).strip("：: -")
    if not normalized:
        return "待分析示例"
    if any(marker in normalized for marker in HUMANISH_TITLE_MARKERS):
        return normalized
    combined_text = " ".join([normalized, initial_message, *follow_up_messages, product_domain]).lower()
    if any(keyword in combined_text for keyword in ("直播", "开播", "观看人数", "直播间")):
        return "直播间流量有点不稳"
    if any(keyword in combined_text for keyword in ("排班", "excel", "表格", "冲突")):
        return "排班还是靠表在传"
    if any(keyword in combined_text for keyword in ("会员", "续费", "到期")):
        return "续费提醒这块有点打扰"
    if any(keyword in combined_text for keyword in ("配送员", "骑手", "流失率")):
        return "配送员最近有点留不住"
    if any(keyword in combined_text for keyword in ("收款码", "收钱")):
        return "收款码这块老有人来问"
    if any(keyword in combined_text for keyword in ("缴费", "账单", "入口")):
        return "缴费这块有点不好找"
    if any(keyword in combined_text for keyword in ("首页", "流量", "推荐", "分发", "点击")):
        return "首页点击有点掉"
    if any(keyword in combined_text for keyword in ("报表", "数据", "后台", "看板", "对账", "流水")):
        return "后台报表有点看不明白"
    if any(keyword in combined_text for keyword in ("详情页", "商品详情", "详情")):
        return "详情页信息有点乱"
    if any(keyword in combined_text for keyword in ("消息", "提醒", "通知")):
        return "提醒这块有点打扰"
    if any(keyword in combined_text for keyword in ("售后", "退货", "退款", "投诉率")):
        return "售后这块目标没先收住"
    if any(keyword in combined_text for keyword in ("履约", "物流", "送达")):
        return "承诺时间和实际感受有点对不上"
    return normalized


def _normalize_demo_initial_message(
    initial_message: str,
    *,
    title: str,
    product_domain: str,
    business_model: str,
    primary_platform: str,
    roles: List[str],
) -> str:
    text = _normalize_sentence(initial_message)
    if _has_solution_intent(text):
        return _build_problemish_initial_message(
            title=title,
            product_domain=product_domain,
            business_model=business_model,
            primary_platform=primary_platform,
            roles=roles,
        )
    if text and not _looks_like_solution_framed(text):
        if any(marker in text for marker in UNCERTAINTY_MARKERS):
            return text
        return f"{text.rstrip('。')}，但我还没想清楚这次最该先收住哪一个问题。"
    return _build_problemish_initial_message(
        title=title,
        product_domain=product_domain,
        business_model=business_model,
        primary_platform=primary_platform,
        roles=roles,
    )


def _normalize_demo_follow_ups(
    payload: object,
    *,
    title: str,
    product_domain: str,
    business_model: str,
    primary_platform: str,
    roles: List[str],
) -> List[str]:
    normalized = _normalize_string_list(payload, limit=2)
    cleaned = [_normalize_sentence(item) for item in normalized if _normalize_sentence(item)]
    if len(cleaned) >= 2 and all(_looks_like_human_follow_up(item) for item in cleaned):
        return cleaned[:2]

    return [
        _build_context_follow_up(
            product_domain=product_domain,
            business_model=business_model,
            primary_platform=primary_platform,
            roles=roles,
        ),
        _build_evidence_follow_up(title=title, roles=roles),
    ]


def _looks_like_solution_framed(text: str) -> bool:
    if not text:
        return True
    if any(marker in text for marker in UNCERTAINTY_MARKERS):
        return False
    return any(marker in text for marker in SOLUTIONISH_MARKERS)


def _has_solution_intent(text: str) -> bool:
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "想做个",
            "想做一个",
            "想改改",
            "想加一个",
            "想弄个",
            "想搞个",
            "想改一下",
            "希望做个",
            "能不能搞个",
            "能不能做个",
        )
    )


def _looks_like_human_follow_up(text: str) -> bool:
    if not text:
        return False
    if _looks_like_solution_framed(text):
        return False
    if any(marker in text for marker in QUESTIONISH_MARKERS):
        return False
    return any(marker in text for marker in OBSERVATION_MARKERS)


def _build_problemish_initial_message(
    *,
    title: str,
    product_domain: str,
    business_model: str,
    primary_platform: str,
    roles: List[str],
) -> str:
    if "首页点击有点掉" in title:
        return "最近首页有些位置的点击往下掉，运营那边也开始追着问是不是该动一下，但我还没想清楚这次到底是分发问题、内容问题，还是入口本身就不对。"
    if "后台报表有点看不明白" in title:
        return "最近商家后台那边老有人说报表不太看得明白，讨论也越来越多，但我还没想清楚这次到底是展示问题、口径问题，还是数据链路本身有问题。"
    if "详情页信息有点乱" in title:
        return "最近商品详情页这块老有人说信息有点乱，重要内容不太好找，但我还没想清楚这次更像是展示层次问题，还是用户本来就分不清重点。"
    if "缴费这块有点不好找" in title:
        return "最近总有人说生活缴费这块不太好找，运营也有点着急，但我还没想清楚这次更像是入口问题、心智问题，还是用户本来就不急着在这里办。"
    if "收款码这块老有人来问" in title:
        return "最近收款码这块总有人反复来问，门店那边也开始有点烦，但我还没想清楚这次到底是产品信息没讲明白，还是流程本身就不顺。"
    if "排班还是靠表在传" in title:
        return "我们这边排班现在还是靠表在传，经常来回改，也容易撞车，但我还没想清楚这次到底是协作方式有问题，还是排班规则本来就没先说清。"
    if "提醒这块有点打扰" in title:
        return "最近关于提醒太多、打扰感太强的反馈又多起来了，但我还没想清楚这次更像是通知策略问题，还是消息分层本身没做好。"
    if "售后这块目标没先收住" in title:
        return "最近售后这块讨论有点散，大家都觉得该动一动，但我还没想清楚这次到底是要先看退货发起率，还是先盯投诉和体验。"
    if "承诺时间和实际感受有点对不上" in title:
        return "最近不少人都在吐槽预计送达和实际感受对不上，这件事看起来该处理，但我还没想清楚这次是展示承诺有问题，还是履约本身就不稳定。"

    topic = _build_topic_phrase(title=title, product_domain=product_domain)
    role_hint = f"{roles[0]}那边" if roles else "用户侧"
    platform_hint = _platform_label(primary_platform)
    business_hint = _business_model_label(business_model)
    return (
        f"最近{topic}这块讨论慢慢变多了，{role_hint}在{platform_hint}里已经有感知，"
        f"但我还没想清楚这次更像是{business_hint}里的理解问题、流程问题，还是优先级没先收住。"
    )


def _build_context_follow_up(
    *,
    product_domain: str,
    business_model: str,
    primary_platform: str,
    roles: List[str],
) -> str:
    domain_text = product_domain or "这个产品"
    role_text = "、".join(roles[:2]) if roles else "用户和业务方"
    if roles:
        first_role = roles[0]
    else:
        first_role = "用户"
    if "App" == _platform_label(primary_platform):
        return (
            f"这事主要还是发生在{_platform_label(primary_platform)}里，{first_role}会直接碰到，"
            f"{role_text}也都在盯。"
        )
    if business_model == "tob":
        return (
            f"这事现在主要还是卡在{domain_text}这段，{first_role}会最先碰到，"
            f"{role_text}也都会被带上。"
        )
    return (
        f"这个场景主要发生在{domain_text}里，当前主要还是通过{_platform_label(primary_platform)}承接，"
        f"{role_text}都会直接受影响。"
    )


def _build_evidence_follow_up(*, title: str, roles: List[str]) -> str:
    role_text = roles[0] if roles else "业务方"
    topic = _build_topic_phrase(title=title, product_domain="")
    if "首页点击有点掉" in title:
        return "现在一边能看到点击往下掉，一边也有些零散反馈，但还没拆清到底是内容不对，还是位置没放对。"
    if "后台报表有点看不明白" in title:
        return "现在已经有人反复提这件事了，但还没拆清到底是字段太绕、口径不一致，还是大家根本不知道该怎么看。"
    if "详情页信息有点乱" in title:
        return "现在已经有人说找参数、规则和服务说明找得有点费劲，但还没拆清到底是信息堆得太平，还是重点本来就没露出来。"
    if "缴费这块有点不好找" in title:
        return "现在已经有人说找缴费找得有点费劲，但还没拆清到底是路径太深，还是这件事本来就不在用户当下心智里。"
    if "收款码这块老有人来问" in title:
        return "现在已经有人反复提这件事了，但还没拆清到底是入口太绕、说明不够，还是门店本来就容易走错。"
    if "提醒这块有点打扰" in title:
        return "现在已经能听到一些关于打扰感的抱怨，但还没拆清到底是哪一类提醒最烦，还是频率本身就过高。"
    if "售后这块目标没先收住" in title:
        return "现在数据和反馈都在涨，但还没拆清到底是效率问题更急，还是体验问题更急。"
    if "承诺时间和实际感受有点对不上" in title:
        return "现在投诉和客服反馈都能看到，但还没拆清到底是承诺展示太满，还是履约本身就跟不上。"
    return (
        f"现在已经能听到一些关于{topic}的零散反馈，{role_text}也开始有感知，"
        "但还没拆清到底是现状流程有问题，还是用户预期本来就没有对齐。"
    )


def _build_topic_phrase(*, title: str, product_domain: str) -> str:
    normalized_title = title.strip()
    if any(marker in normalized_title for marker in ("问题", "提醒", "通知", "售后", "履约", "缴费", "消息", "入口")):
        return normalized_title
    if product_domain:
        return f"{product_domain}里的关键流程"
    return "当前这类场景"


def _normalize_sentence(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip("，,。；;？！!? ")
    return f"{normalized}。" if normalized else ""


def _platform_label(value: str) -> str:
    labels = {
        "pc": "网页端",
        "mobile-web": "移动网页",
        "native-app": "App",
        "mini-program": "小程序",
        "multi-platform": "多端",
    }
    return labels.get(value, "当前产品")


def _business_model_label(value: str) -> str:
    labels = {
        "tob": "企业协作场景",
        "toc": "消费者场景",
        "internal": "内部协作场景",
    }
    return labels.get(value, "当前业务场景")


def _short_text(value: str, *, limit: int) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit - 1]}…"


def _build_demo_seed_fallback(
    fallback_generation: DemoScenarioGeneration,
    *,
    reason: str,
) -> DemoScenarioGeneration:
    return DemoScenarioGeneration(
        scenarios=fallback_generation.scenarios,
        generator_name="llm-fallback",
        fallback_used=True,
        fallback_reason=reason,
        theme=fallback_generation.theme,
        scenario_count_requested=fallback_generation.scenario_count_requested,
    )


def _render_demo_seed_fallback_reason(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _normalize_scenario_count(value: int) -> int:
    if value <= 0:
        return 3
    return min(value, 5)


def _select_default_demo_scenarios(*, theme: str, scenario_count: int) -> List[DemoScenarioSpec]:
    lowered_theme = theme.strip().lower()
    scenarios = list(_default_demo_scenarios())
    if any(keyword in lowered_theme for keyword in ["医疗", "诊所", "his"]):
        scenarios.sort(key=lambda item: 0 if "医疗" in item.product_domain or "诊所" in item.initial_message else 1)
    elif any(keyword in lowered_theme for keyword in ["淘宝", "售后", "电商"]):
        scenarios.sort(key=lambda item: 0 if "淘宝" in item.title or "电商" in item.product_domain else 1)
    elif any(keyword in lowered_theme for keyword in ["支付宝", "支付", "账单"]):
        scenarios.sort(key=lambda item: 0 if "支付宝" in item.title or "支付" in item.product_domain else 1)
    elif any(keyword in lowered_theme for keyword in ["京东", "零售", "物流"]):
        scenarios.sort(key=lambda item: 0 if "京东" in item.title or "零售" in item.product_domain else 1)
    return scenarios[:scenario_count]


def _default_demo_scenarios() -> List[DemoScenarioSpec]:
    return [
        DemoScenarioSpec(
            title="诊所提醒漏发",
            business_model="tob",
            primary_platform="pc",
            product_domain="医疗服务平台",
            target_user_roles=["前台", "店长"],
            initial_message="最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。",
            follow_up_messages=[
                "这是一个 ToB 的 HIS 产品，主要通过网页端使用，前台在操作，店长和核心医生会看结果。",
                "现在前台主要靠手工翻表和微信提醒，最近两周漏了 6 次，店长担心会影响复诊到诊率。",
            ],
        ),
        DemoScenarioSpec(
            title="淘宝售后目标没收住",
            business_model="toc",
            primary_platform="native-app",
            product_domain="电商平台",
            target_user_roles=["买家", "售后运营"],
            initial_message="最近淘宝售后相关反馈不少，但我还没想清楚，这次到底是想提升退货发起率，还是降低售后投诉率。",
            follow_up_messages=[
                "这是一个消费者产品，核心场景发生在 App 里，售后运营和买家都会受影响。",
                "现在既看到投诉变多，也看到退货发起率波动，但还没判断这次最该先盯哪一个指标。",
            ],
        ),
        DemoScenarioSpec(
            title="支付宝提醒打扰感变强",
            business_model="toc",
            primary_platform="native-app",
            product_domain="支付服务",
            target_user_roles=["普通用户", "消息运营"],
            initial_message="最近有不少人反馈支付宝消息太多、打扰感很强，但我们还没想清楚到底是通知策略问题还是消息分层问题。",
            follow_up_messages=[
                "这个场景主要发生在移动端，普通用户会直接感知，消息运营也在盯打开率和关闭率。",
                "当前已经看到一些用户手动关提醒，但还没拆清到底是哪几类消息最容易让人烦。",
            ],
        ),
        DemoScenarioSpec(
            title="京东物流承诺理解偏差",
            business_model="toc",
            primary_platform="native-app",
            product_domain="零售电商",
            target_user_roles=["消费者", "履约运营"],
            initial_message="最近京东履约相关的抱怨变多了，很多用户说承诺送达时间和实际体验不一致，但我还没收住这次要先处理哪一层问题。",
            follow_up_messages=[
                "这个场景主要在 App 的商品详情和下单链路里发生，消费者和履约运营都在关注。",
                "我们现在有投诉和客服记录，但还没拆清是展示文案的问题，还是履约能力本身就不稳定。",
            ],
        ),
    ]


def _read_case_id_from_response(response: object) -> str:
    case_state = getattr(response, "case_state", None)
    if case_state is None:
        return ""
    return str(getattr(case_state, "case_id", "")).strip()
