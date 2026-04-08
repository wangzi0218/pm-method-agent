import os
import subprocess
import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pm_method_agent.http_service import PMMethodHTTPService
from pm_method_agent.llm_adapter import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from pm_method_agent.orchestrator import continue_analysis_with_context, run_analysis
from pm_method_agent.reply_interpreter import (
    HeuristicReplyInterpreter,
    LLMReplyInterpreter,
    build_reply_interpreter_from_env,
)
from pm_method_agent.renderers import render_case_history, render_case_state
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case


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


class OrchestratorSmokeTest(unittest.TestCase):
    def test_auto_mode_requests_context_when_context_is_missing(self) -> None:
        case_state = run_analysis("前台希望增加一个预约前提醒弹窗，避免漏提醒患者。")
        self.assertEqual(case_state.stage, "context-alignment")
        self.assertEqual(case_state.workflow_state, "blocked")
        self.assertEqual(case_state.output_kind, "context-question-card")
        self.assertGreaterEqual(len(case_state.pending_questions), 2)

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
        self.assertIn("## 先做这几步", rendered)
        self.assertIn("### 场景信息", rendered)
        self.assertIn("### 决策与验证", rendered)

    def test_session_service_can_create_and_load_case(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            case_state = create_case(
                raw_input="前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
                store=store,
            )
            loaded_case = get_case(case_state.case_id, store=store)

        self.assertEqual(loaded_case.case_id, case_state.case_id)
        self.assertEqual(loaded_case.output_kind, "context-question-card")
        self.assertEqual(
            loaded_case.metadata["session_original_input"],
            "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
        )

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
        validation_claims = [
            finding.claim for finding in replied_case.findings if finding.dimension == "validation-design"
        ]
        self.assertTrue(validation_claims)
        self.assertNotIn("补充场景信息", validation_claims[0])

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

        self.assertIsInstance(interpreter, LLMReplyInterpreter)

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
