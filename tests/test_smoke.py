import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from unittest.mock import patch

os.environ.setdefault("PMMA_DISABLE_ENV_AUTOLOAD", "1")

from pm_method_agent.agent_shell import PMMethodAgentShell
from pm_method_agent.case_copywriter import LLMCaseCopywriter, apply_case_copywriting, build_case_copywriter_from_env
from pm_method_agent.cli import main
from pm_method_agent.command_executor import LocalCommandExecutor
from pm_method_agent.demo_seed import (
    LLMDemoScenarioGenerator,
    StaticDemoScenarioGenerator,
    seed_workspace_demo,
)
from pm_method_agent.directory_list_tool import LocalDirectoryLister
from pm_method_agent.hook_enforcement import HookExecutionBlockedError, run_pre_operation_hooks
from pm_method_agent.http_service import PMMethodHTTPService
from pm_method_agent.llm_adapter import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from pm_method_agent.follow_up_copywriter import (
    FOLLOW_UP_DISPLAY_FOCUS_KEY,
    FOLLOW_UP_DISPLAY_QUESTIONS_KEY,
    FOLLOW_UP_DISPLAY_REASON_KEY,
    LLMFollowUpCopywriter,
    apply_follow_up_copywriting,
)
from pm_method_agent.models import CaseState
from pm_method_agent.operation_enforcement import evaluate_operation_enforcement
from pm_method_agent.orchestrator import continue_analysis_with_context, run_analysis, run_analysis_with_context
from pm_method_agent.pre_framing import LLMPreFramingGenerator, build_pre_framing_result
from pm_method_agent.prompting import build_prompt_composition
from pm_method_agent.project_profile_service import (
    create_project_profile,
    default_project_profile_store,
    get_project_profile,
)
from pm_method_agent.runtime_session_service import (
    RUNTIME_EVENT_LOG_LIMIT,
    RUNTIME_LEDGER_LIMIT,
    append_runtime_event,
    cancel_runtime_query,
    close_incomplete_hooks,
    complete_runtime_query,
    complete_hook_call,
    complete_tool_call,
    default_runtime_session_store,
    fail_runtime_query,
    get_or_create_runtime_session,
    interrupt_runtime_query,
    request_hook_call,
    request_tool_call,
    save_runtime_session,
    start_runtime_query,
)
from pm_method_agent.reply_interpreter import (
    HeuristicReplyInterpreter,
    HybridReplyInterpreter,
    LLMReplyInterpreter,
    build_reply_interpreter_from_env,
)
from pm_method_agent.renderers import render_case_history, render_case_state, render_runtime_session
from pm_method_agent.renderers import build_case_runtime_payload
from pm_method_agent.runtime_config import ensure_local_env_loaded, get_llm_runtime_status
from pm_method_agent.runtime_policy import (
    check_runtime_action_policy,
    check_runtime_command_policy,
    check_runtime_read_policy,
    resolve_runtime_approval_handling,
    check_runtime_write_policy,
    load_runtime_policy,
)
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case
from pm_method_agent.text_file_read_tool import LocalTextFileReader
from pm_method_agent.web_demo_assets import get_web_demo_asset
from pm_method_agent.text_search_tool import LocalTextSearcher
from pm_method_agent.text_file_tool import LocalTextFileWriter
from pm_method_agent.tool_runtime import (
    LocalToolExecutionOutcome,
    LocalToolHandler,
    LocalToolRequest,
    LocalToolRuntime,
)
from pm_method_agent.workspace_service import (
    activate_workspace_case,
    default_workspace_store,
    get_or_create_workspace,
    get_workspace_approval_preferences,
    save_workspace,
    update_workspace_approval_preferences,
)


class StubLLMAdapter:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content=self.content, provider="stub", model="stub-model")


class RaisingLLMAdapter:
    def __init__(self, error: Optional[Exception] = None) -> None:
        self.error = error or RuntimeError("llm-unavailable")
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        raise self.error


class StubTransport:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict[str, object]] = []

    def __call__(self, url: str, headers: dict[str, str], body: bytes, timeout_seconds: float) -> str:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "body": body.decode("utf-8"),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response_text


class RaisingReplyInterpreter:
    def analyze_reply(self, reply_text: str, previous_case=None):  # type: ignore[no-untyped-def]
        del reply_text, previous_case
        raise RuntimeError("boom")


class StubLocalToolHandler(LocalToolHandler):
    name = "stub-local-tool"

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        return LocalToolExecutionOutcome(
            action="stub-tool-executed",
            terminal_state="completed",
            success=True,
            result_ref=f"stub:{request.tool_name}",
            output_payload={"echo": request.request_payload.get("value")},
        )


class OrchestratorSmokeTest(unittest.TestCase):
    def test_heuristic_reply_interpreter_can_extract_multi_platform_background(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply(
            "当前这个项目属于 ToB 的 HIS 产品，主要使用网页端，但也提供小程序，诊所前台提出需求，店长对结果负责。"
        )

        self.assertEqual(analysis.context_updates["business_model"], "tob")
        self.assertEqual(analysis.context_updates["primary_platform"], "multi-platform")
        self.assertIn("前台", analysis.context_updates["target_user_roles"])
        self.assertIn("店长", analysis.context_updates["target_user_roles"])

    def test_heuristic_reply_interpreter_can_extract_colloquial_business_and_platform_terms(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply(
            "这个偏 B 端，平时门店店员主要在 H5 上操作，但老板会盯结果。"
        )

        self.assertEqual(analysis.context_updates["business_model"], "tob")
        self.assertEqual(analysis.context_updates["primary_platform"], "mobile-web")
        self.assertIn("店员", analysis.context_updates["target_user_roles"])
        self.assertIn("老板", analysis.context_updates["target_user_roles"])

    def test_normalize_context_updates_can_fold_role_aliases(self) -> None:
        adapter = StubLLMAdapter(
            content='{"context_updates":{"target_user_roles":["前台工作人员","店长"]},"parser_confidence":"strong"}'
        )
        analysis = LLMReplyInterpreter(adapter=adapter).analyze_reply("测试")

        self.assertIn("前台", analysis.context_updates["target_user_roles"])
        self.assertNotIn("前台工作人员", analysis.context_updates["target_user_roles"])

    def test_normalize_role_relationships_can_fold_role_aliases(self) -> None:
        adapter = StubLLMAdapter(
            content='{"role_relationships":{"proposers":["前台员工"]},"parser_confidence":"strong"}'
        )
        analysis = LLMReplyInterpreter(adapter=adapter).analyze_reply("这是前台提的。")

        self.assertEqual(analysis.role_relationships["proposers"], ["前台"])

    def test_llm_reply_interpreter_uses_layered_prompt_sections(self) -> None:
        adapter = StubLLMAdapter(
            content='{"categories":["context"],"parser_confidence":"strong"}'
        )
        interpreter = LLMReplyInterpreter(adapter=adapter)

        interpreter.analyze_reply("这是一个 ToB 的 HIS 产品，前台在网页端操作提醒。")

        request = adapter.requests[0]
        system_prompt = request.messages[0].content
        self.assertIn("[身份描述]", system_prompt)
        self.assertIn("[角色职责]", system_prompt)
        self.assertIn("[行为规则]", system_prompt)
        self.assertIn("[工具约束]", system_prompt)
        self.assertIn("[输出纪律]", system_prompt)
        self.assertIn("[任务目标]", system_prompt)
        self.assertIn("prompt_layers", request.metadata)

    def test_llm_reply_interpreter_can_normalize_answered_pending_questions(self) -> None:
        adapter = StubLLMAdapter(
            content=(
                '{"answered_pending_questions":["当前的基线数据是多少","失败或停止条件是什么"],'
                '"partial_pending_questions":["成功指标是什么"],'
                '"parser_confidence":"strong"}'
            )
        )
        interpreter = LLMReplyInterpreter(adapter=adapter)
        previous_case = CaseState(
            case_id="demo-case",
            stage="validation-design",
            pending_questions=["当前基线指标是什么", "停止条件是什么", "成功指标是什么"],
            raw_input="新用户发帖率一直上不来。",
        )

        analysis = interpreter.analyze_reply(
            "当前首帖率大概 6%，如果两周没起色就停。",
            previous_case=previous_case,
        )

        self.assertEqual(analysis.answered_pending_questions, ["当前基线指标是什么", "停止条件是什么"])
        self.assertEqual(analysis.partial_pending_questions, ["成功指标是什么"])

    def test_llm_reply_interpreter_can_fall_back_to_heuristic_when_adapter_fails(self) -> None:
        interpreter = LLMReplyInterpreter(adapter=RaisingLLMAdapter(RuntimeError("network-down")))

        analysis = interpreter.analyze_reply("这是一个 ToB 的 HIS 产品，前台在网页端操作提醒。")

        self.assertEqual(analysis.parser_name, "llm-fallback")
        self.assertTrue(analysis.fallback_used)
        self.assertIn("RuntimeError", analysis.fallback_reason)
        self.assertEqual(analysis.context_updates["business_model"], "tob")
        self.assertEqual(analysis.context_updates["primary_platform"], "pc")

    def test_hybrid_reply_interpreter_can_keep_working_when_llm_fails(self) -> None:
        interpreter = HybridReplyInterpreter(
            llm_interpreter=LLMReplyInterpreter(adapter=RaisingLLMAdapter(RuntimeError("timeout"))),
            fallback=HeuristicReplyInterpreter(),
        )

        analysis = interpreter.analyze_reply("这个偏 B 端，前台在 H5 上操作，老板盯结果。")

        self.assertEqual(analysis.parser_name, "hybrid-fallback")
        self.assertTrue(analysis.fallback_used)
        self.assertEqual(analysis.context_updates["business_model"], "tob")
        self.assertEqual(analysis.context_updates["primary_platform"], "mobile-web")
        self.assertIn("老板", analysis.role_relationships["outcome_owners"])

    def test_heuristic_reply_interpreter_can_extract_generic_roles_from_sentence(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply(
            "这个需求是诊所前台提出的需求，每一个诊所的店长或者核心医生会对结果负责。"
        )

        self.assertIn("前台", analysis.context_updates["target_user_roles"])
        self.assertIn("店长", analysis.context_updates["target_user_roles"])
        self.assertIn("核心医生", analysis.context_updates["target_user_roles"])
        self.assertIn("前台", analysis.role_relationships["proposers"])
        self.assertIn("店长", analysis.role_relationships["outcome_owners"])

    def test_heuristic_reply_interpreter_does_not_treat_patient_as_target_role_without_usage_signal(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply("前台最近老是漏提醒患者，我在想是不是要处理一下。")

        self.assertIn("前台", analysis.context_updates["target_user_roles"])
        self.assertNotIn("患者", analysis.context_updates["target_user_roles"])

    def test_heuristic_reply_interpreter_keeps_patient_role_when_patient_side_usage_is_explicit(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply("这是一个患者端小程序，患者会在上面查看报告，医生也会跟进结果。")

        self.assertIn("患者", analysis.context_updates["target_user_roles"])
        self.assertIn("医生", analysis.context_updates["target_user_roles"])

    def test_heuristic_reply_interpreter_can_understand_consumer_app_role_phrasing(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply(
            "这是一个内容社区 App，运营提出这个想法，新用户是实际使用者。现在发帖转化主要卡在注册后第一天。"
        )

        self.assertEqual(analysis.context_updates["business_model"], "toc")
        self.assertEqual(analysis.context_updates["primary_platform"], "native-app")
        self.assertEqual(analysis.context_updates["target_user_roles"], ["运营", "新用户"])
        self.assertEqual(analysis.role_relationships["proposers"], ["运营"])
        self.assertEqual(analysis.role_relationships["users"], ["新用户"])

    def test_heuristic_reply_interpreter_can_extract_natural_role_relationships(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply(
            "这个事是运营提的，审核同学每天在用，老板盯结果。"
        )

        self.assertIn("运营", analysis.context_updates["target_user_roles"])
        self.assertIn("审核专员", analysis.context_updates["target_user_roles"])
        self.assertIn("老板", analysis.context_updates["target_user_roles"])
        self.assertIn("运营", analysis.role_relationships["proposers"])
        self.assertIn("审核专员", analysis.role_relationships["users"])
        self.assertIn("老板", analysis.role_relationships["outcome_owners"])

    def test_heuristic_reply_interpreter_can_extract_user_from_in_between_operation_phrase(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply(
            "这是一个 ToB 的 HIS 产品，前台在网页端操作提醒，店长会盯结果。"
        )

        self.assertIn("前台", analysis.role_relationships["users"])
        self.assertEqual(analysis.role_relationships["outcome_owners"], ["店长"])

    def test_heuristic_reply_interpreter_can_distinguish_operator_and_non_user_decision_maker(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply(
            "这个事是运营提的，一线审核同学在处理，老板拍板，医生不直接操作。"
        )

        self.assertIn("运营", analysis.context_updates["target_user_roles"])
        self.assertIn("审核专员", analysis.context_updates["target_user_roles"])
        self.assertIn("老板", analysis.context_updates["target_user_roles"])
        self.assertIn("医生", analysis.context_updates["target_user_roles"])
        self.assertEqual(analysis.role_relationships["proposers"], ["运营"])
        self.assertEqual(analysis.role_relationships["users"], ["审核专员"])
        self.assertEqual(analysis.role_relationships["outcome_owners"], ["老板"])

    def test_heuristic_reply_interpreter_can_extract_hospital_head_without_marking_them_as_user(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply("护士在用，院长不操作但会拍板。")

        self.assertIn("护士", analysis.context_updates["target_user_roles"])
        self.assertIn("院长", analysis.context_updates["target_user_roles"])
        self.assertEqual(analysis.role_relationships["users"], ["护士"])
        self.assertEqual(analysis.role_relationships["outcome_owners"], ["院长"])

    def test_heuristic_reply_interpreter_can_ignore_negated_roles(self) -> None:
        interpreter = HeuristicReplyInterpreter()
        analysis = interpreter.analyze_reply("更准确说，不是前台在操作，是护士在操作，店长盯结果。")

        self.assertNotIn("前台", analysis.context_updates["target_user_roles"])
        self.assertEqual(analysis.role_relationships["users"], ["护士"])

    def test_review_card_can_render_role_relationships(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "最近诊所前台经常漏掉复诊患者的就诊前提醒。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "multi-platform",
                "target_user_roles": ["前台", "店长"],
            },
        )
        case_state.metadata["role_relationships"] = {
            "proposers": ["前台"],
            "users": ["前台"],
            "outcome_owners": ["店长"],
        }

        rendered = render_case_state(case_state)
        self.assertIn("提出者：前台", rendered)
        self.assertIn("实际使用者：前台", rendered)
        self.assertIn("结果责任人：店长", rendered)

    def test_auto_mode_requests_context_when_context_is_missing(self) -> None:
        case_state = run_analysis("前台希望增加一个预约前提醒弹窗，避免漏提醒患者。")
        self.assertEqual(case_state.stage, "pre-framing")
        self.assertEqual(case_state.workflow_state, "blocked")
        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIsNotNone(case_state.pre_framing_result)
        assert case_state.pre_framing_result is not None
        self.assertGreaterEqual(len(case_state.pre_framing_result.candidate_directions), 2)
        self.assertGreaterEqual(len(case_state.pending_questions), 2)

    def test_auto_mode_still_uses_context_question_card_for_too_short_input(self) -> None:
        case_state = run_analysis("做个弹窗")

        self.assertEqual(case_state.stage, "context-alignment")
        self.assertEqual(case_state.workflow_state, "blocked")
        self.assertEqual(case_state.output_kind, "context-question-card")

    def test_problem_framing_mode_keeps_expected_stage(self) -> None:
        case_state = run_analysis("诊所希望做一个新的数据看板", mode="problem-framing")
        self.assertEqual(case_state.stage, "problem-definition")
        self.assertEqual(case_state.metadata["selected_modes"], ["problem-framing"])
        self.assertEqual(case_state.output_kind, "review-card")

    def test_context_profile_is_carried_into_case_state(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "pc",
                "target_user_roles": ["前台", "管理者"],
            },
        )
        self.assertEqual(case_state.context_profile["business_model"], "tob")
        self.assertEqual(case_state.context_profile["primary_platform"], "pc")
        self.assertEqual(case_state.workflow_state, "done")
        self.assertEqual(case_state.output_kind, "review-card")
        self.assertGreaterEqual(len(case_state.findings), 3)

    def test_auto_mode_can_stop_at_decision_gate(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "我们需要优化权限配置流程，避免前台误操作。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "pc",
                "target_user_roles": ["前台", "管理员"],
            },
        )
        self.assertEqual(case_state.stage, "decision-challenge")
        self.assertEqual(case_state.workflow_state, "blocked")
        self.assertEqual(case_state.output_kind, "decision-gate-card")
        self.assertGreaterEqual(len(case_state.decision_gates), 1)

    def test_case_id_is_hidden_by_default_in_markdown(self) -> None:
        case_state = run_analysis("前台希望增加一个预约前提醒弹窗，避免漏提醒患者。")
        rendered = render_case_state(case_state)
        self.assertNotIn("案例编号", rendered)

    def test_case_id_is_visible_when_enabled(self) -> None:
        case_state = run_analysis(
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
            show_case_id=True,
            case_id="demo-case",
        )
        rendered = render_case_state(case_state)
        self.assertIn("案例编号", rendered)
        self.assertIn("demo-case", rendered)

    def test_review_card_groups_unknowns(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "mobile-web",
                "target_user_roles": ["前台", "诊所管理者"],
            },
        )
        rendered = render_case_state(case_state)
        self.assertIn("## 我主要看到这几个点", rendered)
        self.assertIn("## 更建议先补", rendered)
        self.assertIn("### 现状与证据", rendered)
        self.assertIn("### 决策与验证", rendered)

    def test_rendered_review_card_can_polish_finding_copy_without_mutating_data(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "mobile-web",
                "target_user_roles": ["前台", "诊所管理者"],
            },
        )

        original_claims = [finding.claim for finding in case_state.findings]
        rendered = render_case_state(case_state)

        self.assertIn("输入里已经带出方案，先把要解决的问题单独说清。", rendered)
        self.assertIn("补上现状流程、失败案例和现有替代做法。", rendered)
        self.assertIn("把当前输入拆成现象、解释、方案假设三层。", rendered)
        self.assertIn("输入里已经带出方案，建议先把要解决的问题单独说清。", original_claims)

    def test_rendered_review_card_can_polish_gate_copy(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "mobile-web",
                "target_user_roles": ["前台", "诊所管理者"],
            },
        )

        rendered = render_case_state(case_state)

        self.assertIn("按现在的信息，能不能直接进入方案讨论？", rendered)
        self.assertIn("按现在的信息，这件事要不要继续往产品方案走？", rendered)
        self.assertIn("输入里已经混进方案了，现状证据也还不够。", rendered)
        self.assertIn("基础场景信息已经够用了，也没看到更优的非产品路径，可以继续往验证走。", rendered)

    def test_rendered_review_card_can_dedupe_overlap_between_actions_and_unknowns(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "mobile-web",
                "target_user_roles": ["前台", "诊所管理者"],
            },
        )

        rendered = render_case_state(case_state)

        self.assertIn("补上现状流程、失败案例和现有替代做法。", rendered)
        self.assertNotIn("- 当前流程是怎么运行的", rendered)
        self.assertNotIn("- 当前是否已有替代方案或绕路方式", rendered)
        self.assertIn("- 当前的基线数据是多少", rendered)

    def test_rendered_review_card_can_merge_compact_decision_context_findings(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "mobile-web",
                "target_user_roles": ["前台", "诊所管理者"],
            },
        )

        rendered = render_case_state(case_state)

        self.assertIn("还有几个场景前提会直接影响后面的判断", rendered)
        self.assertIn("这是企业产品场景", rendered)
        self.assertIn("现在主要是非桌面端场景", rendered)
        self.assertEqual(rendered.count("这条会影响后面怎么判断，但不用单独放大。"), 1)

    def test_rendered_review_card_does_not_show_summary_count_markers(self) -> None:
        from pm_method_agent.orchestrator import run_analysis_with_context

        case_state = run_analysis_with_context(
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "mobile-web",
                "target_user_roles": ["前台", "诊所管理者"],
            },
        )

        rendered = render_case_state(case_state)

        self.assertNotIn("另有 1 项", rendered)
        self.assertNotIn("另有 2 项", rendered)

    def test_session_service_can_create_and_load_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
                store=store,
            )
            loaded_case = get_case(case_state.case_id, store=store)

        self.assertEqual(loaded_case.case_id, case_state.case_id)
        self.assertEqual(loaded_case.output_kind, "continue-guidance-card")
        self.assertEqual(
            loaded_case.metadata["session_original_input"],
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
        )

    def test_continue_card_can_render_pre_framing_directions(self) -> None:
        case_state = run_analysis("想增加一个新手引导浮层，提升新用户发帖率。")

        rendered = render_case_state(case_state)

        self.assertIn("## 我先按这几个方向理解", rendered)
        self.assertIn("## 现在更值得先补", rendered)
        self.assertIn("## 如果先按这个方向继续", rendered)

    def test_pre_framing_can_identify_core_problem_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "目前用户反馈的微信消息太多、打扰频繁，真正要解决的是消息过载问题，还是通知打扰问题，还是群消息管理问题？三者对应的产品方向完全不同，需要先明确核心问题定义。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("核心问题还没收住", rendered)
        self.assertIn("这次最先要收敛的到底是哪一个问题", rendered)
        self.assertIn("现在最大的卡点其实是「核心问题还没收住」", rendered)

    def test_pre_framing_can_identify_colloquial_core_problem_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近很多微信用户都在抱怨群消息太多，重要消息容易被淹没。我现在没想清楚，这次到底该优先解决消息过载、通知打扰，还是群消息筛选问题。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("核心问题还没收住", rendered)
        self.assertNotIn("关键行为门槛或动机不足", rendered)

    def test_pre_framing_can_identify_colloquial_competing_problem_frames(self) -> None:
        case_state = run_analysis_with_context(
            "有些微信用户会在手机切账号时把平板也一起挤下线，很多人抱怨正在看的会话和文档会被打断。我现在没想清楚，这次到底是在解决多设备独立登录场景，还是在解决账号体系和登录安全边界的问题。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "multi-platform",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("核心问题还没收住", rendered)
        self.assertNotIn("关键行为门槛或动机不足", rendered)

    def test_pre_framing_can_handle_alipay_like_competing_problem_frames(self) -> None:
        case_state = run_analysis_with_context(
            "最近不少支付宝用户在抱怨活动体验很怪，明明是在领红包或摇现金，页面却老是跳到自己没想去的地方，花了时间最后奖励还不一定到账。我现在没想清楚，这次到底是在解决活动规则不透明、页面跳转打断，还是奖励到账机制本身不稳定。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("核心问题还没收住", rendered)
        self.assertIn("这次最先要收敛的到底是哪一个问题", rendered)

    def test_pre_framing_can_handle_jd_merchant_like_competing_problem_frames(self) -> None:
        case_state = run_analysis_with_context(
            "最近一些京东秒送商家对接单体验意见很大，单一多电话提醒就一直响，订单里又塞了很多不必要的信息，立即配送和预约单的时间展示也不直观。我现在没想清楚，这次到底是在解决提醒打扰、订单信息过载，还是履约时间标记不清的问题。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("核心问题还没收住", rendered)
        self.assertNotIn("流程执行或责任链不稳定", rendered)

    def test_pre_framing_can_handle_taobao_after_sales_like_competing_problem_frames(self) -> None:
        case_state = run_analysis_with_context(
            "最近淘宝用户对售后和会员权益意见很大，有人下单后才发现不支持七天无理由，提示埋得很深；真去退货时，88VIP 的退货包运费又兑现不了，客服还一直绕。我现在没想清楚，这次到底是在解决下单前提示不清、售后履约断层，还是会员权益兑现机制的问题。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("核心问题还没收住", rendered)
        self.assertIn("如果这轮只解决一件事", rendered)

    def test_pre_framing_can_handle_alipay_like_user_scene_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近支付宝里和账单提醒相关的抱怨变多了，但我现在没想清楚，这轮到底更该面向经常记账的个人用户、帮家里人管钱的中年用户，还是小商家老板。大家对提醒打扰和账目清晰度的在意点明显不一样。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("用户与场景还没钉住", rendered)
        self.assertIn("这次最核心的人群到底是谁", rendered)

    def test_pre_framing_can_handle_taobao_like_user_scene_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近淘宝上不少用户在抱怨首页信息太杂，但我现在没想清楚，这轮到底主要是在服务高频逛街的老用户、低频但目标明确的搜索用户，还是只在大促时进来的活动用户。几类人的浏览路径差得挺远。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("用户与场景还没钉住", rendered)
        self.assertNotIn("关键行为门槛或动机不足", rendered)

    def test_pre_framing_can_handle_jd_like_b_side_user_scene_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近京东秒送商家侧对接单体验意见挺多，但我现在没想清楚，这轮到底更该优先照顾店员、店长，还是区域运营。不同角色都在看订单，但最在意的信息完全不是一回事。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("用户与场景还没钉住", rendered)
        self.assertNotIn("分析卡", rendered)

    def test_pre_framing_can_handle_alipay_like_goal_value_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近支付宝活动页的抱怨不少，但我现在没想清楚，这轮优化到底是要优先提升活动参与率、减少中途退出，还是降低用户对套路感和投诉量。几个目标都能讲通，但不是一回事。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("目标与价值还没钉住", rendered)
        self.assertIn("这次最想优先拉动的目标到底是什么", rendered)

    def test_pre_framing_can_handle_taobao_like_goal_value_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近淘宝售后相关反馈不少，但我现在没想清楚，这次到底是想提升退货发起率、降低售后投诉率，还是提升 88VIP 用户对权益兑现的感知。后面拿什么判断值不值得做，我现在还没有锚点。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("目标与价值还没钉住", rendered)
        self.assertNotIn("分析卡", rendered)

    def test_pre_framing_can_handle_jd_like_b_side_goal_value_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近京东秒送商家侧一直在提接单体验，但我现在没想清楚，这轮到底是要优先提升履约时效、减少漏单，还是先让一线门店觉得系统更好用。如果目标没先定，后面方案很容易越做越散。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("目标与价值还没钉住", rendered)
        self.assertNotIn("流程执行或责任链不稳定", rendered)

    def test_pre_framing_can_handle_alipay_like_scope_boundary_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近支付宝首页入口越做越多，但我现在没想清楚，这次改动到底要不要把账单、出行、借还、活动入口都一起纳进来，还是先只收最常用的那一层。如果一版范围没锁住，后面很容易越改越大。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("范围与边界还没锁住", rendered)
        self.assertIn("这次准备先覆盖哪些对象，不覆盖哪些对象", rendered)

    def test_pre_framing_can_handle_taobao_like_scope_boundary_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近淘宝售后入口的抱怨不少，但我现在没想清楚，这次到底只优化退款申请这一段，还是要把换货、补差价、再次申诉这些链路一起带上。要不要动整个售后主链路，我现在也没锁。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("范围与边界还没锁住", rendered)
        self.assertNotIn("流程执行或责任链不稳定", rendered)

    def test_pre_framing_can_handle_jd_like_b_side_scope_boundary_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近京东秒送商家侧有人提想把接单页重做，但我现在没想清楚，这次只是补充几个状态标记和筛选能力，还是允许直接改掉现有接单主流程。如果边界不先锁住，这个需求很容易长成半次重构。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("范围与边界还没锁住", rendered)
        self.assertNotIn("决策关口卡", rendered)

    def test_pre_framing_can_handle_alipay_like_constraint_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近支付宝活动奖励到账慢的抱怨不少，但我现在没想清楚，这到底是活动服务本身不稳定，还是资金发放、风控校验和账号状态这些底层条件卡住了。现有能力到底支不支持即时到账，我现在也不确定。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("条件与约束还没摸清", rendered)
        self.assertIn("现有底层能力到底支不支持这件事成立", rendered)

    def test_pre_framing_can_handle_taobao_like_constraint_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近淘宝商家和用户都在抱怨售后时效不稳定，但我现在没想清楚，这次想做的能力会不会碰到平台规则、商家履约约束和逆向物流节点这些硬限制。方案看起来能做，不代表条件真的成立。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("条件与约束还没摸清", rendered)
        self.assertNotIn("分析卡", rendered)

    def test_pre_framing_can_handle_jd_like_b_side_constraint_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "最近京东秒送商家侧一直在提接单效率，但我现在没想清楚，这次如果想做自动催单和履约优先级，会不会先碰到门店设备能力、定位精度和骑手侧系统依赖。底层条件如果不成立，前面讨论再顺也没用。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("条件与约束还没摸清", rendered)
        self.assertNotIn("分析卡", rendered)

    def test_pre_framing_can_identify_user_scene_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "本次要优化的消息提醒体验，核心面向的是职场用户、学生用户，还是中老年用户？不同人群的痛点强度与使用场景差异极大。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("用户与场景还没钉住", rendered)
        self.assertIn("这次最核心的人群到底是谁", rendered)

    def test_pre_framing_can_identify_scope_boundary_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "本次要做的消息分类需求，是否包含公众号、小程序通知、群聊、私聊？是否要覆盖所有消息类型，范围未定义。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("范围与边界还没锁住", rendered)
        self.assertIn("这次准备先覆盖哪些对象，不覆盖哪些对象", rendered)

    def test_pre_framing_can_identify_goal_value_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "本次对聊天列表体验的优化，核心目标是提升使用时长、降低卸载率，还是提升关键操作效率？成功指标不明确，需求优先级无法锚定。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("目标与价值还没钉住", rendered)
        self.assertIn("这次最想优先拉动的目标到底是什么", rendered)

    def test_pre_framing_can_identify_constraints_uncertainty(self) -> None:
        case_state = run_analysis_with_context(
            "现有微信后台数据与存储架构，是否支持对消息做实时分类、优先级计算？底层能力是否满足需求前提尚不明确。",
            context_profile={
                "business_model": "toc",
                "primary_platform": "native-app",
            },
        )

        rendered = render_case_state(case_state)

        self.assertEqual(case_state.output_kind, "continue-guidance-card")
        self.assertIn("条件与约束还没摸清", rendered)
        self.assertIn("现有底层能力到底支不支持这件事成立", rendered)

    def test_project_profile_service_can_create_and_load_profile(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_project_profile_store(tmpdir)
            profile = create_project_profile(
                project_name="医疗服务平台",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "mobile-web",
                    "target_user_roles": ["前台", "诊所管理者"],
                },
                stable_constraints=["上线周期紧"],
                success_metrics=["预约到诊率"],
                notes=["主要服务诊所前台场景"],
                store=store,
            )
            loaded_profile = get_project_profile(profile.project_profile_id, store=store)

        self.assertEqual(loaded_profile.project_name, "医疗服务平台")
        self.assertEqual(loaded_profile.context_profile["business_model"], "tob")
        self.assertIn("上线周期紧", loaded_profile.stable_constraints)
        self.assertIn("预约到诊率", loaded_profile.success_metrics)

    def test_case_can_inherit_context_from_project_profile(self) -> None:
        with TemporaryDirectory() as tmpdir:
            case_store = default_store(tmpdir)
            profile_store = default_project_profile_store(tmpdir)
            profile = create_project_profile(
                project_name="医疗服务平台",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "mobile-web",
                    "target_user_roles": ["前台", "诊所管理者"],
                },
                store=profile_store,
            )
            case_state = create_case(
                raw_input="前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
                project_profile=profile,
                context_profile={"product_domain": "医疗服务平台"},
                store=case_store,
            )

        self.assertEqual(case_state.context_profile["business_model"], "tob")
        self.assertEqual(case_state.context_profile["primary_platform"], "mobile-web")
        self.assertEqual(case_state.context_profile["product_domain"], "医疗服务平台")
        self.assertEqual(case_state.metadata["project_profile_name"], "医疗服务平台")

    def test_session_service_can_reply_and_continue(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="这是一个 ToB 移动端产品，前台使用，管理者负责结果。",
                store=store,
            )

        self.assertEqual(replied_case.case_id, case_state.case_id)
        self.assertEqual(replied_case.context_profile["business_model"], "tob")
        self.assertEqual(replied_case.context_profile["primary_platform"], "native-app")
        self.assertIn("前台", replied_case.context_profile["target_user_roles"])
        self.assertIn("管理者", replied_case.context_profile["target_user_roles"])
        self.assertGreaterEqual(len(replied_case.metadata["conversation_turns"]), 2)
        self.assertNotEqual(replied_case.output_kind, "context-question-card")
        self.assertGreaterEqual(len(replied_case.metadata["answered_questions"]), 1)
        self.assertIn(
            "这是一个 ToB 移动端产品，前台使用，管理者负责结果。",
            replied_case.metadata["session_note_buckets"]["context_notes"],
        )
        self.assertEqual(
            replied_case.metadata["latest_user_reply"],
            "这是一个 ToB 移动端产品，前台使用，管理者负责结果。",
        )
        self.assertEqual(replied_case.metadata["last_resume_stage"], "context-alignment")
        validation_claims = [
            finding.claim for finding in replied_case.findings if finding.dimension == "validation-design"
        ]
        self.assertTrue(validation_claims)
        self.assertNotIn("补充场景信息", validation_claims[0])

    def test_session_service_stores_each_follow_up_reply_in_single_primary_note_bucket(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="前台最近老是漏提醒患者，我在想是不是要处理一下。",
                store=store,
            )
            reply_text = "这是一个 ToB 的 HIS 产品，前台在网页端操作提醒，店长会盯结果。"
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text=reply_text,
                store=store,
            )

        self.assertIn(reply_text, replied_case.metadata["session_note_buckets"]["context_notes"])
        self.assertNotIn(reply_text, replied_case.metadata["session_note_buckets"]["decision_notes"])
        self.assertEqual(replied_case.raw_input.count(reply_text), 1)
        self.assertIn("这轮补到的场景背景", replied_case.raw_input)
        self.assertNotIn("补充场景信息", replied_case.raw_input)

    def test_session_service_can_replace_roles_on_explicit_correction(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="最近门店提醒流程总出错，我想看看是不是该处理。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "店长"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="更准确说，不是前台在操作，是护士在操作，店长盯结果。",
                store=store,
            )

        self.assertEqual(replied_case.context_profile["target_user_roles"], ["护士", "店长"])
        self.assertEqual(replied_case.metadata["role_relationships"]["users"], ["护士"])
        self.assertEqual(replied_case.metadata["role_relationships"]["outcome_owners"], ["店长"])

    def test_session_service_only_marks_questions_as_answered_when_reply_is_sufficient(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。",
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="这是一个 ToB 网页端产品，前台在使用。",
                store=store,
            )

        answered_questions = replied_case.metadata["answered_questions"]
        self.assertTrue(
            any("企业产品" in question or "消费者产品" in question or "内部产品" in question for question in answered_questions)
        )
        self.assertFalse(any("谁提出需求、谁使用产品、谁承担最终结果" in question for question in answered_questions))
        self.assertEqual(replied_case.context_profile["primary_platform"], "pc")

    def test_session_service_uses_reply_attribution_to_mark_answered_questions(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input=(
                    "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，"
                    "新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。"
                ),
                store=store,
            )
            interpreter = LLMReplyInterpreter(
                adapter=StubLLMAdapter(
                    content=(
                        '{"answered_pending_questions":["当前的基线数据是多少","停止条件可以怎么定"],'
                        '"partial_pending_questions":["成功指标是什么"],'
                        '"categories":["evidence"],'
                        '"parser_confidence":"strong"}'
                    )
                )
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="当前首帖率大概只有 6%，如果两周内没起色就先停。",
                store=store,
                reply_interpreter=interpreter,
            )

        answered_questions = list(replied_case.metadata.get("answered_questions", []))
        self.assertIn("当前基线指标是什么", answered_questions)
        self.assertIn("失败或停止条件是什么", answered_questions)
        self.assertNotIn("成功指标是什么", answered_questions)
        self.assertEqual(replied_case.metadata.get("last_partial_pending_questions"), ["成功指标是什么"])
        rendered_history = render_case_history(replied_case)
        self.assertIn("最近一轮还差半步的", rendered_history)
        self.assertIn("成功指标是什么", rendered_history)

    def test_partial_answer_can_narrow_follow_up_focus_and_question_order(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input=(
                    "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，"
                    "新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。"
                ),
                store=store,
            )
            interpreter = LLMReplyInterpreter(
                adapter=StubLLMAdapter(
                    content=(
                        '{"partial_pending_questions":["成功指标是什么"],'
                        '"categories":["evidence"],'
                        '"parser_confidence":"strong"}'
                    )
                )
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="我觉得这件事如果能提升一点发帖率就值得看，但具体目标还没想清。",
                store=store,
                reply_interpreter=interpreter,
            )

        self.assertEqual(replied_case.metadata.get("last_partial_pending_questions"), ["成功指标是什么"])
        self.assertEqual(replied_case.metadata.get("follow_up_focus"), "先把刚补到一半的点说完整")
        self.assertIn("还有半步没落稳", replied_case.metadata.get("follow_up_reason", ""))
        self.assertTrue(replied_case.pending_questions)
        self.assertEqual(replied_case.pending_questions[0], "成功指标是什么")
        self.assertEqual(
            replied_case.metadata.get("follow_up_display_questions", [])[0],
            "发帖率方向已经提到了，再补一句：做到什么程度，你会觉得这轮值得继续？",
        )
        rendered_card = render_case_state(replied_case)
        self.assertIn("先把刚补到一半的点说完整", rendered_card)
        self.assertIn("发帖率方向已经提到了，再补一句：做到什么程度，你会觉得这轮值得继续？", rendered_card)

    def test_local_partial_rewrite_templates_can_cover_non_product_and_role_triplet(self) -> None:
        case_state = CaseState(
            case_id="demo-case",
            stage="decision-challenge",
            workflow_state="open",
            output_kind="review-card",
            raw_input="门店提醒总出错，我在想要不要做产品能力。",
            pending_questions=["不改产品能否先解决 60%", "谁提出需求、谁使用产品、谁承担最终结果"],
            metadata={
                "last_partial_pending_questions": ["不改产品能否先解决 60%", "谁提出需求、谁使用产品、谁承担最终结果"],
                "session_note_buckets": {
                    "decision_notes": ["前台和店长都觉得值得看，但还没比较流程和运营能不能先兜住。"],
                },
            },
        )

        apply_follow_up_copywriting(case_state)

        self.assertEqual(
            case_state.metadata.get("follow_up_display_questions"),
            [
                "你已经碰到方向了，再补一句：不改产品的话，先靠流程或运营能不能兜住一部分？",
                "这层已经碰到了，再补一句：谁提、谁在用、最后谁盯结果？",
            ],
        )

    def test_role_relationships_can_influence_problem_framing_judgment(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。",
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="当前这个项目属于 ToB 的 HIS 产品，前台提了这个需求，前台自己就在流程里操作这个动作，店长对结果负责。",
                store=store,
            )

        claims = [finding.claim for finding in replied_case.findings if finding.dimension == "problem-framing"]
        self.assertIn("关键角色已经有了基础分工，接下来更值得补目标差异和协作边界。", claims)

    def test_session_service_tracks_resolved_blocking_gate(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="我们已经试过培训和流程提醒，效果不稳定，还是继续产品化。",
                store=store,
            )

        self.assertEqual(case_state.output_kind, "decision-gate-card")
        self.assertGreaterEqual(len(replied_case.metadata["resolved_gates"]), 1)
        self.assertEqual(replied_case.metadata["last_resume_stage"], "decision-challenge")
        self.assertEqual(replied_case.metadata["resolved_gates"][-1]["user_choice"], "productize-now")
        self.assertEqual(
            replied_case.metadata["resolved_gates"][-1]["resolution_kind"],
            "overrode-recommendation",
        )
        self.assertIn(
            "我们已经试过培训和流程提醒，效果不稳定，还是继续产品化。",
            replied_case.metadata["session_note_buckets"]["decision_notes"],
        )
        self.assertEqual(replied_case.output_kind, "review-card")
        self.assertEqual(replied_case.workflow_state, "done")

    def test_continue_analysis_with_context_can_resume_from_decision_challenge(self) -> None:
        case_state = continue_analysis_with_context(
            raw_input="我们需要优化权限配置流程，避免前台误操作。",
            start_stage="decision-challenge",
            context_profile={
                "business_model": "tob",
                "primary_platform": "pc",
                "target_user_roles": ["前台", "管理员"],
            },
        )
        self.assertEqual(case_state.metadata["selected_modes"], ["decision-challenge"])
        self.assertEqual(case_state.output_kind, "decision-gate-card")

    def test_session_service_can_respect_non_product_choice(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="先试流程和培训，不急着继续产品化。",
                store=store,
            )

        self.assertEqual(replied_case.output_kind, "stage-block-card")
        self.assertEqual(replied_case.metadata["last_gate_choice"], "try-non-product-first")
        self.assertEqual(replied_case.workflow_state, "blocked")

    def test_session_service_can_resume_after_non_product_trial(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            blocked_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="先试流程和培训，不急着继续产品化。",
                store=store,
            )
            resumed_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="已经试过培训和流程提醒，两周后效果回落，还是继续产品化。",
                store=store,
            )

        self.assertEqual(blocked_case.metadata["next_stage"], "decision-challenge")
        self.assertEqual(resumed_case.output_kind, "review-card")
        self.assertEqual(resumed_case.workflow_state, "done")
        self.assertEqual(resumed_case.metadata["last_resume_stage"], "decision-challenge")

    def test_review_card_exposes_follow_up_questions_for_next_round(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input=(
                    "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，"
                    "新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。"
                ),
                store=store,
            )

        self.assertEqual(case_state.output_kind, "review-card")
        self.assertGreater(len(case_state.pending_questions), 0)
        self.assertLessEqual(len(case_state.pending_questions), 3)
        self.assertEqual(case_state.metadata["follow_up_loop_state"], "open")

    def test_reply_can_mark_generic_follow_up_question_as_answered(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input=(
                    "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，"
                    "新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。"
                ),
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text=(
                    "当前首帖率大概只有 6%，如果能拉到 10% 就算有效；"
                    "如果两周内没有明显改善，我们就先停。"
                ),
                store=store,
            )

        answered_questions = list(replied_case.metadata.get("answered_questions", []))
        self.assertTrue(answered_questions)
        self.assertTrue(any("指标" in item or "停止条件" in item for item in answered_questions))
        self.assertFalse(any(item in replied_case.pending_questions for item in answered_questions))
        self.assertIn(
            "当前首帖率大概只有 6%，如果能拉到 10% 就算有效；如果两周内没有明显改善，我们就先停。",
            replied_case.metadata["session_note_buckets"]["evidence_notes"],
        )
        self.assertEqual(replied_case.metadata["last_resume_stage"], "validation-design")
        self.assertNotIn("当前的基线数据是多少", replied_case.pending_questions)

    def test_review_card_metric_reply_resumes_from_validation_design(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input=(
                    "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，"
                    "新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。"
                ),
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="我们先把首帖率从 6% 拉到 10% 当成功线，如果两周没起色就停。",
                store=store,
            )

        self.assertEqual(case_state.output_kind, "review-card")
        self.assertEqual(replied_case.metadata["last_resume_stage"], "validation-design")
        self.assertEqual(replied_case.output_kind, "review-card")
        self.assertEqual(replied_case.workflow_state, "done")
        self.assertNotIn("当前的基线数据是多少", replied_case.pending_questions)

    def test_review_card_why_now_reply_resumes_from_decision_challenge(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input=(
                    "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，"
                    "新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。"
                ),
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="最近增长目标压得比较紧，如果晚两个月做，这块活跃可能会继续掉，而且当前排期也要和别的增长实验抢资源。",
                store=store,
            )

        self.assertEqual(case_state.output_kind, "review-card")
        self.assertEqual(replied_case.metadata["last_resume_stage"], "decision-challenge")
        self.assertEqual(replied_case.output_kind, "review-card")

    def test_session_service_keeps_gate_block_when_choice_is_unclear(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="这个问题确实存在，而且影响挺大。",
                store=store,
            )

        self.assertEqual(case_state.output_kind, "decision-gate-card")
        self.assertEqual(replied_case.output_kind, "decision-gate-card")
        self.assertEqual(replied_case.workflow_state, "blocked")
        self.assertIsNone(replied_case.metadata["last_gate_choice"])

    def test_render_case_history_exposes_session_metadata(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="这是一个 ToB 移动端产品，前台使用，管理者负责结果。",
                store=store,
            )
            rendered = render_case_history(replied_case)

        self.assertIn("## 这段对话里说过什么", rendered)
        self.assertIn("## 这段里已经说清的", rendered)
        self.assertIn("## 这段里补到了哪些信息", rendered)
        self.assertIn("场景背景", rendered)
        self.assertIn("下次大概率会从", rendered)

    def test_session_service_can_use_llm_reply_interpreter(self) -> None:
        adapter = StubLLMAdapter(
            content=(
                '{"context_updates":{"business_model":"toc","primary_platform":"native-app",'
                '"target_user_roles":["新用户","运营"]},"categories":["context"],'
                '"inferred_gate_choice":"productize-now","parser_confidence":"strong"}'
            )
        )
        interpreter = LLMReplyInterpreter(adapter=adapter)
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="想增加一个新手引导浮层，提升新用户发帖率。",
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="这是内容社区的 App，新用户和运营都关心这个问题。",
                store=store,
                reply_interpreter=interpreter,
            )

        self.assertEqual(replied_case.context_profile["business_model"], "toc")
        self.assertEqual(replied_case.context_profile["primary_platform"], "native-app")
        self.assertIn("新用户", replied_case.context_profile["target_user_roles"])
        self.assertEqual(replied_case.metadata["last_reply_parser"], "llm")
        self.assertEqual(len(adapter.requests), 1)

    def test_hybrid_reply_interpreter_can_merge_heuristic_and_llm_results(self) -> None:
        llm_adapter = StubLLMAdapter(
            content=(
                '{"context_updates":{"business_model":"tob","primary_platform":"mobile-web"},'
                '"role_relationships":{"outcome_owners":["老板"]},'
                '"categories":["context","decision"],'
                '"inferred_gate_choice":"defer","parser_confidence":"strong"}'
            )
        )
        interpreter = HybridReplyInterpreter(
            llm_interpreter=LLMReplyInterpreter(adapter=llm_adapter),
            fallback=HeuristicReplyInterpreter(),
        )

        analysis = interpreter.analyze_reply("这个事是运营提的，审核同学每天在用，老板盯结果，资源比较紧张。")

        self.assertEqual(analysis.context_updates["business_model"], "tob")
        self.assertEqual(analysis.context_updates["primary_platform"], "mobile-web")
        self.assertIn("运营", analysis.context_updates["target_user_roles"])
        self.assertIn("审核专员", analysis.context_updates["target_user_roles"])
        self.assertIn("运营", analysis.role_relationships["proposers"])
        self.assertIn("审核专员", analysis.role_relationships["users"])
        self.assertIn("老板", analysis.role_relationships["outcome_owners"])
        self.assertEqual(analysis.inferred_gate_choice, "defer")
        self.assertEqual(analysis.parser_name, "hybrid")

    def test_hybrid_reply_interpreter_prefers_explicit_heuristic_role_relationships(self) -> None:
        llm_adapter = StubLLMAdapter(
            content=(
                '{"role_relationships":{"outcome_owners":["前台","店长"]},'
                '"categories":["context"],"parser_confidence":"strong"}'
            )
        )
        interpreter = HybridReplyInterpreter(
            llm_interpreter=LLMReplyInterpreter(adapter=llm_adapter),
            fallback=HeuristicReplyInterpreter(),
        )

        analysis = interpreter.analyze_reply("前台在网页端操作提醒，店长会盯结果。")

        self.assertEqual(analysis.role_relationships["outcome_owners"], ["店长"])

    def test_hybrid_reply_interpreter_does_not_backfill_multiple_proposers_without_explicit_signal(self) -> None:
        llm_adapter = StubLLMAdapter(
            content=(
                '{"role_relationships":{"proposers":["前台","店长"]},'
                '"categories":["context"],"parser_confidence":"strong"}'
            )
        )
        interpreter = HybridReplyInterpreter(
            llm_interpreter=LLMReplyInterpreter(adapter=llm_adapter),
            fallback=HeuristicReplyInterpreter(),
        )

        analysis = interpreter.analyze_reply("前台在网页端操作提醒，店长会盯结果。")

        self.assertEqual(analysis.role_relationships["proposers"], [])

    def test_hybrid_reply_interpreter_can_backfill_explicit_user_phrase_from_llm(self) -> None:
        llm_adapter = StubLLMAdapter(
            content=(
                '{"role_relationships":{"users":["新用户"]},'
                '"categories":["context"],"parser_confidence":"strong"}'
            )
        )
        interpreter = HybridReplyInterpreter(
            llm_interpreter=LLMReplyInterpreter(adapter=llm_adapter),
            fallback=HeuristicReplyInterpreter(),
        )

        analysis = interpreter.analyze_reply("这是一个内容社区 App，新用户是实际使用者。")

        self.assertEqual(analysis.role_relationships["users"], ["新用户"])

    def test_hybrid_reply_interpreter_does_not_backfill_single_proposer_without_explicit_signal(self) -> None:
        llm_adapter = StubLLMAdapter(
            content=(
                '{"role_relationships":{"proposers":["前台员工"]},'
                '"categories":["context"],"parser_confidence":"strong"}'
            )
        )
        interpreter = HybridReplyInterpreter(
            llm_interpreter=LLMReplyInterpreter(adapter=llm_adapter),
            fallback=HeuristicReplyInterpreter(),
        )

        analysis = interpreter.analyze_reply("这是一个 ToB 的 HIS 产品，前台在网页端操作提醒，店长会盯结果。")

        self.assertEqual(analysis.role_relationships["proposers"], [])

    def test_hybrid_reply_interpreter_does_not_backfill_user_for_non_user_decision_role(self) -> None:
        llm_adapter = StubLLMAdapter(
            content=(
                '{"role_relationships":{"users":["采购负责人"]},'
                '"categories":["context"],"parser_confidence":"strong"}'
            )
        )
        interpreter = HybridReplyInterpreter(
            llm_interpreter=LLMReplyInterpreter(adapter=llm_adapter),
            fallback=HeuristicReplyInterpreter(),
        )

        analysis = interpreter.analyze_reply("采购负责人不是使用者，但会决定是否上线。")

        self.assertIn("采购负责人", analysis.context_updates["target_user_roles"])
        self.assertEqual(analysis.role_relationships["users"], [])

    def test_llm_pre_framing_generator_can_enhance_candidates_without_changing_contract(self) -> None:
        adapter = StubLLMAdapter(
            content=(
                '{"reason":"输入里混着现象和方案，先收方向更稳。",'
                '"candidate_directions":['
                '{"direction_id":"D-101","label":"提醒链路本身不稳定","summary":"核心问题可能在提醒链路而不是单点页面。","assumptions":["当前触发条件不稳定"],"confidence":"medium"},'
                '{"direction_id":"D-102","label":"角色分工没有对齐","summary":"执行者和结果责任人之间可能没有形成稳定协作。","assumptions":["责任边界不清"],"confidence":"medium"}'
                '],'
                '"priority_questions":["现在是谁在触发提醒？","最近为什么更值得处理？"],'
                '"recommended_direction_id":"D-102"}'
            )
        )
        generator = LLMPreFramingGenerator(adapter=adapter)
        case_state = CaseState(
            case_id="demo-case",
            stage="intake",
            raw_input="前台希望增加一个提醒弹窗，避免漏提醒患者。",
            context_profile={},
        )

        result = build_pre_framing_result(case_state, generator=generator)

        self.assertTrue(result.triggered)
        self.assertEqual(result.recommended_direction_id, "D-102")
        self.assertEqual(len(result.candidate_directions), 2)
        self.assertEqual(result.generator_name, "llm")
        self.assertFalse(result.fallback_used)
        self.assertIn("提醒链路本身不稳定", [item.label for item in result.candidate_directions])
        self.assertEqual(len(adapter.requests), 1)
        system_prompt = adapter.requests[0].messages[0].content
        self.assertIn("[身份描述]", system_prompt)
        self.assertIn("[行为规则]", system_prompt)
        self.assertIn("[工具约束]", system_prompt)
        self.assertIn("[输出纪律]", system_prompt)
        self.assertIn("[任务目标]", system_prompt)
        self.assertIn("prompt_layers", adapter.requests[0].metadata)

    def test_llm_pre_framing_generator_can_fall_back_when_adapter_fails(self) -> None:
        generator = LLMPreFramingGenerator(adapter=RaisingLLMAdapter(RuntimeError("gateway-timeout")))
        case_state = CaseState(
            case_id="demo-case",
            stage="intake",
            raw_input="想增加一个新手引导浮层，提升新用户发帖率。",
            context_profile={},
        )

        result = build_pre_framing_result(case_state, generator=generator)

        self.assertTrue(result.triggered)
        self.assertGreaterEqual(len(result.candidate_directions), 1)
        self.assertTrue(result.reason)
        self.assertEqual(result.generator_name, "llm-fallback")
        self.assertTrue(result.fallback_used)
        self.assertIn("RuntimeError", result.fallback_reason)

    def test_llm_case_copywriter_can_only_enhance_copy_slots(self) -> None:
        adapter = StubLLMAdapter(
            content=(
                '{"normalized_summary":"先别急着往方案走，先把问题方向收一收。",'
                '"blocking_reason":"这一步还差一个明确选择，系统才能继续往下推进。",'
                '"next_actions":["先明确你的倾向。","顺手补一句原因。"]}'
            )
        )
        copywriter = LLMCaseCopywriter(adapter=adapter)
        case_state = run_analysis_with_context(
            "我们需要优化权限配置流程，避免前台误操作。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "pc",
                "target_user_roles": ["前台", "管理员"],
            },
        )

        original_stage = case_state.stage
        original_output_kind = case_state.output_kind
        enhanced_case = apply_case_copywriting(case_state, copywriter=copywriter)

        self.assertEqual(enhanced_case.stage, original_stage)
        self.assertEqual(enhanced_case.output_kind, original_output_kind)
        self.assertEqual(enhanced_case.normalized_summary, "先别急着往方案走，先把问题方向收一收。")
        self.assertEqual(enhanced_case.blocking_reason, "这一步还差一个明确选择，系统才能继续往下推进。")
        self.assertEqual(enhanced_case.next_actions, ["先明确你的倾向。", "顺手补一句原因。"])
        self.assertEqual(enhanced_case.metadata["copywriter"], "llm")
        self.assertEqual(enhanced_case.metadata["llm_enhancements"]["copywriter"]["engine"], "llm")
        self.assertFalse(enhanced_case.metadata["llm_enhancements"]["copywriter"]["fallback_used"])
        system_prompt = adapter.requests[0].messages[0].content
        self.assertIn("[角色职责]", system_prompt)
        self.assertIn("[追加要求]", system_prompt)
        self.assertIn("prompt_layers", adapter.requests[0].metadata)

    def test_llm_case_copywriter_can_fall_back_when_adapter_fails(self) -> None:
        copywriter = LLMCaseCopywriter(adapter=RaisingLLMAdapter(RuntimeError("llm-offline")))
        case_state = run_analysis_with_context(
            "我们需要优化权限配置流程，避免前台误操作。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "pc",
                "target_user_roles": ["前台", "管理员"],
            },
        )

        original_summary = case_state.normalized_summary
        original_blocking_reason = case_state.blocking_reason
        original_next_actions = list(case_state.next_actions)
        enhanced_case = apply_case_copywriting(case_state, copywriter=copywriter)

        self.assertEqual(enhanced_case.normalized_summary, original_summary)
        self.assertEqual(enhanced_case.blocking_reason, original_blocking_reason)
        self.assertEqual(enhanced_case.next_actions, original_next_actions)
        self.assertEqual(enhanced_case.metadata["copywriter"], "llm-fallback")
        self.assertTrue(enhanced_case.metadata["llm_enhancements"]["copywriter"]["fallback_used"])
        self.assertIn("RuntimeError", enhanced_case.metadata["llm_enhancements"]["copywriter"]["fallback_reason"])
        rendered_history = render_case_history(enhanced_case)
        self.assertIn("最近走过本地兜底", rendered_history)
        self.assertIn("copywriter", rendered_history)

    def test_llm_follow_up_copywriter_can_only_enhance_display_slots(self) -> None:
        adapter = StubLLMAdapter(
            content=(
                '{"focus_text":"这轮先把判断门槛说清。",'
                '"reason_text":"先把这一层说透，后面就不用来回重写。",'
                '"display_questions":["你现在更偏向先补证据，还是先判断值不值得做？","如果先不做，最可能丢掉什么？"]}'
            )
        )
        copywriter = LLMFollowUpCopywriter(adapter=adapter)
        case_state = CaseState(
            case_id="demo-case",
            stage="decision-challenge",
            workflow_state="open",
            output_kind="continue-guidance-card",
            raw_input="最近新用户发帖率上不去，我还没想清楚要不要做产品改动。",
            normalized_summary="方向已经差不多了，但还要把投入判断看稳。",
            pending_questions=["为什么现在更值得做", "如果晚两个月做，会损失什么"],
            metadata={
                "follow_up_focus": "先把值不值得做看清",
                "follow_up_reason": "这轮已经能看到方向，但还差几项信息才能把投入判断看稳。",
            },
        )

        original_pending_questions = list(case_state.pending_questions)
        enhanced_case = apply_follow_up_copywriting(case_state, copywriter=copywriter)

        self.assertEqual(enhanced_case.pending_questions, original_pending_questions)
        self.assertEqual(enhanced_case.metadata[FOLLOW_UP_DISPLAY_FOCUS_KEY], "这轮先把判断门槛说清。")
        self.assertEqual(enhanced_case.metadata[FOLLOW_UP_DISPLAY_REASON_KEY], "先把这一层说透，后面就不用来回重写。")
        self.assertEqual(
            enhanced_case.metadata[FOLLOW_UP_DISPLAY_QUESTIONS_KEY],
            ["你现在更偏向先补证据，还是先判断值不值得做？", "如果先不做，最可能丢掉什么？"],
        )
        self.assertEqual(enhanced_case.metadata["follow_up_copywriter"], "llm")
        self.assertFalse(enhanced_case.metadata["llm_enhancements"]["follow-up-copywriter"]["fallback_used"])
        rendered = render_case_state(enhanced_case)
        self.assertIn("这轮更值得先收", rendered)
        self.assertIn("这轮先把判断门槛说清。", rendered)
        self.assertIn("为什么先收这个", rendered)
        self.assertIn("你现在更偏向先补证据，还是先判断值不值得做？", rendered)
        system_prompt = adapter.requests[0].messages[0].content
        self.assertIn("[角色职责]", system_prompt)
        self.assertIn("prompt_layers", adapter.requests[0].metadata)

    def test_llm_follow_up_copywriter_can_fall_back_when_adapter_fails(self) -> None:
        copywriter = LLMFollowUpCopywriter(adapter=RaisingLLMAdapter(RuntimeError("llm-offline")))
        case_state = CaseState(
            case_id="demo-case",
            stage="problem-definition",
            workflow_state="open",
            output_kind="continue-guidance-card",
            raw_input="最近门店提醒流程总出错，我想看看是不是该处理。",
            pending_questions=["这件事平时是谁在具体操作，和提出需求的人是不是同一类人？"],
            metadata={
                "follow_up_focus": "先把问题收稳",
                "follow_up_reason": "这轮已经有基础判断了，再补最关键的几项会更顺。",
            },
        )

        enhanced_case = apply_follow_up_copywriting(case_state, copywriter=copywriter)

        self.assertNotIn(FOLLOW_UP_DISPLAY_FOCUS_KEY, enhanced_case.metadata)
        self.assertNotIn(FOLLOW_UP_DISPLAY_REASON_KEY, enhanced_case.metadata)
        self.assertNotIn(FOLLOW_UP_DISPLAY_QUESTIONS_KEY, enhanced_case.metadata)
        self.assertEqual(enhanced_case.metadata["follow_up_copywriter"], "llm-fallback")
        self.assertTrue(enhanced_case.metadata["llm_enhancements"]["follow-up-copywriter"]["fallback_used"])
        self.assertIn(
            "RuntimeError",
            enhanced_case.metadata["llm_enhancements"]["follow-up-copywriter"]["fallback_reason"],
        )
        rendered_history = render_case_history(enhanced_case)
        self.assertIn("follow-up-copywriter", rendered_history)

    def test_llm_follow_up_copywriter_request_includes_partial_pending_questions(self) -> None:
        adapter = StubLLMAdapter(
            content='{"focus_text":"先把这半步补完。","reason_text":"顺着刚才那一点继续，会更省来回。"}'
        )
        copywriter = LLMFollowUpCopywriter(adapter=adapter)
        case_state = CaseState(
            case_id="demo-case",
            stage="validation-design",
            workflow_state="open",
            output_kind="continue-guidance-card",
            raw_input="新用户发帖率一直不高，我还在想要不要做引导。",
            pending_questions=["成功指标是什么", "停止条件是什么"],
            metadata={
                "follow_up_focus": "先把刚补到一半的点说完整",
                "follow_up_reason": "你这轮已经碰到关键点了，但还有半步没落稳，顺着这一点补完会更省来回。",
                "last_partial_pending_questions": ["成功指标是什么"],
            },
        )

        apply_follow_up_copywriting(case_state, copywriter=copywriter)

        user_payload = json.loads(adapter.requests[0].messages[1].content)
        self.assertEqual(user_payload["partial_pending_questions"], ["成功指标是什么"])

    def test_llm_demo_scenario_generator_can_normalize_generated_scenarios(self) -> None:
        generator = LLMDemoScenarioGenerator(
            adapter=StubLLMAdapter(
                content=json.dumps(
                    {
                        "scenarios": [
                            {
                                "title": "支付宝提醒过载",
                                "business_model": "toc",
                                "primary_platform": "native-app",
                                "product_domain": "支付服务",
                                "target_user_roles": ["普通用户", "消息运营"],
                                "initial_message": "最近很多人说支付宝消息太多，但我们还没收住要先解决通知打扰还是消息分层。",
                                "follow_up_messages": [
                                    "这个场景主要在 App 里发生，普通用户和消息运营都在盯。",
                                    "现在只知道有人会手动关提醒，还没拆清到底是哪几类消息最烦。",
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
            fallback=StaticDemoScenarioGenerator(),
        )

        result = generator.generate(theme="支付宝", scenario_count=2)

        self.assertEqual(result.generator_name, "llm")
        self.assertFalse(result.fallback_used)
        self.assertEqual(len(result.scenarios), 1)
        self.assertEqual(result.scenarios[0].business_model, "toc")
        self.assertEqual(result.scenarios[0].primary_platform, "native-app")
        self.assertEqual(result.scenarios[0].target_user_roles, ["普通用户", "消息运营"])
        self.assertIn("提醒", result.scenarios[0].title)
        self.assertIn("还没收住", result.scenarios[0].initial_message)

    def test_llm_demo_scenario_generator_can_fall_back_when_adapter_fails(self) -> None:
        generator = LLMDemoScenarioGenerator(
            adapter=RaisingLLMAdapter(RuntimeError("demo-llm-offline")),
            fallback=StaticDemoScenarioGenerator(),
        )

        result = generator.generate(theme="淘宝", scenario_count=2)

        self.assertEqual(result.generator_name, "llm-fallback")
        self.assertTrue(result.fallback_used)
        self.assertIn("RuntimeError", result.fallback_reason)
        self.assertEqual(len(result.scenarios), 2)
        self.assertTrue(any("淘宝" in item.title for item in result.scenarios))

    def test_llm_demo_scenario_generator_can_pull_solution_like_output_back_to_problem_draft(self) -> None:
        generator = LLMDemoScenarioGenerator(
            adapter=StubLLMAdapter(
                content=json.dumps(
                    {
                        "scenarios": [
                            {
                                "title": "支付宝首页生活缴费入口体验提升",
                                "business_model": "toc",
                                "primary_platform": "native-app",
                                "product_domain": "支付服务",
                                "target_user_roles": ["普通用户", "运营"],
                                "initial_message": "建议优化支付宝首页生活缴费入口，提升转化。",
                                "follow_up_messages": [
                                    "增加一个更明显的入口按钮。",
                                    "把生活缴费放到首页金刚位里。",
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
            fallback=StaticDemoScenarioGenerator(),
        )

        result = generator.generate(theme="支付宝", scenario_count=1)

        self.assertEqual(result.generator_name, "llm")
        self.assertEqual(len(result.scenarios), 1)
        self.assertEqual(result.scenarios[0].title, "缴费这块有点不好找")
        self.assertIn("还没想清楚", result.scenarios[0].initial_message)
        self.assertIn("总有人说生活缴费这块不太好找", result.scenarios[0].initial_message)
        self.assertNotIn("入口按钮", result.scenarios[0].follow_up_messages[0])
        self.assertIn("发生在App里", result.scenarios[0].follow_up_messages[0])
        self.assertIn("路径太深", result.scenarios[0].follow_up_messages[1])

    def test_llm_demo_scenario_generator_can_humanize_short_noun_titles(self) -> None:
        generator = LLMDemoScenarioGenerator(
            adapter=StubLLMAdapter(
                content=json.dumps(
                    {
                        "scenarios": [
                            {
                                "title": "商家收款码",
                                "business_model": "tob",
                                "primary_platform": "multi-platform",
                                "product_domain": "商户服务",
                                "target_user_roles": ["小商家店主", "连锁店运营"],
                                "initial_message": "想优化商家收款码相关体验。",
                                "follow_up_messages": [
                                    "完善收款码相关入口和说明。",
                                    "优化门店操作流程。",
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
            fallback=StaticDemoScenarioGenerator(),
        )

        result = generator.generate(theme="支付宝", scenario_count=1)

        self.assertEqual(result.scenarios[0].title, "收款码这块老有人来问")
        self.assertIn("反复来问", result.scenarios[0].initial_message)
        self.assertIn("入口太绕", result.scenarios[0].follow_up_messages[1])

    def test_llm_demo_scenario_generator_can_align_title_with_live_stream_context(self) -> None:
        generator = LLMDemoScenarioGenerator(
            adapter=StubLLMAdapter(
                content=json.dumps(
                    {
                        "scenarios": [
                            {
                                "title": "首页流量分发",
                                "business_model": "tob",
                                "primary_platform": "pc",
                                "product_domain": "电商直播",
                                "target_user_roles": ["直播商家运营", "直播场控"],
                                "initial_message": "最近商家反馈直播间的流量分配不太稳定，有时候开播半小时了，观看人数还是上不去。",
                                "follow_up_messages": [
                                    "有些场控说同一场直播前后波动很大。",
                                    "现在还没拆清是内容不对，还是流量机制有问题。",
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
            fallback=StaticDemoScenarioGenerator(),
        )

        result = generator.generate(theme="淘宝", scenario_count=1)

        self.assertEqual(result.scenarios[0].title, "直播间流量有点不稳")
        self.assertIn("流量分配不太稳定", result.scenarios[0].initial_message)

    def test_llm_demo_scenario_generator_can_rewrite_explicit_solution_intent(self) -> None:
        generator = LLMDemoScenarioGenerator(
            adapter=StubLLMAdapter(
                content=json.dumps(
                    {
                        "scenarios": [
                            {
                                "title": "配送员激励方案",
                                "business_model": "tob",
                                "primary_platform": "mobile-web",
                                "product_domain": "本地即时配送",
                                "target_user_roles": ["配送员", "区域运营经理"],
                                "initial_message": "最近配送员流失率有点高，想做个激励方案试试看。",
                                "follow_up_messages": [
                                    "可以加一点奖励机制。",
                                    "再做个每周排名。",
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
            fallback=StaticDemoScenarioGenerator(),
        )

        result = generator.generate(theme="京东", scenario_count=1)

        self.assertEqual(result.scenarios[0].title, "配送员最近有点留不住")
        self.assertNotIn("想做个激励方案", result.scenarios[0].initial_message)
        self.assertIn("还没想清楚", result.scenarios[0].initial_message)

    def test_llm_demo_scenario_generator_can_rewrite_solution_intent_for_scheduling(self) -> None:
        generator = LLMDemoScenarioGenerator(
            adapter=StubLLMAdapter(
                content=json.dumps(
                    {
                        "scenarios": [
                            {
                                "title": "医生排班那个事儿",
                                "business_model": "tob",
                                "primary_platform": "pc",
                                "product_domain": "医院管理系统",
                                "target_user_roles": ["科室主任", "行政助理"],
                                "initial_message": "我们医院现在排班还是靠Excel发来发去，经常有冲突，能不能搞个在线协作的。",
                                "follow_up_messages": [
                                    "最好先把排班冲突都自动算出来。",
                                    "具体是哪些科室最容易撞班。",
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
            fallback=StaticDemoScenarioGenerator(),
        )

        result = generator.generate(theme="医疗", scenario_count=1)

        self.assertEqual(result.scenarios[0].title, "排班还是靠表在传")
        self.assertNotIn("能不能搞个在线协作的", result.scenarios[0].initial_message)
        self.assertIn("还是靠表在传", result.scenarios[0].initial_message)
        self.assertIn("现状流程有问题", result.scenarios[0].follow_up_messages[1])

    def test_seed_workspace_demo_can_create_multiple_cases(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            result = seed_workspace_demo(
                shell,
                workspace_id="demo-seed",
                generator=StaticDemoScenarioGenerator(),
                theme="医疗",
                scenario_count=2,
            )

        self.assertEqual(len(result.seeded_case_ids), 2)
        self.assertEqual(result.generation.generator_name, "fallback")
        self.assertTrue(result.latest_response.workspace.active_case_id)
        self.assertEqual(result.latest_response.workspace.workspace_id, "demo-seed")

    def test_layered_prompt_can_accept_project_and_append_overrides_from_env(self) -> None:
        adapter = StubLLMAdapter(
            content='{"categories":["context"],"parser_confidence":"strong"}'
        )
        with patch.dict(
            os.environ,
            {
                "PMMA_PROMPT_PROJECT": "项目里默认使用中文\n优先保守解释",
                "PMMA_PROMPT_APPEND": "输出前先检查是否越权",
            },
            clear=False,
        ):
            interpreter = LLMReplyInterpreter(adapter=adapter)
            interpreter.analyze_reply("这是一个 ToB 的 HIS 产品，前台在网页端操作提醒。")

        system_prompt = adapter.requests[0].messages[0].content
        self.assertIn("[项目规则]", system_prompt)
        self.assertIn("项目里默认使用中文", system_prompt)
        self.assertIn("优先保守解释", system_prompt)
        self.assertIn("[追加要求]", system_prompt)
        self.assertIn("输出前先检查是否越权", system_prompt)

    def test_prompt_composition_can_load_rules_from_repo_directory_and_user_layers(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text(
                "# 团队规则\n- 仓库级规则一\n",
                encoding="utf-8",
            )
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "behavior_rules": ["先看清上下文再动手"],
                        "tool_constraints": ["不要直接改生产配置"],
                        "output_discipline": ["默认用中文输出"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            nested = root / "frontend" / "pages"
            (nested / ".pmma").mkdir(parents=True, exist_ok=True)
            (nested / ".pmma" / "rules.md").write_text(
                "[目录规则]\n- 当前目录优先遵循前端约束\n",
                encoding="utf-8",
            )
            user_rules_path = root / "user-rules.md"
            user_rules_path.write_text(
                "[项目规则]\n- 用户偏好先给结论再解释\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"PMMA_USER_RULES_PATH": str(user_rules_path)},
                clear=False,
            ):
                prompt = build_prompt_composition(
                    identity="测试身份",
                    task_instruction="测试任务",
                    base_dir=str(nested),
                )

        rendered = prompt.render()
        self.assertIn("仓库级规则一", rendered)
        self.assertIn("当前目录优先遵循前端约束", rendered)
        self.assertIn("用户偏好先给结论再解释", rendered)
        self.assertIn("先看清上下文再动手", rendered)
        self.assertIn("不要直接改生产配置", rendered)
        self.assertIn("默认用中文输出", rendered)
        self.assertGreaterEqual(len(prompt.rule_sources), 3)

    def test_runtime_policy_can_load_from_policy_json(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_intents": ["switch-case"],
                            "blocked_actions": ["session-service.create-case"],
                            "approval_required_actions": ["project-profile-service.*"],
                            "auto_approve_actions": ["workspace-service.*"],
                            "auto_expire_approval_actions": ["renderer.case-state"],
                            "manual_approval_only_actions": ["command-executor.run"],
                            "command_allowlist_prefixes": ["git status", "python -m unittest"],
                            "blocked_command_patterns": ["rm *"],
                            "approval_required_command_patterns": ["git push*"],
                            "allowed_read_roots": ["docs", "examples"],
                            "blocked_read_paths": [".env*", "secrets/*"],
                            "approval_required_read_paths": ["docs/internal/*"],
                            "allowed_write_roots": ["src", "tests"],
                            "blocked_write_paths": [".env*", "secrets/*"],
                            "approval_required_write_paths": ["docs/releases/*"],
                            "allow_new_cases": False,
                            "allow_project_profile_updates": False,
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = load_runtime_policy(base_dir=tmpdir)

        self.assertEqual(policy.blocked_intents, ["switch-case"])
        self.assertEqual(policy.blocked_actions, ["session-service.create-case"])
        self.assertEqual(policy.approval_required_actions, ["project-profile-service.*"])
        self.assertEqual(policy.auto_approve_actions, ["workspace-service.*"])
        self.assertEqual(policy.auto_expire_approval_actions, ["renderer.case-state"])
        self.assertEqual(policy.manual_approval_only_actions, ["command-executor.run"])
        self.assertEqual(policy.command_allowlist_prefixes, ["git status", "python -m unittest"])
        self.assertEqual(policy.blocked_command_patterns, ["rm *"])
        self.assertEqual(policy.approval_required_command_patterns, ["git push*"])
        self.assertTrue(policy.allowed_read_roots[0].endswith("/docs"))
        self.assertEqual(policy.blocked_read_paths, [".env*", "secrets/*"])
        self.assertEqual(policy.approval_required_read_paths, ["docs/internal/*"])
        self.assertTrue(policy.allowed_write_roots[0].endswith("/src"))
        self.assertEqual(policy.blocked_write_paths, [".env*", "secrets/*"])
        self.assertEqual(policy.approval_required_write_paths, ["docs/releases/*"])
        self.assertFalse(policy.allow_new_cases)
        self.assertFalse(policy.allow_project_profile_updates)

    def test_runtime_action_policy_can_match_exact_and_wildcard_patterns(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_actions": ["session-service.create-case"],
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = load_runtime_policy(base_dir=tmpdir)

        blocked = check_runtime_action_policy(policy, action_name="session-service.create-case")
        approval = check_runtime_action_policy(policy, action_name="project-profile-service.update-or-create")
        allowed = check_runtime_action_policy(policy, action_name="renderer.case-state")

        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.action_name, "session-service.create-case")
        self.assertIsNotNone(approval)
        self.assertIn("需要先人工确认", approval.reason)
        self.assertIsNone(allowed)

    def test_runtime_approval_handling_can_resolve_manual_auto_approve_and_auto_expire(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "auto_approve_actions": ["workspace-service.*"],
                            "auto_expire_approval_actions": ["renderer.case-state"],
                            "manual_approval_only_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = load_runtime_policy(base_dir=tmpdir)

        manual = resolve_runtime_approval_handling(
            policy,
            action_name="project-profile-service.update-or-create",
            workspace_auto_approve_actions=["project-profile-service.update-or-create"],
        )
        workspace_auto = resolve_runtime_approval_handling(
            policy,
            action_name="case-service.read",
            workspace_auto_approve_actions=["case-service.*"],
        )
        policy_auto = resolve_runtime_approval_handling(
            policy,
            action_name="workspace-service.load-recent-cases",
        )
        auto_expire = resolve_runtime_approval_handling(
            policy,
            action_name="renderer.case-state",
        )

        self.assertEqual(manual.mode, "manual-only")
        self.assertEqual(workspace_auto.mode, "auto-approve")
        self.assertEqual(policy_auto.mode, "auto-approve")
        self.assertEqual(auto_expire.mode, "auto-expire")

    def test_runtime_command_policy_can_enforce_allowlist_blocklist_and_approval(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "command_allowlist_prefixes": ["git status", "python -m unittest"],
                            "blocked_command_patterns": ["rm *"],
                            "approval_required_command_patterns": ["git push*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = load_runtime_policy(base_dir=tmpdir)

        allowed = check_runtime_command_policy(policy, command_args=["git", "status"])
        blocked = check_runtime_command_policy(policy, command_args=["rm", "-rf", "tmp"])
        approval = check_runtime_command_policy(policy, command_args=["git", "push", "origin", "main"])
        disallowed = check_runtime_command_policy(policy, command_args=["git", "commit", "-m", "x"])

        self.assertIsNone(allowed)
        self.assertIsNotNone(blocked)
        self.assertIn("rm -rf tmp", blocked.reason)
        self.assertIsNotNone(approval)
        self.assertIn("需要先人工确认", approval.reason)
        self.assertIsNotNone(disallowed)
        self.assertIn("git commit -m x", disallowed.reason)

    def test_runtime_write_policy_can_enforce_roots_blocklist_and_approval(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "allowed_write_roots": ["src", "tests"],
                            "blocked_write_paths": [".env*", "secrets/*"],
                            "approval_required_write_paths": ["docs/releases/*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = load_runtime_policy(base_dir=tmpdir)

        allowed = check_runtime_write_policy(policy, write_paths=["src/pm_method_agent/runtime_policy.py"])
        blocked = check_runtime_write_policy(policy, write_paths=[".env.local"])
        approval = check_runtime_write_policy(policy, write_paths=["docs/releases/v0.2.0.md"])
        outside = check_runtime_write_policy(policy, write_paths=["README.md"])

        self.assertIsNone(allowed)
        self.assertIsNotNone(blocked)
        self.assertIn(".env.local", blocked.reason)
        self.assertIsNotNone(approval)
        self.assertIn("需要先人工确认", approval.reason)
        self.assertIsNotNone(outside)
        self.assertIn("README.md", outside.reason)

    def test_runtime_read_policy_can_enforce_roots_blocklist_and_approval(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "allowed_read_roots": ["docs", "examples"],
                            "blocked_read_paths": [".env*", "secrets/*"],
                            "approval_required_read_paths": ["docs/internal/*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = load_runtime_policy(base_dir=tmpdir)

        allowed = check_runtime_read_policy(policy, read_paths=["docs/guide.md"])
        blocked = check_runtime_read_policy(policy, read_paths=[".env.local"])
        approval = check_runtime_read_policy(policy, read_paths=["docs/internal/plan.md"])
        outside = check_runtime_read_policy(policy, read_paths=["README.md"])

        self.assertIsNone(allowed)
        self.assertIsNotNone(blocked)
        self.assertIn(".env.local", blocked.reason)
        self.assertIsNotNone(approval)
        self.assertIn("需要先人工确认", approval.reason)
        self.assertIsNotNone(outside)
        self.assertIn("README.md", outside.reason)

    def test_operation_enforcement_can_return_unified_decision(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                            "command_allowlist_prefixes": ["git status"],
                            "allowed_read_roots": ["docs"],
                            "allowed_write_roots": ["src"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = load_runtime_policy(base_dir=tmpdir)

        allowed = evaluate_operation_enforcement(
            policy,
            action_name="renderer.case-state",
            command_args=["git", "status"],
            read_paths=["docs/runtime.md"],
            write_paths=["src/pm_method_agent/runtime_policy.py"],
        )
        blocked = evaluate_operation_enforcement(
            policy,
            action_name="project-profile-service.update-or-create",
            command_args=["git", "status"],
        )

        self.assertTrue(allowed.allowed)
        self.assertEqual([item.decision for item in allowed.checks], ["allowed", "allowed", "allowed", "allowed"])
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.violation_kind, "approval-required")
        self.assertEqual(blocked.checks[0].check_type, "action")

    def test_hook_enforcement_can_run_pre_operation_hook_and_return_decision(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            runtime_session = get_or_create_runtime_session(
                "demo-hooks",
                store=default_runtime_session_store(tmpdir),
            )
            start_runtime_query(runtime_session, message="测试 hook")
            policy = load_runtime_policy(base_dir=tmpdir)

            with self.assertRaises(HookExecutionBlockedError):
                run_pre_operation_hooks(
                    runtime_session,
                    policy,
                    action_name="project-profile-service.update-or-create",
                )

        self.assertEqual(runtime_session.pending_hooks, [])
        event_types = [item["event_type"] for item in runtime_session.event_log]
        self.assertIn("hook-call-requested", event_types)
        self.assertIn("hook-call-completed", event_types)

    def test_runtime_session_can_close_pending_hooks_on_next_query(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_store = default_runtime_session_store(tmpdir)
            runtime_session = get_or_create_runtime_session("demo-hook-close", store=runtime_store)
            runtime_session.current_query_id = "query-0003"
            pending_entry = request_hook_call(
                runtime_session,
                hook_name="demo-hook",
                hook_stage="pre-operation",
                request_payload={"action_name": "demo.action"},
            )
            close_incomplete_hooks(runtime_session, reason="next-query-started")

        self.assertEqual(runtime_session.pending_hooks, [])
        self.assertEqual(pending_entry["hook_name"], "demo-hook")
        self.assertIn("hook-call-failed", [item["event_type"] for item in runtime_session.event_log])

    def test_runtime_session_event_ids_remain_monotonic_after_log_truncation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_store = default_runtime_session_store(tmpdir)
            runtime_session = get_or_create_runtime_session("demo-event-log", store=runtime_store)

            for index in range(RUNTIME_EVENT_LOG_LIMIT + 5):
                append_runtime_event(
                    runtime_session,
                    "demo-event",
                    {"index": index + 1},
                )

            save_runtime_session(runtime_session, store=runtime_store)
            reloaded_session = get_or_create_runtime_session("demo-event-log", store=runtime_store)
            append_runtime_event(reloaded_session, "demo-event", {"index": RUNTIME_EVENT_LOG_LIMIT + 6})

        event_ids = [item["event_id"] for item in reloaded_session.event_log]
        self.assertEqual(len(event_ids), RUNTIME_EVENT_LOG_LIMIT)
        self.assertEqual(len(event_ids), len(set(event_ids)))
        self.assertEqual(event_ids[0], "evt-0007")
        self.assertEqual(event_ids[-1], "evt-0056")

    def test_runtime_session_tool_call_ids_remain_monotonic_after_ledger_truncation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_store = default_runtime_session_store(tmpdir)
            runtime_session = get_or_create_runtime_session("demo-ledger", store=runtime_store)
            runtime_session.current_query_id = "query-0001"

            for index in range(RUNTIME_LEDGER_LIMIT + 5):
                entry = request_tool_call(
                    runtime_session,
                    tool_name="demo-tool",
                    request_payload={"index": index + 1},
                )
                complete_tool_call(runtime_session, call_id=entry["call_id"], result_ref=f"tool:{index + 1}")

            save_runtime_session(runtime_session, store=runtime_store)
            reloaded_session = get_or_create_runtime_session("demo-ledger", store=runtime_store)
            reloaded_session.current_query_id = "query-0002"
            next_entry = request_tool_call(
                reloaded_session,
                tool_name="demo-tool",
                request_payload={"index": RUNTIME_LEDGER_LIMIT + 6},
            )

        call_ids = [item["call_id"] for item in reloaded_session.execution_ledger]
        self.assertEqual(len(call_ids), RUNTIME_LEDGER_LIMIT)
        self.assertEqual(len(call_ids), len(set(call_ids)))
        self.assertEqual(call_ids[0], "call-0007")
        self.assertEqual(call_ids[-1], "call-0106")
        self.assertEqual(next_entry["call_id"], "call-0106")

    def test_runtime_session_hook_ids_remain_monotonic_across_completed_calls(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_store = default_runtime_session_store(tmpdir)
            runtime_session = get_or_create_runtime_session("demo-hooks-monotonic", store=runtime_store)
            runtime_session.current_query_id = "query-0001"

            first = request_hook_call(
                runtime_session,
                hook_name="demo-hook",
                hook_stage="pre-operation",
                request_payload={"index": 1},
            )
            complete_hook_call(runtime_session, hook_call_id=first["hook_call_id"], result_payload={"ok": True})

            second = request_hook_call(
                runtime_session,
                hook_name="demo-hook",
                hook_stage="pre-operation",
                request_payload={"index": 2},
            )
            complete_hook_call(runtime_session, hook_call_id=second["hook_call_id"], result_payload={"ok": True})

            third = request_hook_call(
                runtime_session,
                hook_name="demo-hook",
                hook_stage="pre-operation",
                request_payload={"index": 3},
            )

        self.assertEqual(first["hook_call_id"], "hook-0001")
        self.assertEqual(second["hook_call_id"], "hook-0002")
        self.assertEqual(third["hook_call_id"], "hook-0003")
        self.assertEqual(runtime_session.pending_hooks[-1]["hook_call_id"], "hook-0003")

    def test_cli_rules_command_can_render_effective_rule_layers(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text(
                "# 团队规则\n- 默认使用中文\n",
                encoding="utf-8",
            )
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "behavior_rules": ["先看清上下文再动手"],
                        "runtime_policy": {
                            "blocked_intents": ["switch-case"],
                            "approval_required_actions": ["project-profile-service.*"],
                            "command_allowlist_prefixes": ["git status"],
                            "allowed_read_roots": ["docs"],
                            "allowed_write_roots": ["src"],
                            "allow_new_cases": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["rules", "--base-dir", tmpdir, "--show-prompt"])

        rendered = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("规则概览", rendered)
        self.assertIn("默认使用中文", rendered)
        self.assertIn("先看清上下文再动手", rendered)
        self.assertIn("允许新建案例：否", rendered)
        self.assertIn("`switch-case`", rendered)
        self.assertIn("`project-profile-service.*`", rendered)
        self.assertIn("`git status`", rendered)
        self.assertIn("允许读取根目录", rendered)
        self.assertIn("[身份描述]", rendered)

    def test_agent_shell_can_block_new_case_by_runtime_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "allow_new_cases": False,
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )

        self.assertEqual(response.action, "policy-blocked")
        self.assertIn("不允许直接新建案例", response.message)
        self.assertIn("规则阻塞卡", response.rendered_card)
        self.assertEqual(response.runtime_session.last_terminal_event["terminal_state"], "blocked")

    def test_agent_shell_can_block_switch_case_by_runtime_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_intents": ["switch-case"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "这是一个 ToB 的 PC 后台，前台和管理员在用。我们需要优化权限配置流程，避免前台误操作。",
                workspace_id="demo",
            )
            second_response = shell.handle_message(
                "还有一个问题，新用户注册后发帖率也偏低，想一起看看。",
                workspace_id="demo",
            )
            response = shell.handle_message(
                "切到上一个案例。",
                workspace_id="demo",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(second_response.action, "create-case")
        self.assertEqual(response.action, "policy-blocked")
        self.assertIn("被禁用了", response.message)
        self.assertEqual(response.runtime_session.last_terminal_event["terminal_state"], "cancelled")

    def test_agent_shell_can_block_internal_action_by_runtime_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_actions": ["session-service.create-case"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )

        self.assertEqual(response.action, "policy-blocked")
        self.assertIn("session-service.create-case", response.message)
        self.assertIn("当前动作", response.rendered_card)
        self.assertEqual(response.runtime_session.last_terminal_event["terminal_state"], "blocked")
        self.assertEqual(len(response.runtime_session.pending_hooks), 0)
        self.assertEqual(len(response.runtime_session.execution_ledger), 1)
        event_types = [item["event_type"] for item in response.runtime_session.event_log]
        self.assertIn("hook-call-requested", event_types)
        self.assertIn("hook-call-completed", event_types)
        self.assertEqual(event_types.count("tool-call-requested"), 1)

    def test_agent_shell_can_require_approval_for_internal_action_by_runtime_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "当前这个项目属于 ToB 的 HIS 产品，主要通过网页端使用，前台在操作，店长会看结果。",
                workspace_id="demo",
            )

        self.assertEqual(response.action, "policy-blocked")
        self.assertIn("需要先人工确认", response.message)
        self.assertIn("project-profile-service.update-or-create", response.rendered_card)
        self.assertEqual(response.runtime_session.last_terminal_event["terminal_state"], "blocked")
        self.assertEqual(len(response.runtime_session.pending_hooks), 0)

    def test_llm_case_copywriter_can_soften_stiff_phrases(self) -> None:
        adapter = StubLLMAdapter(
            content=(
                '{"normalized_summary":"问题描述已初步成型，但还需要补充更多证据和角色关系的细节。",'
                '"blocking_reason":"当前先按非产品路径推进，建议先试流程、培训或管理方案。",'
                '"next_actions":["建议先补充现状流程。","当前还没有明确选择。"]}'
            )
        )
        copywriter = LLMCaseCopywriter(adapter=adapter)
        case_state = run_analysis_with_context(
            "我们需要优化权限配置流程，避免前台误操作。",
            context_profile={
                "business_model": "tob",
                "primary_platform": "pc",
                "target_user_roles": ["前台", "管理员"],
            },
        )

        enhanced_case = apply_case_copywriting(case_state, copywriter=copywriter)

        self.assertEqual(enhanced_case.normalized_summary, "方向已经差不多了，但还得补更多证据和角色关系的细节。")
        self.assertEqual(enhanced_case.blocking_reason, "这轮先按非产品路径看，先试流程、培训或管理方案。")
        self.assertEqual(enhanced_case.next_actions, ["先补充现状流程。", "这轮还没明确选择。"])

    def test_build_case_copywriter_from_env_requires_explicit_flag(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PMMA_LLM_ENABLED": "1",
                "PMMA_LLM_BASE_URL": "https://api.deepseek.com",
                "PMMA_LLM_API_KEY": "demo-key",
                "PMMA_LLM_MODEL": "deepseek-chat",
                "PMMA_LLM_PROVIDER": "deepseek",
                "PMMA_LLM_COPYWRITER_ENABLED": "1",
            },
            clear=False,
        ):
            copywriter = build_case_copywriter_from_env()

        self.assertIsNotNone(copywriter)

    def test_runtime_config_can_load_env_local_without_overriding_existing_env(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text("PMMA_LLM_MODEL=base-model\n", encoding="utf-8")
            (root / ".env.local").write_text(
                "PMMA_LLM_BASE_URL=https://api.deepseek.com\n"
                "PMMA_LLM_MODEL=deepseek-chat\n"
                "PMMA_LLM_PROVIDER=deepseek\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "PMMA_DISABLE_ENV_AUTOLOAD": "0",
                    "PMMA_LLM_ENABLED": "1",
                    "PMMA_LLM_API_KEY": "env-key",
                },
                clear=False,
            ):
                ensure_local_env_loaded(tmpdir)
                runtime = get_llm_runtime_status(tmpdir)
                self.assertEqual(os.getenv("PMMA_LLM_MODEL"), "deepseek-chat")
                self.assertEqual(runtime["provider"], "deepseek")

    def test_rendered_card_can_show_llm_runtime_summary(self) -> None:
        case_state = run_analysis("前台希望增加一个预约前提醒弹窗，避免漏提醒患者。")
        case_state.metadata["llm_runtime"] = {"summary": "LLM 混合（回复解释、前置收敛）"}

        rendered = render_case_state(case_state)

        self.assertIn("增强模式", rendered)
        self.assertIn("LLM 混合（回复解释、前置收敛）", rendered)

    def test_build_case_runtime_payload_can_expose_fallback_components(self) -> None:
        case_state = run_analysis("前台希望增加一个预约前提醒弹窗，避免漏提醒患者。")
        case_state.metadata["llm_runtime"] = {"summary": "LLM 混合（回复解释、前置收敛、文案增强）"}
        case_state.metadata["llm_enhancements"] = {
            "reply-interpreter": {
                "engine": "hybrid-fallback",
                "fallback_used": True,
                "fallback_reason": "RuntimeError: network-down",
            },
            "copywriter": {
                "engine": "llm",
                "fallback_used": False,
                "fallback_reason": "",
            },
        }

        payload = build_case_runtime_payload(case_state)

        self.assertEqual(payload["summary"], "LLM 混合（回复解释、前置收敛、文案增强）")
        self.assertTrue(payload["fallback_active"])
        self.assertEqual(payload["fallback_count"], 1)
        self.assertEqual(payload["fallback_components"], ["reply-interpreter"])

    def test_http_service_can_create_reply_and_load_history(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            create_response = service.handle(
                method="POST",
                path="/cases",
                body=(
                    '{"input":"前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",'
                    '"context_profile":{"business_model":"tob","primary_platform":"mobile-web",'
                    '"target_user_roles":["前台","诊所管理者"]}}'
                ).encode("utf-8"),
            )
            case_id = str(create_response.payload["case"]["case_id"])
            reply_response = service.handle(
                method="POST",
                path=f"/cases/{case_id}/reply",
                body='{"reply":"现在前台是手动翻表提醒，最近两周漏了 6 次。"}'.encode("utf-8"),
            )
            history_response = service.handle(
                method="GET",
                path=f"/cases/{case_id}/history",
            )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(reply_response.status_code, 200)
        self.assertEqual(history_response.status_code, 200)
        self.assertIn("rendered_card", create_response.payload)
        self.assertIn("case_runtime", create_response.payload)
        self.assertIn("summary", create_response.payload["case_runtime"])
        self.assertIn("history", history_response.payload)
        self.assertIn("case_runtime", history_response.payload["history"])
        self.assertIn("rendered_history", history_response.payload)
        self.assertEqual(history_response.payload["case_id"], case_id)

    def test_http_service_returns_not_found_for_missing_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(method="GET", path="/cases/case-missing")

        self.assertEqual(response.status_code, 404)

    def test_http_service_can_serve_web_demo_shell_and_assets(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            html_response = service.handle(method="GET", path="/")
            css_response = service.handle(method="GET", path="/assets/web-demo.css")
            js_response = service.handle(method="GET", path="/assets/web-demo.js")
            favicon_response = service.handle(method="GET", path="/assets/favicon.svg")
            favicon_ico_response = service.handle(method="GET", path="/favicon.ico")

        self.assertEqual(html_response.status_code, 200)
        self.assertEqual(html_response.content_type, "text/html; charset=utf-8")
        self.assertIn("PM Method Agent", html_response.encoded_body().decode("utf-8"))
        self.assertIn("/assets/web-demo.js", html_response.encoded_body().decode("utf-8"))
        self.assertIn("/assets/favicon.svg", html_response.encoded_body().decode("utf-8"))
        self.assertIn("运行时", html_response.encoded_body().decode("utf-8"))
        self.assertIn("refreshRuntimeButton", html_response.encoded_body().decode("utf-8"))
        self.assertIn("seedWorkspaceButton", html_response.encoded_body().decode("utf-8"))

        self.assertEqual(css_response.status_code, 200)
        self.assertEqual(css_response.content_type, "text/css; charset=utf-8")
        self.assertIn(".page-shell", css_response.encoded_body().decode("utf-8"))

        self.assertEqual(js_response.status_code, 200)
        self.assertEqual(js_response.content_type, "application/javascript; charset=utf-8")
        self.assertIn("loadWorkspace", js_response.encoded_body().decode("utf-8"))
        self.assertIn("case_runtime", js_response.encoded_body().decode("utf-8"))
        self.assertIn("loadRuntimeSession", js_response.encoded_body().decode("utf-8"))
        self.assertIn("/runtime/session", js_response.encoded_body().decode("utf-8"))
        self.assertIn("runtimeLoopLabel", js_response.encoded_body().decode("utf-8"))
        self.assertIn("pickRuntimeHighlights", js_response.encoded_body().decode("utf-8"))
        self.assertIn("seedWorkspaceDemo", js_response.encoded_body().decode("utf-8"))
        self.assertIn("renderWorkingMemoryItem", js_response.encoded_body().decode("utf-8"))
        self.assertIn("需要人工确认", js_response.encoded_body().decode("utf-8"))
        self.assertIn("历史已收拢", js_response.encoded_body().decode("utf-8"))
        self.assertIn("眼下正带着哪些线索", js_response.encoded_body().decode("utf-8"))
        self.assertIn("更早的内容怎么被收住", js_response.encoded_body().decode("utf-8"))
        self.assertNotIn("发起工具调用", js_response.encoded_body().decode("utf-8"))
        self.assertNotIn("发起 hook", js_response.encoded_body().decode("utf-8"))
        self.assertNotIn("发出终止事件", js_response.encoded_body().decode("utf-8"))

        self.assertEqual(favicon_response.status_code, 200)
        self.assertEqual(favicon_response.content_type, "image/svg+xml")
        self.assertIn("<svg", favicon_response.encoded_body().decode("utf-8"))

        self.assertEqual(favicon_ico_response.status_code, 200)
        self.assertEqual(favicon_ico_response.content_type, "image/svg+xml")

    def test_http_service_can_seed_demo_workspace_cases(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(
                method="POST",
                path="/workspaces/demo-seed/demo-seed",
                body=json.dumps(
                    {
                        "theme": "医疗",
                        "scenario_count": 2,
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("workspace", response.payload)
        self.assertIn("cases", response.payload)
        self.assertIn("seed_result", response.payload)
        self.assertIn("runtime_session", response.payload)
        self.assertIn("case", response.payload)
        self.assertEqual(response.payload["workspace"]["workspace_id"], "demo-seed")
        self.assertEqual(len(response.payload["seed_result"]["seeded_case_ids"]), 2)
        self.assertIn("generation", response.payload["seed_result"])

    def test_http_service_health_can_expose_llm_runtime(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(method="GET", path="/health")

        self.assertEqual(response.status_code, 200)
        self.assertIn("llm_runtime", response.payload)

    def test_http_service_can_expose_runtime_policy_and_enforcement_decision(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                            "command_allowlist_prefixes": ["git status"],
                            "allowed_write_roots": ["src"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            policy_response = service.handle(method="GET", path="/runtime/policy")
            evaluate_response = service.handle(
                method="POST",
                path="/runtime/policy/evaluate",
                body=json.dumps(
                    {
                        "action_name": "project-profile-service.update-or-create",
                        "command_args": ["git", "status"],
                        "write_paths": ["src/pm_method_agent/runtime_policy.py"],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(policy_response.status_code, 200)
        self.assertIn("runtime_policy", policy_response.payload)
        self.assertEqual(evaluate_response.status_code, 200)
        self.assertFalse(evaluate_response.payload["decision"]["allowed"])
        self.assertEqual(evaluate_response.payload["decision"]["violation_kind"], "approval-required")
        self.assertEqual(evaluate_response.payload["decision"]["checks"][0]["check_type"], "action")

    def test_http_service_can_list_and_execute_local_tools(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "command_allowlist_prefixes": [f"{sys.executable} -c"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            list_response = service.handle(method="GET", path="/runtime/tools")
            describe_response = service.handle(method="GET", path="/runtime/tools/local-command")
            exec_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "local-command",
                        "workspace_id": "tool-http",
                        "command_args": [sys.executable, "-c", "print('via-tool-http')"],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.payload["tools"][0]["tool_name"], "local-command")
        self.assertIn("input_schema", list_response.payload["tools"][0])
        self.assertEqual(list_response.payload["tools"][0]["execution_scope"], "local")
        self.assertIn("platform-workspace-overview", [item["tool_name"] for item in list_response.payload["tools"]])
        self.assertEqual(describe_response.status_code, 200)
        self.assertEqual(describe_response.payload["tool"]["tool_name"], "local-command")
        self.assertTrue(describe_response.payload["tool"]["supports_command_args"])
        self.assertEqual(exec_response.status_code, 200)
        self.assertEqual(exec_response.payload["tool_name"], "local-command")
        self.assertEqual(exec_response.payload["result"]["tool_name"], "local-command")
        self.assertIn("via-tool-http", exec_response.payload["result"]["stdout"])

    def test_local_text_file_writer_can_write_allowed_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "allowed_write_roots": ["notes"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            writer = LocalTextFileWriter(base_dir=tmpdir)
            result = writer.write_text(
                path="notes/demo.txt",
                content="hello tool runtime",
                workspace_id="file-demo",
            )
            written = (root / "notes" / "demo.txt").read_text(encoding="utf-8")

        self.assertTrue(result.allowed)
        self.assertEqual(result.action, "file-written")
        self.assertEqual(written, "hello tool runtime")
        self.assertEqual(result.output_payload["characters_written"], 18)

    def test_local_directory_lister_can_list_directory_entries(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "a.txt").write_text("a", encoding="utf-8")
            (root / "notes" / "sub").mkdir(parents=True, exist_ok=True)
            (root / "notes" / ".hidden").write_text("h", encoding="utf-8")
            lister = LocalDirectoryLister(base_dir=tmpdir)
            result = lister.list_directory(
                path="notes",
                workspace_id="dir-list-demo",
            )

        entry_names = [item["name"] for item in result.output_payload["entries"]]
        self.assertTrue(result.allowed)
        self.assertEqual(result.action, "directory-listed")
        self.assertEqual(entry_names, ["a.txt", "sub"])
        self.assertFalse(result.output_payload["include_hidden"])

    def test_local_directory_lister_can_be_blocked_by_read_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_read_paths": ["notes/private"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "notes" / "private").mkdir(parents=True, exist_ok=True)
            lister = LocalDirectoryLister(base_dir=tmpdir)
            result = lister.list_directory(
                path="notes/private",
                workspace_id="dir-list-demo",
            )

        self.assertFalse(result.allowed)
        self.assertEqual(result.action, "directory-list-blocked")
        self.assertEqual(result.terminal_state, "blocked")
        self.assertIn("notes/private", result.reason)

    def test_local_directory_lister_can_limit_entry_count(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "a.txt").write_text("a", encoding="utf-8")
            (root / "notes" / "b.txt").write_text("b", encoding="utf-8")
            lister = LocalDirectoryLister(base_dir=tmpdir)
            result = lister.list_directory(
                path="notes",
                workspace_id="dir-list-demo",
                max_entries=1,
            )

        self.assertTrue(result.allowed)
        self.assertEqual(result.output_payload["entry_count"], 1)
        self.assertTrue(result.output_payload["truncated"])

    def test_local_text_file_reader_can_read_existing_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "demo.txt").write_text("hello reader", encoding="utf-8")
            reader = LocalTextFileReader(base_dir=tmpdir)
            result = reader.read_text(
                path="notes/demo.txt",
                workspace_id="file-read-demo",
            )

        self.assertTrue(result.allowed)
        self.assertEqual(result.action, "file-read")
        self.assertEqual(result.output_payload["content"], "hello reader")
        self.assertFalse(result.output_payload["truncated"])

    def test_local_text_searcher_can_search_directory(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "a.txt").write_text("hello world\nnext line", encoding="utf-8")
            (root / "notes" / "b.txt").write_text("something else\nHello there", encoding="utf-8")
            searcher = LocalTextSearcher(base_dir=tmpdir)
            result = searcher.search_text(
                path="notes",
                query="hello",
                workspace_id="text-search-demo",
            )

        self.assertTrue(result.allowed)
        self.assertEqual(result.action, "text-searched")
        self.assertEqual(result.output_payload["match_count"], 2)
        self.assertEqual(result.output_payload["matches"][0]["relative_path"], "a.txt")

    def test_local_text_searcher_can_be_blocked_by_read_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_read_paths": ["notes/private"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "notes" / "private").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "private" / "a.txt").write_text("hello", encoding="utf-8")
            searcher = LocalTextSearcher(base_dir=tmpdir)
            result = searcher.search_text(
                path="notes/private",
                query="hello",
                workspace_id="text-search-demo",
            )

        self.assertFalse(result.allowed)
        self.assertEqual(result.action, "text-search-blocked")
        self.assertEqual(result.terminal_state, "blocked")
        self.assertIn("notes/private", result.reason)

    def test_local_text_searcher_can_limit_result_count(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "a.txt").write_text("hello\nhello\nhello", encoding="utf-8")
            searcher = LocalTextSearcher(base_dir=tmpdir)
            result = searcher.search_text(
                path="notes",
                query="hello",
                workspace_id="text-search-demo",
                max_results=2,
            )

        self.assertTrue(result.allowed)
        self.assertEqual(result.output_payload["match_count"], 2)
        self.assertTrue(result.output_payload["truncated"])

    def test_local_text_file_reader_can_be_blocked_by_read_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_read_paths": ["notes/secret.txt"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "secret.txt").write_text("hidden", encoding="utf-8")
            reader = LocalTextFileReader(base_dir=tmpdir)
            result = reader.read_text(
                path="notes/secret.txt",
                workspace_id="file-read-demo",
            )

        self.assertFalse(result.allowed)
        self.assertEqual(result.action, "file-read-blocked")
        self.assertEqual(result.terminal_state, "blocked")
        self.assertEqual(result.violation_kind, "blocked")
        self.assertIn("notes/secret.txt", result.reason)

    def test_local_text_file_reader_can_truncate_large_content(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "demo.txt").write_text("abcdefghij", encoding="utf-8")
            reader = LocalTextFileReader(base_dir=tmpdir)
            result = reader.read_text(
                path="notes/demo.txt",
                workspace_id="file-read-demo",
                max_characters=4,
            )

        self.assertTrue(result.allowed)
        self.assertEqual(result.output_payload["content"], "abcd")
        self.assertTrue(result.output_payload["truncated"])
        self.assertEqual(result.output_payload["max_characters"], 4)

    def test_local_text_file_writer_can_be_blocked_by_write_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_write_paths": ["notes/secret.txt"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            writer = LocalTextFileWriter(base_dir=tmpdir)
            result = writer.write_text(
                path="notes/secret.txt",
                content="blocked",
                workspace_id="file-demo",
            )

        self.assertFalse(result.allowed)
        self.assertEqual(result.action, "file-write-blocked")
        self.assertEqual(result.terminal_state, "blocked")
        self.assertFalse((root / "notes" / "secret.txt").exists())

    def test_http_service_can_execute_local_text_file_write_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "allowed_write_roots": ["notes"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            list_response = service.handle(method="GET", path="/runtime/tools")
            write_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "local-text-file-write",
                        "workspace_id": "file-http",
                        "path": "notes/http.txt",
                        "content": "from http",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            written = (root / "notes" / "http.txt").read_text(encoding="utf-8")

        tool_names = [item["tool_name"] for item in list_response.payload["tools"]]
        self.assertIn("local-text-file-write", tool_names)
        self.assertEqual(write_response.status_code, 200)
        self.assertEqual(write_response.payload["tool_name"], "local-text-file-write")
        self.assertEqual(write_response.payload["result"]["action"], "file-written")
        self.assertEqual(written, "from http")

    def test_http_service_can_execute_platform_workspace_overview_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            case_store = default_store(tmpdir)
            workspace_store = default_workspace_store(tmpdir)
            case_state = create_case(
                raw_input="前台希望减少漏提醒。",
                context_profile={"business_model": "tob"},
                store=case_store,
            )
            workspace = get_or_create_workspace("platform-http", store=workspace_store)
            activate_workspace_case(workspace, case_state.case_id)
            save_workspace(workspace, store=workspace_store)
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "platform-workspace-overview",
                        "workspace_id": "platform-http",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["tool_name"], "platform-workspace-overview")
        self.assertEqual(response.payload["result"]["action"], "platform-workspace-loaded")
        self.assertEqual(response.payload["result"]["output_payload"]["workspace"]["active_case_id"], case_state.case_id)
        self.assertIsNotNone(response.payload["result"]["runtime_session"])

    def test_http_service_can_execute_local_text_file_read_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "http-read.txt").write_text("from http read", encoding="utf-8")
            service = PMMethodHTTPService(store_dir=tmpdir)
            read_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "local-text-file-read",
                        "workspace_id": "file-http-read",
                        "path": "notes/http-read.txt",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.payload["tool_name"], "local-text-file-read")
        self.assertEqual(read_response.payload["result"]["action"], "file-read")
        self.assertEqual(read_response.payload["result"]["output_payload"]["content"], "from http read")

    def test_http_service_can_execute_local_text_search_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "http-search.txt").write_text("alpha\nbeta\nalpha", encoding="utf-8")
            service = PMMethodHTTPService(store_dir=tmpdir)
            search_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "local-text-search",
                        "workspace_id": "search-http",
                        "path": "notes",
                        "query": "alpha",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.payload["tool_name"], "local-text-search")
        self.assertEqual(search_response.payload["result"]["action"], "text-searched")
        self.assertEqual(search_response.payload["result"]["output_payload"]["match_count"], 2)

    def test_http_service_can_execute_local_directory_list_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "http-list.txt").write_text("ok", encoding="utf-8")
            service = PMMethodHTTPService(store_dir=tmpdir)
            list_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "local-directory-list",
                        "workspace_id": "dir-http",
                        "path": "notes",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.payload["tool_name"], "local-directory-list")
        self.assertEqual(list_response.payload["result"]["action"], "directory-listed")
        self.assertEqual(list_response.payload["result"]["output_payload"]["entries"][0]["name"], "http-list.txt")

    def test_http_service_policy_evaluate_can_check_read_paths(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "allowed_read_roots": ["docs"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            evaluate_response = service.handle(
                method="POST",
                path="/runtime/policy/evaluate",
                body=json.dumps(
                    {
                        "action_name": "text-file-reader.read",
                        "read_paths": ["README.md"],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(evaluate_response.status_code, 200)
        self.assertFalse(evaluate_response.payload["decision"]["allowed"])
        self.assertEqual(evaluate_response.payload["decision"]["checks"][1]["check_type"], "read-path")

    def test_cli_tool_command_can_execute_local_text_file_write_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "allowed_write_roots": ["notes"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "local-text-file-write",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "file-cli",
                                "path": "notes/cli.txt",
                                "content": "from cli",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
            payload = json.loads(stdout.getvalue())
            written = (root / "notes" / "cli.txt").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["tool_name"], "local-text-file-write")
        self.assertEqual(payload["action"], "file-written")
        self.assertEqual(written, "from cli")

    def test_cli_tool_command_can_list_and_describe_tools(self) -> None:
        with TemporaryDirectory() as tmpdir:
            list_stdout = StringIO()
            with redirect_stdout(list_stdout):
                list_exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--list",
                    ]
                )
            describe_stdout = StringIO()
            with redirect_stdout(describe_stdout):
                describe_exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--describe",
                        "local-text-file-read",
                    ]
                )

        list_payload = json.loads(list_stdout.getvalue())
        describe_payload = json.loads(describe_stdout.getvalue())
        tool_names = [item["tool_name"] for item in list_payload["tools"]]

        self.assertEqual(list_exit_code, 0)
        self.assertIn("local-directory-list", tool_names)
        self.assertIn("local-text-file-read", tool_names)
        self.assertIn("local-text-search", tool_names)
        self.assertIn("platform-workspace-overview", tool_names)
        self.assertEqual(describe_exit_code, 0)
        self.assertEqual(describe_payload["tool_name"], "local-text-file-read")
        self.assertEqual(describe_payload["kind"], "file-read")
        self.assertEqual(describe_payload["execution_scope"], "local")
        self.assertIn("path", describe_payload["input_schema"]["required"])

    def test_cli_tool_command_can_execute_platform_case_read_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            case_store = default_store(tmpdir)
            case_state = create_case(
                raw_input="想提升新用户发帖率。",
                context_profile={"business_model": "toc", "primary_platform": "native-app"},
                store=case_store,
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "platform-case-read",
                        "--payload-json",
                        json.dumps(
                            {
                                "case_id": case_state.case_id,
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["tool_name"], "platform-case-read")
        self.assertEqual(payload["action"], "platform-case-loaded")
        self.assertEqual(payload["output_payload"]["case"]["case_id"], case_state.case_id)
        self.assertIsNotNone(payload["runtime_session"])

    def test_cli_tool_command_can_execute_platform_project_profile_upsert_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "platform-project-profile-upsert",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "platform-upsert-cli",
                                "project_name": "医疗服务平台",
                                "context_profile": {
                                    "business_model": "tob",
                                    "primary_platform": "mobile-web",
                                },
                                "notes": ["当前主要面向诊所场景"],
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["tool_name"], "platform-project-profile-upsert")
        self.assertEqual(payload["action"], "platform-project-profile-created")
        self.assertEqual(payload["output_payload"]["project_profile"]["project_name"], "医疗服务平台")
        self.assertIsNotNone(payload["runtime_session"])

    def test_platform_project_profile_upsert_tool_can_be_blocked_by_action_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "platform-project-profile-upsert",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "platform-upsert-cli",
                                "project_name": "医疗服务平台",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["tool_name"], "platform-project-profile-upsert")
        self.assertEqual(payload["action"], "platform-project-profile-upsert-blocked")
        self.assertEqual(payload["terminal_state"], "blocked")
        self.assertEqual(payload["violation_kind"], "approval-required")
        self.assertEqual(payload["output_payload"]["pending_approval"]["tool_name"], "platform-project-profile-upsert")
        self.assertEqual(payload["runtime_session"]["pending_approvals"][0]["approval_id"], "approval-0001")

    def test_http_service_can_list_and_approve_pending_platform_write_operation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            blocked_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "platform-project-profile-upsert",
                        "workspace_id": "platform-approval-http",
                        "project_name": "医疗服务平台",
                        "context_profile": {
                            "business_model": "tob",
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            approval_id = blocked_response.payload["result"]["output_payload"]["pending_approval"]["approval_id"]
            list_response = service.handle(
                method="GET",
                path="/workspaces/platform-approval-http/runtime/approvals",
            )
            approve_response = service.handle(
                method="POST",
                path=f"/workspaces/platform-approval-http/runtime/approvals/{approval_id}/approve",
                body=b"",
            )

        self.assertEqual(blocked_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.payload["pending_approvals"]), 1)
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.payload["result"]["action"], "platform-project-profile-created")
        self.assertEqual(
            approve_response.payload["result"]["output_payload"]["project_profile"]["project_name"],
            "医疗服务平台",
        )
        runtime_session = approve_response.payload["result"]["runtime_session"]
        self.assertEqual(runtime_session["pending_approvals"], [])
        event_types = [item["event_type"] for item in runtime_session["event_log"]]
        self.assertIn("approval-requested", event_types)
        self.assertIn("approval-approved", event_types)
        self.assertIn("approval-override-applied", event_types)

    def test_http_service_can_reject_pending_platform_write_operation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            blocked_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "platform-project-profile-upsert",
                        "workspace_id": "platform-reject-http",
                        "project_name": "医疗服务平台",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            approval_id = blocked_response.payload["result"]["output_payload"]["pending_approval"]["approval_id"]
            reject_response = service.handle(
                method="POST",
                path=f"/workspaces/platform-reject-http/runtime/approvals/{approval_id}/reject",
                body=json.dumps({"reason": "暂不投入这项能力"}, ensure_ascii=False).encode("utf-8"),
            )

        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(reject_response.payload["result"]["action"], "approval-rejected")
        self.assertEqual(reject_response.payload["result"]["status"], "rejected")
        self.assertEqual(reject_response.payload["result"]["runtime_session"]["pending_approvals"], [])
        self.assertEqual(
            reject_response.payload["result"]["runtime_session"]["approval_ledger"][0]["status"],
            "rejected",
        )

    def test_http_service_can_return_already_approved_semantics_for_duplicate_approve(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            blocked_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "platform-project-profile-upsert",
                        "workspace_id": "platform-duplicate-http",
                        "project_name": "医疗服务平台",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            approval_id = blocked_response.payload["result"]["output_payload"]["pending_approval"]["approval_id"]
            first_approve_response = service.handle(
                method="POST",
                path=f"/workspaces/platform-duplicate-http/runtime/approvals/{approval_id}/approve",
                body=b"",
            )
            duplicate_approve_response = service.handle(
                method="POST",
                path=f"/workspaces/platform-duplicate-http/runtime/approvals/{approval_id}/approve",
                body=b"",
            )

        self.assertEqual(first_approve_response.status_code, 200)
        self.assertEqual(duplicate_approve_response.status_code, 200)
        self.assertEqual(duplicate_approve_response.payload["result"]["action"], "approval-already-approved")
        self.assertEqual(duplicate_approve_response.payload["result"]["status"], "approved")

    def test_workspace_approval_preferences_can_auto_approve_runtime_action(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            workspace_store = default_workspace_store(tmpdir)
            workspace = get_or_create_workspace("workspace-auto-approve", store=workspace_store)
            update_workspace_approval_preferences(
                workspace,
                auto_approve_actions=["project-profile-service.*"],
            )
            save_workspace(workspace, store=workspace_store)
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "platform-project-profile-upsert",
                        "workspace_id": "workspace-auto-approve",
                        "project_name": "自动批准项目背景",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["result"]["action"], "platform-project-profile-created")
        runtime_session = response.payload["result"]["runtime_session"]
        self.assertEqual(runtime_session["pending_approvals"], [])
        self.assertEqual(runtime_session["approval_ledger"][0]["status"], "approved")
        event_types = [item["event_type"] for item in runtime_session["event_log"]]
        self.assertIn("approval-auto-approved", event_types)

    def test_runtime_policy_can_auto_expire_approval_required_action(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                            "auto_expire_approval_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "platform-project-profile-upsert",
                        "workspace_id": "approval-auto-expire",
                        "project_name": "自动过期项目背景",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["result"]["action"], "approval-expired")
        self.assertEqual(response.payload["result"]["terminal_state"], "cancelled")
        runtime_session = response.payload["result"]["runtime_session"]
        self.assertEqual(runtime_session["pending_approvals"], [])
        self.assertEqual(runtime_session["approval_ledger"][0]["status"], "expired")
        event_types = [item["event_type"] for item in runtime_session["event_log"]]
        self.assertIn("approval-auto-expired", event_types)

    def test_manual_approval_only_action_cannot_be_expired(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                            "manual_approval_only_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            blocked_response = service.handle(
                method="POST",
                path="/runtime/tools/execute",
                body=json.dumps(
                    {
                        "tool_name": "platform-project-profile-upsert",
                        "workspace_id": "approval-manual-only",
                        "project_name": "必须人工处理项目背景",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            approval_id = blocked_response.payload["result"]["output_payload"]["pending_approval"]["approval_id"]
            expire_response = service.handle(
                method="POST",
                path=f"/workspaces/approval-manual-only/runtime/approvals/{approval_id}/expire",
                body=b"",
            )
            list_response = service.handle(
                method="GET",
                path="/workspaces/approval-manual-only/runtime/approvals",
            )

        self.assertEqual(expire_response.status_code, 200)
        self.assertEqual(expire_response.payload["result"]["action"], "approval-expire-not-allowed")
        self.assertEqual(expire_response.payload["result"]["status"], "pending")
        self.assertEqual(len(list_response.payload["pending_approvals"]), 1)

    def test_cli_can_reject_and_expire_pending_runtime_operation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            blocked_stdout = StringIO()
            with redirect_stdout(blocked_stdout):
                main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "platform-project-profile-upsert",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "platform-reject-cli",
                                "project_name": "诊所工作台",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
            blocked_payload = json.loads(blocked_stdout.getvalue())
            reject_approval_id = blocked_payload["output_payload"]["pending_approval"]["approval_id"]

            reject_stdout = StringIO()
            with redirect_stdout(reject_stdout):
                reject_exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "--format",
                        "json",
                        "reject",
                        "--workspace-id",
                        "platform-reject-cli",
                        "--reason",
                        "当前先不做",
                        reject_approval_id,
                    ]
                )

            blocked_stdout_2 = StringIO()
            with redirect_stdout(blocked_stdout_2):
                main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "platform-project-profile-upsert",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "platform-expire-cli",
                                "project_name": "诊所工作台",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
            blocked_payload_2 = json.loads(blocked_stdout_2.getvalue())
            expire_approval_id = blocked_payload_2["output_payload"]["pending_approval"]["approval_id"]

            expire_stdout = StringIO()
            with redirect_stdout(expire_stdout):
                expire_exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "--format",
                        "json",
                        "expire",
                        "--workspace-id",
                        "platform-expire-cli",
                        expire_approval_id,
                    ]
                )

        reject_payload = json.loads(reject_stdout.getvalue())
        expire_payload = json.loads(expire_stdout.getvalue())

        self.assertEqual(reject_exit_code, 0)
        self.assertEqual(expire_exit_code, 0)
        self.assertEqual(reject_payload["action"], "approval-rejected")
        self.assertEqual(reject_payload["status"], "rejected")
        self.assertEqual(expire_payload["action"], "approval-expired")
        self.assertEqual(expire_payload["status"], "expired")

    def test_workspace_command_can_update_approval_preferences(self) -> None:
        with TemporaryDirectory() as tmpdir:
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "--format",
                        "json",
                        "workspace",
                        "workspace-pref-cli",
                        "--approval-preferences-json",
                        json.dumps(
                            {
                                "auto_approve_actions": ["project-profile-service.*"],
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload["approval_preferences"]["auto_approve_actions"],
            ["project-profile-service.*"],
        )

    def test_http_service_can_update_workspace_approval_preferences(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            update_response = service.handle(
                method="POST",
                path="/workspaces/workspace-pref-http/approval-preferences",
                body=json.dumps(
                    {
                        "auto_approve_actions": ["project-profile-service.*"],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            get_response = service.handle(
                method="GET",
                path="/workspaces/workspace-pref-http/approval-preferences",
            )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(
            get_response.payload["approval_preferences"]["auto_approve_actions"],
            ["project-profile-service.*"],
        )

    def test_cli_can_list_and_approve_pending_runtime_operation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": ["project-profile-service.*"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            blocked_stdout = StringIO()
            with redirect_stdout(blocked_stdout):
                blocked_exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "platform-project-profile-upsert",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "platform-approval-cli",
                                "project_name": "诊所工作台",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
            blocked_payload = json.loads(blocked_stdout.getvalue())
            approval_id = blocked_payload["output_payload"]["pending_approval"]["approval_id"]

            list_stdout = StringIO()
            with redirect_stdout(list_stdout):
                list_exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "--format",
                        "json",
                        "approvals",
                        "--workspace-id",
                        "platform-approval-cli",
                    ]
                )

            approve_stdout = StringIO()
            with redirect_stdout(approve_stdout):
                approve_exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "--format",
                        "json",
                        "approve",
                        "--workspace-id",
                        "platform-approval-cli",
                        approval_id,
                    ]
                )

        list_payload = json.loads(list_stdout.getvalue())
        approve_payload = json.loads(approve_stdout.getvalue())

        self.assertEqual(blocked_exit_code, 0)
        self.assertEqual(list_exit_code, 0)
        self.assertEqual(approve_exit_code, 0)
        self.assertEqual(list_payload["pending_approvals"][0]["approval_id"], approval_id)
        self.assertEqual(approve_payload["action"], "platform-project-profile-created")
        self.assertEqual(approve_payload["runtime_session"]["pending_approvals"], [])

    def test_cli_tool_command_can_execute_local_directory_list_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "cli-list.txt").write_text("ok", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "local-directory-list",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "dir-cli",
                                "path": "notes",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["tool_name"], "local-directory-list")
        self.assertEqual(payload["action"], "directory-listed")
        self.assertEqual(payload["output_payload"]["entries"][0]["name"], "cli-list.txt")

    def test_cli_tool_command_can_execute_local_text_file_read_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "cli-read.txt").write_text("from cli read", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "local-text-file-read",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "file-cli-read",
                                "path": "notes/cli-read.txt",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["tool_name"], "local-text-file-read")
        self.assertEqual(payload["action"], "file-read")
        self.assertEqual(payload["output_payload"]["content"], "from cli read")

    def test_cli_tool_command_can_execute_local_text_search_tool(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes").mkdir(parents=True, exist_ok=True)
            (root / "notes" / "cli-search.txt").write_text("focus\nalpha\nfocus", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "tool",
                        "--format",
                        "json",
                        "--tool-name",
                        "local-text-search",
                        "--payload-json",
                        json.dumps(
                            {
                                "workspace_id": "search-cli",
                                "path": "notes",
                                "query": "focus",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["tool_name"], "local-text-search")
        self.assertEqual(payload["action"], "text-searched")
        self.assertEqual(payload["output_payload"]["match_count"], 2)

    def test_local_tool_runtime_can_execute_generic_tool_handler(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "approval_required_actions": [],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            runtime = LocalToolRuntime(base_dir=tmpdir)
            request = LocalToolRequest(
                tool_name="stub-local-tool",
                action_name="stub-local-tool.execute",
                workspace_id="stub-demo",
                summary="执行 stub 工具",
                request_payload={"value": "ok"},
                resume_from="stub-local-tool.execute",
            )
            result = runtime.execute_tool(request, handler=StubLocalToolHandler())

        self.assertTrue(result.allowed)
        self.assertEqual(result.tool_name, "stub-local-tool")
        self.assertEqual(result.action, "stub-tool-executed")
        self.assertEqual(result.output_payload["echo"], "ok")
        self.assertEqual(result.runtime_session.execution_ledger[0]["tool_name"], "stub-local-tool")

    def test_local_command_executor_can_run_allowed_command(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "command_allowlist_prefixes": [f"{sys.executable} -c"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            executor = LocalCommandExecutor(base_dir=tmpdir)
            result = executor.execute(
                command_args=[sys.executable, "-c", "print('pmma-ok')"],
                workspace_id="cmd-demo",
            )

        self.assertTrue(result.allowed)
        self.assertEqual(result.action, "command-executed")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("pmma-ok", result.stdout)
        self.assertEqual(result.runtime_session.last_terminal_event["terminal_state"], "completed")

    def test_local_command_executor_can_be_blocked_by_hook_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "blocked_command_patterns": [f"{sys.executable} *"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            executor = LocalCommandExecutor(base_dir=tmpdir)
            result = executor.execute(
                command_args=[sys.executable, "-c", "print('pmma-blocked')"],
                workspace_id="cmd-demo",
            )

        self.assertFalse(result.allowed)
        self.assertEqual(result.action, "command-blocked")
        self.assertEqual(result.terminal_state, "blocked")
        self.assertIn(sys.executable, result.reason)
        event_types = [item["event_type"] for item in result.runtime_session.event_log]
        self.assertIn("hook-call-requested", event_types)
        self.assertNotIn("tool-call-requested", event_types)

    def test_local_command_executor_can_record_failed_command(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "command_allowlist_prefixes": [f"{sys.executable} -c"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            executor = LocalCommandExecutor(base_dir=tmpdir)
            result = executor.execute(
                command_args=[sys.executable, "-c", "import sys; sys.exit(3)"],
                workspace_id="cmd-demo",
            )

        self.assertTrue(result.allowed)
        self.assertEqual(result.action, "command-failed")
        self.assertEqual(result.exit_code, 3)
        self.assertEqual(result.runtime_session.last_terminal_event["terminal_state"], "failed")

    def test_http_service_can_execute_local_command(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".pmma").mkdir(parents=True, exist_ok=True)
            (root / ".pmma" / "policy.json").write_text(
                json.dumps(
                    {
                        "runtime_policy": {
                            "command_allowlist_prefixes": [f"{sys.executable} -c"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(
                method="POST",
                path="/runtime/commands/execute",
                body=json.dumps(
                    {
                        "workspace_id": "cmd-http",
                        "command_args": [sys.executable, "-c", "print('via-http')"],
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["result"]["action"], "command-executed")
        self.assertIn("via-http", response.payload["result"]["stdout"])

    def test_http_service_can_manage_project_profile(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            create_response = service.handle(
                method="POST",
                path="/project-profiles",
                body=(
                    '{"project_name":"医疗服务平台",'
                    '"context_profile":{"business_model":"tob","primary_platform":"mobile-web"},'
                    '"stable_constraints":["上线周期紧"]}'
                ).encode("utf-8"),
            )
            profile_id = str(create_response.payload["project_profile"]["project_profile_id"])
            update_response = service.handle(
                method="POST",
                path=f"/project-profiles/{profile_id}",
                body='{"success_metrics":["到诊率"],"notes":["默认服务诊所前台场景"]}'.encode("utf-8"),
            )
            get_response = service.handle(
                method="GET",
                path=f"/project-profiles/{profile_id}",
            )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(get_response.status_code, 200)
        self.assertIn("上线周期紧", get_response.payload["project_profile"]["stable_constraints"])
        self.assertIn("到诊率", get_response.payload["project_profile"]["success_metrics"])

    def test_http_service_can_handle_agent_messages_with_workspace(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            first_response = service.handle(
                method="POST",
                path="/agent/messages",
                body='{"workspace_id":"demo","message":"前台最近老是漏提醒患者，我在想是不是要处理一下。"}'.encode(
                    "utf-8"
                ),
            )
            second_response = service.handle(
                method="POST",
                path="/workspaces/demo/messages",
                body='{"message":"这是一个 ToB 移动端产品，前台使用，管理者负责结果。"}'.encode("utf-8"),
            )
            workspace_response = service.handle(
                method="GET",
                path="/workspaces/demo",
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.payload["action"], "create-case")
        self.assertIn("case_runtime", first_response.payload)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.payload["action"], "reply-case")
        self.assertIn("case_runtime", second_response.payload)
        self.assertEqual(workspace_response.status_code, 200)
        self.assertTrue(workspace_response.payload["workspace"]["active_case_id"])

    def test_http_service_can_list_workspace_cases_and_switch_active_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            first_response = service.handle(
                method="POST",
                path="/workspaces/demo/messages",
                body='{"message":"前台最近老是漏提醒患者，我在想是不是要处理一下。"}'.encode("utf-8"),
            )
            second_response = service.handle(
                method="POST",
                path="/workspaces/demo/messages",
                body='{"message":"还有一个问题，新用户注册后发帖率也偏低，想一起看看。"}'.encode("utf-8"),
            )
            list_response = service.handle(
                method="GET",
                path="/workspaces/demo/cases",
            )
            first_case_id = str(first_response.payload["case"]["case_id"])
            switch_response = service.handle(
                method="POST",
                path="/workspaces/demo/active-case",
                body=json.dumps({"case_id": first_case_id}, ensure_ascii=False).encode("utf-8"),
            )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.payload["cases"]["recent_cases"]), 2)
        self.assertEqual(second_response.payload["workspace"]["active_case_id"], second_response.payload["case"]["case_id"])
        self.assertEqual(switch_response.status_code, 200)
        self.assertEqual(switch_response.payload["workspace"]["active_case_id"], first_case_id)
        self.assertIn(first_case_id, switch_response.payload["rendered_card"])

    def test_http_service_can_use_workspace_agent_for_project_background(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(
                method="POST",
                path="/workspaces/demo/messages",
                body='{"message":"这个项目是 ToB 医疗服务平台，主要跑在移动端。"}'.encode("utf-8"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["action"], "project-profile-updated")
        self.assertIsNotNone(response.payload["project_profile"])

    def test_agent_shell_can_create_case_from_rough_idea(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )

        self.assertEqual(response.action, "create-case")
        self.assertTrue(response.workspace.active_case_id)
        self.assertIn("PM Method Agent", response.rendered_card)

    def test_agent_shell_can_continue_active_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )
            second_response = shell.handle_message(
                "这是一个 ToB 移动端产品，前台使用，管理者负责结果。",
                workspace_id="demo",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(second_response.action, "reply-case")
        self.assertEqual(first_response.workspace.active_case_id, second_response.workspace.active_case_id)
        self.assertIn("## 我现在的判断", second_response.rendered_card)

    def test_agent_shell_prefers_continuing_active_case_for_follow_up_message(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。",
                workspace_id="demo",
            )
            shell.handle_message(
                "当前这个项目属于 ToB 的 HIS 产品，主要使用网页端，但也提供 App，诊所前台提出需求，店长对结果负责。",
                workspace_id="demo",
            )
            follow_up_response = shell.handle_message(
                "我暂时没有想好是否值得投入产品能力，但研发资源比较紧张，这个更像是一个 nice to have 的能力。",
                workspace_id="demo",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(follow_up_response.action, "reply-case")
        self.assertEqual(first_response.workspace.active_case_id, follow_up_response.workspace.active_case_id)
        self.assertIn("先把这个点定下来", follow_up_response.rendered_card)

    def test_agent_shell_keeps_short_metric_reply_on_active_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。",
                workspace_id="metric-follow-up",
            )
            second_response = shell.handle_message(
                "当前首帖率大概只有 6%，如果能拉到 10% 就算有效；如果两周内没有明显改善，我们就先停。",
                workspace_id="metric-follow-up",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(second_response.action, "reply-case")
        self.assertEqual(first_response.workspace.active_case_id, second_response.workspace.active_case_id)
        self.assertTrue(second_response.case_state.metadata.get("answered_questions"))

    def test_web_demo_javascript_keeps_follow_up_focus_and_memory_cues(self) -> None:
        asset = get_web_demo_asset("/assets/web-demo.js")

        self.assertIsNotNone(asset)
        content_type, body = asset
        script = body.decode("utf-8")

        self.assertIn("function buildComposerPlaceholder()", script)
        self.assertIn("这轮先收：", script)
        self.assertIn("这轮现在先收什么", script)
        self.assertIn("最近补充", script)
        self.assertIn("当前焦点", script)
        self.assertEqual(content_type, "application/javascript; charset=utf-8")

    def test_session_service_can_infer_defer_from_soft_gate_expression(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="我觉得这个需求可以不用现在做，研发资源比较紧张，更像是一个 nice to have。",
                store=store,
            )

        self.assertEqual(replied_case.output_kind, "stage-block-card")
        self.assertEqual(replied_case.metadata["last_gate_choice"], "defer")
        self.assertEqual(replied_case.workflow_state, "deferred")

    def test_session_service_can_infer_defer_from_validation_before_commit_expression(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="先做点轻验证，但先不立项。",
                store=store,
            )

        self.assertEqual(replied_case.output_kind, "stage-block-card")
        self.assertEqual(replied_case.metadata["last_gate_choice"], "defer")
        self.assertEqual(replied_case.workflow_state, "deferred")

    def test_session_service_can_infer_defer_from_design_before_launch_expression(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="设计可以先看，上线先别急。",
                store=store,
            )

        self.assertEqual(replied_case.metadata["last_gate_choice"], "defer")
        self.assertEqual(replied_case.workflow_state, "deferred")

    def test_session_service_can_infer_defer_from_observe_then_decide_expression(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="先观察两周，再决定要不要做产品。",
                store=store,
            )

        self.assertEqual(replied_case.metadata["last_gate_choice"], "defer")
        self.assertEqual(replied_case.workflow_state, "deferred")

    def test_session_service_can_infer_try_non_product_from_process_constraint_expression(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="我们需要优化权限配置流程，避免前台误操作。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "pc",
                    "target_user_roles": ["前台", "管理员"],
                },
                store=store,
            )
            replied_case = reply_to_case(
                case_id=case_state.case_id,
                reply_text="先看流程约束能不能解决，再决定要不要做产品。",
                store=store,
            )

        self.assertEqual(replied_case.metadata["last_gate_choice"], "try-non-product-first")
        self.assertEqual(replied_case.workflow_state, "blocked")

    def test_agent_shell_can_update_project_profile(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "这个项目是 ToB 医疗服务平台，主要跑在移动端，前台和诊所管理者都很关键。",
                workspace_id="demo",
            )

        self.assertEqual(response.action, "project-profile-updated")
        self.assertIsNotNone(response.project_profile)
        self.assertEqual(response.workspace.active_project_profile_id, response.project_profile.project_profile_id)
        self.assertEqual(response.project_profile.context_profile["business_model"], "tob")
        self.assertEqual(response.rendered_card, "")

    def test_agent_shell_project_background_can_backfill_active_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。",
                workspace_id="demo",
            )
            second_response = shell.handle_message(
                "当前这个项目属于 ToB 的 HIS 产品，主要使用网页端，但也提供小程序，诊所前台提出需求，店长对结果负责。",
                workspace_id="demo",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(second_response.action, "project-profile-updated")
        self.assertIsNotNone(second_response.case_state)
        self.assertEqual(second_response.case_state.context_profile["business_model"], "tob")
        self.assertEqual(second_response.case_state.context_profile["primary_platform"], "multi-platform")
        self.assertIn("店长", second_response.case_state.context_profile["target_user_roles"])
        self.assertIn("继续往下看", second_response.rendered_card)
        self.assertIn("提出者：前台", second_response.rendered_card)
        self.assertIn("结果责任人：店长", second_response.rendered_card)
        self.assertNotIn("当前产品属于企业产品、消费者产品还是内部产品？", second_response.case_state.pending_questions)
        self.assertNotIn("当前主要使用平台是桌面端、移动端、小程序还是多端？", second_response.case_state.pending_questions)

    def test_agent_shell_can_show_guidance_for_active_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )
            response = shell.handle_message(
                "我现在下一步该做什么？",
                workspace_id="demo",
            )

        self.assertEqual(response.action, "show-guidance")
        self.assertIn("PM Method Agent", response.rendered_card)

    def test_agent_shell_can_start_new_case_even_with_active_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )
            second_response = shell.handle_message(
                "还有一个问题，新用户注册后发帖率也偏低，想一起看看。",
                workspace_id="demo",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(second_response.action, "create-case")
        self.assertNotEqual(first_response.case_state.case_id, second_response.case_state.case_id)
        self.assertEqual(second_response.workspace.active_case_id, second_response.case_state.case_id)

    def test_agent_shell_can_treat_meta_question_as_guidance(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )
            response = shell.handle_message(
                "如果这是 ToC，会有什么不同？",
                workspace_id="demo",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(response.action, "show-guidance")
        self.assertEqual(first_response.workspace.active_case_id, response.workspace.active_case_id)

    def test_agent_shell_can_show_workspace_overview(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )
            shell.handle_message(
                "还有一个问题，新用户注册后发帖率也偏低，想一起看看。",
                workspace_id="demo",
            )
            response = shell.handle_message(
                "看看最近几个案例。",
                workspace_id="demo",
            )

        self.assertEqual(response.action, "show-workspace")
        self.assertIn("## 最近案例", response.rendered_card)
        self.assertIn("当前", response.rendered_card)

    def test_agent_shell_can_switch_to_previous_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )
            second_response = shell.handle_message(
                "还有一个问题，新用户注册后发帖率也偏低，想一起看看。",
                workspace_id="demo",
            )
            response = shell.handle_message(
                "切到上一个案例。",
                workspace_id="demo",
            )

        self.assertEqual(second_response.action, "create-case")
        self.assertEqual(response.action, "switch-case")
        self.assertEqual(response.workspace.active_case_id, first_response.case_state.case_id)
        self.assertIn(first_response.case_state.case_id, response.rendered_card)

    def test_agent_shell_can_replace_project_profile_roles_on_explicit_correction(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "这个项目是 ToB 医疗服务平台，前台和诊所管理者都很关键。",
                workspace_id="demo",
            )
            response = shell.handle_message(
                "更准确说，这个项目核心不是前台，是医生和护士。",
                workspace_id="demo",
            )

        self.assertEqual(first_response.action, "project-profile-updated")
        self.assertEqual(response.action, "project-profile-updated")
        assert response.project_profile is not None
        self.assertEqual(response.project_profile.context_profile["target_user_roles"], ["医生", "护士"])

    def test_agent_shell_persists_runtime_session_with_event_log(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )
            runtime_session = get_or_create_runtime_session(
                "demo",
                store=default_runtime_session_store(tmpdir),
            )

        self.assertEqual(response.runtime_session.workspace_id, "demo")
        self.assertEqual(response.runtime_session.turn_count, 1)
        self.assertEqual(runtime_session.turn_count, 1)
        self.assertGreaterEqual(len(runtime_session.event_log), 5)
        event_types = [item["event_type"] for item in runtime_session.event_log]
        self.assertEqual(event_types[:2], ["turn-received", "loop-started"])
        self.assertIn("tool-call-requested", event_types)
        self.assertIn("tool-call-completed", event_types)
        self.assertIn("turn-classified", event_types)
        self.assertIn("loop-state-changed", event_types)
        self.assertEqual(runtime_session.last_terminal_event["query_id"], "query-0001")
        self.assertGreaterEqual(len(runtime_session.execution_ledger), 2)
        self.assertEqual(runtime_session.execution_ledger[0]["tool_name"], "reply-interpreter")
        self.assertEqual(runtime_session.execution_ledger[0]["status"], "completed")
        self.assertEqual(runtime_session.runtime_metadata["last_loop_handler"], "_handle_create_case")

    def test_agent_shell_runtime_session_tracks_execution_ledger(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "看看最近几个案例。",
                workspace_id="demo",
            )

        ledger = response.runtime_session.execution_ledger
        self.assertGreaterEqual(len(ledger), 2)
        self.assertEqual(ledger[0]["tool_name"], "reply-interpreter")
        self.assertEqual(ledger[0]["status"], "completed")
        self.assertTrue(ledger[0]["result_ref"].startswith("parser:"))
        self.assertEqual(ledger[1]["tool_name"], "workspace-service")
        self.assertEqual(ledger[1]["status"], "completed")

    def test_runtime_session_closes_pending_tool_calls_on_next_query(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_store = default_runtime_session_store(tmpdir)
            runtime_session = get_or_create_runtime_session("demo", store=runtime_store)
            runtime_session.current_query_id = "query-0009"
            pending_entry = request_tool_call(
                runtime_session,
                tool_name="demo-tool",
                request_payload={"note": "pending"},
            )
            save_runtime_session(runtime_session, store=runtime_store)

            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo",
            )

        self.assertEqual(response.runtime_session.pending_tool_calls, [])
        first_entry = response.runtime_session.execution_ledger[0]
        self.assertEqual(first_entry["call_id"], pending_entry["call_id"])
        self.assertEqual(first_entry["status"], "failed")
        self.assertEqual(first_entry["error"]["reason"], "next-query-started")

    def test_runtime_session_can_mark_failed_interrupted_and_cancelled_terminal_states(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_session = get_or_create_runtime_session(
                "demo-runtime-semantics",
                store=default_runtime_session_store(tmpdir),
            )
            start_runtime_query(runtime_session, message="测试失败路径")
            fail_runtime_query(
                runtime_session,
                action="runtime-error",
                resume_from="decision-challenge",
                error={"type": "RuntimeError", "message": "boom"},
            )
            self.assertEqual(runtime_session.runtime_status, "failed")
            self.assertEqual(runtime_session.last_terminal_event["terminal_state"], "failed")
            self.assertEqual(runtime_session.last_terminal_event["resume_from"], "decision-challenge")

            start_runtime_query(runtime_session, message="测试中断路径")
            interrupt_runtime_query(
                runtime_session,
                action="user-interrupt",
                resume_from="validation-design",
                reason={"reason": "manual-stop"},
            )
            self.assertEqual(runtime_session.runtime_status, "interrupted")
            self.assertEqual(runtime_session.last_terminal_event["terminal_state"], "interrupted")
            self.assertEqual(runtime_session.last_terminal_event["error"]["reason"], "manual-stop")

            start_runtime_query(runtime_session, message="测试取消路径")
            cancel_runtime_query(
                runtime_session,
                action="user-cancel",
                resume_from="problem-definition",
                reason={"reason": "cancelled-by-user"},
            )
            self.assertEqual(runtime_session.runtime_status, "cancelled")
            self.assertEqual(runtime_session.last_terminal_event["terminal_state"], "cancelled")
            self.assertEqual(runtime_session.last_terminal_event["error"]["reason"], "cancelled-by-user")

    def test_runtime_session_can_compress_old_query_history_into_summary_memory(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_session = get_or_create_runtime_session(
                "demo-runtime-compression",
                store=default_runtime_session_store(tmpdir),
            )
            runtime_session.context_budget["raw_history_budget"] = 2
            runtime_session.context_budget["working_memory_budget"] = 1
            runtime_session.context_budget["summary_memory_budget"] = 2

            for index in range(3):
                start_runtime_query(runtime_session, message=f"第 {index + 1} 轮输入")
                complete_runtime_query(
                    runtime_session,
                    terminal_state="completed",
                    action="show-guidance",
                    active_case_id=f"case-{index + 1}",
                    resume_from="decision-challenge",
                    output_kind="continue-guidance-card",
                    workflow_state="blocked",
                )

        self.assertEqual(len(runtime_session.raw_history), 2)
        self.assertEqual(len(runtime_session.working_memory), 1)
        self.assertEqual(len(runtime_session.summary_memory), 1)
        self.assertEqual(runtime_session.summary_memory[0]["from_turn"], 1)
        self.assertEqual(runtime_session.summary_memory[0]["to_turn"], 1)
        self.assertEqual(runtime_session.compression_state["status"], "compressed")
        self.assertEqual(runtime_session.compression_state["compressed_turns"], 1)
        self.assertEqual(runtime_session.compression_state["last_compression_turn"], 1)
        self.assertTrue(
            any(item["event_type"] == "context-compressed" for item in runtime_session.event_log)
        )
        rendered = render_runtime_session(runtime_session)
        self.assertIn("摘要记忆", rendered)
        self.assertIn("summary-0001", rendered)

    def test_agent_shell_runtime_session_tracks_terminal_state_and_resume_point(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "这是一个 ToB 的 PC 后台，前台和管理员在用。我们需要优化权限配置流程，避免前台误操作。",
                workspace_id="demo",
            )
            second_response = shell.handle_message(
                "我觉得这个需求可以不用现在做，研发资源比较紧张，更像是一个 nice to have。",
                workspace_id="demo",
            )

        self.assertEqual(first_response.runtime_session.last_terminal_event["terminal_state"], "blocked")
        self.assertEqual(first_response.runtime_session.last_terminal_event["resume_from"], "decision-challenge")
        self.assertEqual(second_response.case_state.workflow_state, "deferred")
        self.assertEqual(second_response.runtime_session.last_terminal_event["terminal_state"], "deferred")
        self.assertEqual(second_response.runtime_session.last_terminal_event["resume_from"], "decision-challenge")

    def test_agent_shell_persists_failed_terminal_state_when_runtime_crashes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            shell._reply_interpreter = RaisingReplyInterpreter()
            with self.assertRaises(RuntimeError):
                shell.handle_message(
                    "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                    workspace_id="demo",
                )
            runtime_session = get_or_create_runtime_session(
                "demo",
                store=default_runtime_session_store(tmpdir),
            )

        self.assertEqual(runtime_session.runtime_status, "failed")
        self.assertEqual(runtime_session.last_terminal_event["terminal_state"], "failed")
        self.assertEqual(runtime_session.last_terminal_event["action"], "runtime-error")
        self.assertEqual(runtime_session.last_terminal_event["error"]["type"], "RuntimeError")

    def test_agent_shell_records_llm_fallback_without_failing_runtime(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            shell._reply_interpreter = HybridReplyInterpreter(
                llm_interpreter=LLMReplyInterpreter(adapter=RaisingLLMAdapter(RuntimeError("network-down"))),
                fallback=HeuristicReplyInterpreter(),
            )
            response = shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo-fallback",
            )
            runtime_session = get_or_create_runtime_session(
                "demo-fallback",
                store=default_runtime_session_store(tmpdir),
            )

        self.assertNotEqual(response.runtime_session.last_terminal_event["action"], "runtime-error")
        self.assertEqual(runtime_session.runtime_status, "idle")
        self.assertTrue(
            any(
                item["event_type"] == "llm-fallback"
                and item["payload"].get("component") == "reply-interpreter"
                and item["payload"].get("fallback_parser") == "heuristic"
                for item in runtime_session.event_log
            )
        )

    def test_agent_shell_can_record_case_level_llm_fallback_events(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            runtime_session = get_or_create_runtime_session(
                "demo-case-fallback",
                store=default_runtime_session_store(tmpdir),
            )
            start_runtime_query(runtime_session, message="测试 case 级降级")
            case_state = CaseState(
                case_id="case-demo",
                stage="pre-framing",
                raw_input="想增加一个新手引导浮层，提升新用户发帖率。",
                metadata={
                    "llm_enhancements": {
                        "pre-framing": {
                            "engine": "llm-fallback",
                            "fallback_used": True,
                            "fallback_reason": "RuntimeError: gateway-timeout",
                        },
                        "copywriter": {
                            "engine": "llm-fallback",
                            "fallback_used": True,
                            "fallback_reason": "RuntimeError: llm-offline",
                        },
                    }
                },
            )

            shell._record_case_fallbacks(runtime_session, case_state, action="create-case")

        event_payloads = [
            item["payload"]
            for item in runtime_session.event_log
            if item["event_type"] == "llm-fallback"
        ]
        self.assertTrue(any(item.get("component") == "pre-framing" for item in event_payloads))
        self.assertTrue(any(item.get("component") == "copywriter" for item in event_payloads))

    def test_cli_runtime_command_can_render_runtime_session(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            shell.handle_message(
                "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                workspace_id="demo-runtime-cli",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "runtime",
                        "--workspace-id",
                        "demo-runtime-cli",
                    ]
                )

        self.assertEqual(exit_code, 0)
        rendered = stdout.getvalue()
        self.assertIn("PM Method Agent Runtime Session", rendered)
        self.assertIn("工作记忆", rendered)

    def test_http_service_can_return_runtime_session_payload(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            shell.handle_message(
                "想增加一个新手引导浮层，提升新用户发帖率。",
                workspace_id="demo-runtime-http",
            )
            service = PMMethodHTTPService(store_dir=tmpdir)

            response = service.handle("GET", "/workspaces/demo-runtime-http/runtime/session")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.encoded_body().decode("utf-8"))
        runtime_session = payload["runtime_session"]
        self.assertEqual(runtime_session["workspace_id"], "demo-runtime-http")
        self.assertIn("raw_history", runtime_session)
        self.assertIn("working_memory", runtime_session)
        self.assertIn("summary_memory", runtime_session)

    def test_openai_compatible_adapter_uses_base_url_and_api_key(self) -> None:
        transport = StubTransport(
            response_text=(
                '{"model":"deepseek-chat","choices":[{"message":{"content":"{\\"ok\\": true}"}}]}'
            )
        )
        adapter = OpenAICompatibleAdapter(
            config=OpenAICompatibleConfig(
                base_url="https://api.deepseek.com",
                api_key="demo-key",
                model="deepseek-chat",
                provider_name="deepseek",
            ),
            transport=transport,
        )
        response = adapter.generate(
            LLMRequest(
                messages=[
                    LLMMessage(role="system", content="请输出 JSON。"),
                    LLMMessage(role="user", content="测试"),
                ]
            )
        )

        self.assertEqual(response.provider, "deepseek")
        self.assertEqual(response.model, "deepseek-chat")
        self.assertEqual(response.content, '{"ok": true}')
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(transport.calls[0]["headers"]["Authorization"], "Bearer demo-key")
        self.assertIn('"model": "deepseek-chat"', transport.calls[0]["body"])

    def test_build_reply_interpreter_from_env_can_enable_openai_compatible_mode(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PMMA_LLM_ENABLED": "1",
                "PMMA_LLM_BASE_URL": "https://api.deepseek.com",
                "PMMA_LLM_API_KEY": "demo-key",
                "PMMA_LLM_MODEL": "deepseek-chat",
                "PMMA_LLM_PROVIDER": "deepseek",
            },
            clear=False,
        ):
            interpreter = build_reply_interpreter_from_env()

        self.assertIsInstance(interpreter, HybridReplyInterpreter)

    def test_build_reply_interpreter_from_env_falls_back_when_config_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PMMA_LLM_ENABLED": "1",
                "PMMA_LLM_BASE_URL": "",
                "PMMA_LLM_API_KEY": "",
                "PMMA_LLM_MODEL": "",
            },
            clear=False,
        ):
            interpreter = build_reply_interpreter_from_env()

        self.assertIsInstance(interpreter, HeuristicReplyInterpreter)

    def test_module_entrypoint_can_render_help(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        result = subprocess.run(
            [sys.executable, "-m", "pm_method_agent", "--help"],
            cwd=".",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("pm-method-agent", result.stdout)

    def test_cli_direct_json_output_can_include_case_runtime(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "--format",
                    "json",
                    "--business-model",
                    "tob",
                    "--primary-platform",
                    "mobile-web",
                    "--target-user-role",
                    "前台",
                    "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertIn("case", payload)
        self.assertIn("case_runtime", payload)
        self.assertIn("rendered_card", payload)
        self.assertIn("summary", payload["case_runtime"])

    def test_cli_history_json_output_can_include_case_runtime_and_rendered_history(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
                context_profile={
                    "business_model": "tob",
                    "primary_platform": "mobile-web",
                    "target_user_roles": ["前台", "诊所管理者"],
                },
                store=store,
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "--format",
                        "json",
                        "history",
                        case_state.case_id,
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertIn("history", payload)
        self.assertIn("case_runtime", payload)
        self.assertIn("rendered_history", payload)
        self.assertEqual(payload["history"]["case_id"], case_state.case_id)

    def test_cli_agent_json_output_can_include_case_runtime(self) -> None:
        with TemporaryDirectory() as tmpdir:
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store-dir",
                        tmpdir,
                        "--format",
                        "json",
                        "agent",
                        "--workspace-id",
                        "demo-cli-json",
                        "前台最近老是漏提醒患者，我在想是不是要处理一下。",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertIn("action", payload)
        self.assertIn("case", payload)
        self.assertIn("case_runtime", payload)
        self.assertIn("rendered_card", payload)


if __name__ == "__main__":
    unittest.main()
