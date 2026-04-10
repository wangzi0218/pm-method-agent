import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("PMMA_DISABLE_ENV_AUTOLOAD", "1")

from pm_method_agent.agent_shell import PMMethodAgentShell
from pm_method_agent.case_copywriter import LLMCaseCopywriter, apply_case_copywriting, build_case_copywriter_from_env
from pm_method_agent.cli import main
from pm_method_agent.command_executor import LocalCommandExecutor
from pm_method_agent.hook_enforcement import HookExecutionBlockedError, run_pre_operation_hooks
from pm_method_agent.http_service import PMMethodHTTPService
from pm_method_agent.llm_adapter import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
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
    cancel_runtime_query,
    close_incomplete_hooks,
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
from pm_method_agent.renderers import render_case_history, render_case_state
from pm_method_agent.runtime_config import ensure_local_env_loaded, get_llm_runtime_status
from pm_method_agent.runtime_policy import (
    check_runtime_action_policy,
    check_runtime_command_policy,
    check_runtime_write_policy,
    load_runtime_policy,
)
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case
from pm_method_agent.text_file_tool import LocalTextFileWriter
from pm_method_agent.tool_runtime import (
    LocalToolExecutionOutcome,
    LocalToolHandler,
    LocalToolRequest,
    LocalToolRuntime,
)


class StubLLMAdapter:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content=self.content, provider="stub", model="stub-model")


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
        self.assertIn("## 关键判断", rendered)
        self.assertIn("## 建议先做", rendered)
        self.assertIn("### 场景信息", rendered)
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

        self.assertIn("## 更像哪几类问题", rendered)
        self.assertIn("## 先确认这几件事", rendered)
        self.assertIn("## 更建议先沿哪条继续", rendered)

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
        self.assertIn("当前产品属于企业产品、消费者产品还是内部产品？", answered_questions)
        self.assertIn("当前主要使用平台是桌面端、移动端、小程序还是多端？", answered_questions)
        self.assertNotIn("谁提出需求、谁使用产品、谁承担最终结果？", answered_questions)
        self.assertEqual(replied_case.context_profile["primary_platform"], "pc")

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

        self.assertIn("## 会话回合", rendered)
        self.assertIn("## 已回答问题", rendered)
        self.assertIn("最近恢复阶段", rendered)

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
        self.assertIn("提醒链路本身不稳定", [item.label for item in result.candidate_directions])
        self.assertEqual(len(adapter.requests), 1)
        system_prompt = adapter.requests[0].messages[0].content
        self.assertIn("[身份描述]", system_prompt)
        self.assertIn("[行为规则]", system_prompt)
        self.assertIn("[工具约束]", system_prompt)
        self.assertIn("[输出纪律]", system_prompt)
        self.assertIn("[任务目标]", system_prompt)
        self.assertIn("prompt_layers", adapter.requests[0].metadata)

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
        system_prompt = adapter.requests[0].messages[0].content
        self.assertIn("[角色职责]", system_prompt)
        self.assertIn("[追加要求]", system_prompt)
        self.assertIn("prompt_layers", adapter.requests[0].metadata)

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
                            "command_allowlist_prefixes": ["git status", "python -m unittest"],
                            "blocked_command_patterns": ["rm *"],
                            "approval_required_command_patterns": ["git push*"],
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
        self.assertEqual(policy.command_allowlist_prefixes, ["git status", "python -m unittest"])
        self.assertEqual(policy.blocked_command_patterns, ["rm *"])
        self.assertEqual(policy.approval_required_command_patterns, ["git push*"])
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
            write_paths=["src/pm_method_agent/runtime_policy.py"],
        )
        blocked = evaluate_operation_enforcement(
            policy,
            action_name="project-profile-service.update-or-create",
            command_args=["git", "status"],
        )

        self.assertTrue(allowed.allowed)
        self.assertEqual([item.decision for item in allowed.checks], ["allowed", "allowed", "allowed"])
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
        self.assertIn("history", history_response.payload)
        self.assertIn("rendered_history", history_response.payload)
        self.assertEqual(history_response.payload["case_id"], case_id)

    def test_http_service_returns_not_found_for_missing_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = PMMethodHTTPService(store_dir=tmpdir)
            response = service.handle(method="GET", path="/cases/case-missing")

        self.assertEqual(response.status_code, 404)

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
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.payload["action"], "reply-case")
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
        self.assertIn("执行模块", second_response.rendered_card)

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
        self.assertIn("决策关口卡", follow_up_response.rendered_card)

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
        self.assertIn("继续卡", second_response.rendered_card)
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
        self.assertEqual(runtime_session.last_terminal_event["query_id"], "query-0001")
        self.assertGreaterEqual(len(runtime_session.execution_ledger), 2)
        self.assertEqual(runtime_session.execution_ledger[0]["tool_name"], "reply-interpreter")
        self.assertEqual(runtime_session.execution_ledger[0]["status"], "completed")

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


if __name__ == "__main__":
    unittest.main()
