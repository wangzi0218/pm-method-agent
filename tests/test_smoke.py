import unittest
from tempfile import TemporaryDirectory

from pm_method_agent.orchestrator import run_analysis
from pm_method_agent.renderers import render_case_state
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case


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
        validation_claims = [
            finding.claim for finding in replied_case.findings if finding.dimension == "validation-design"
        ]
        self.assertTrue(validation_claims)
        self.assertNotIn("补充信息", validation_claims[0])


if __name__ == "__main__":
    unittest.main()
