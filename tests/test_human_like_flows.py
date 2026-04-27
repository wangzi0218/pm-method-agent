import os
import unittest
from tempfile import TemporaryDirectory

os.environ.setdefault("PMMA_DISABLE_ENV_AUTOLOAD", "1")

from pm_method_agent.agent_shell import PMMethodAgentShell
from pm_method_agent.reply_interpreter import LLMReplyInterpreter
from pm_method_agent.session_service import create_case, default_store, reply_to_case
from tests.test_smoke import StubLLMAdapter


class HumanLikeFlowTest(unittest.TestCase):
    def test_junior_pm_vague_tob_flow_can_move_from_pre_framing_to_decision_gate(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "最近诊所前台老说这里总会漏提醒，我在想是不是该处理一下。",
                workspace_id="junior-pm-flow",
            )
            second_response = shell.handle_message(
                "补充一下，这是一个 ToB 的 HIS 产品，主要通过网页端使用，诊所前台提出来的，前台自己在操作，店长对结果负责。",
                workspace_id="junior-pm-flow",
            )
            third_response = shell.handle_message(
                "现在主要靠前台手工翻列表提醒，研发资源比较紧张，我更倾向先看看流程约束能不能解决。",
                workspace_id="junior-pm-flow",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(first_response.case_state.output_kind, "continue-guidance-card")
        self.assertEqual(first_response.case_state.stage, "pre-framing")
        self.assertIn("我先按这几个方向理解", first_response.rendered_card)

        self.assertEqual(second_response.action, "reply-case")
        self.assertEqual(second_response.case_state.output_kind, "review-card")
        self.assertEqual(second_response.case_state.workflow_state, "done")
        self.assertIn("## 我主要看到这几个点", second_response.rendered_card)
        self.assertIn("## 如果继续往下聊，优先补这几项", second_response.rendered_card)

        self.assertEqual(third_response.action, "reply-case")
        self.assertEqual(third_response.case_state.output_kind, "decision-gate-card")
        self.assertEqual(third_response.case_state.workflow_state, "blocked")
        self.assertIn("倾向：暂缓", third_response.rendered_card)

    def test_mid_level_pm_toc_growth_case_can_go_directly_to_review_card(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。",
                workspace_id="mid-pm-flow",
            )

        self.assertEqual(response.action, "create-case")
        self.assertIsNotNone(response.case_state)
        self.assertEqual(response.case_state.output_kind, "review-card")
        self.assertEqual(response.case_state.workflow_state, "done")
        self.assertIn("## 后面还可以继续补", response.rendered_card)
        self.assertIn("成功指标是什么", response.rendered_card)
        self.assertNotIn("输入里已经带出方案", response.rendered_card)

    def test_stage_conclusion_over_ask_sample_can_land_on_review_card(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "这是一个内容社区 App。最近新用户注册后 3 天内发帖率还是起不来，"
                "运营怀疑不是没人想发，而是不知道第一条该发什么。"
                "我手上还没有特别细的数据，但这个方向我觉得已经挺明显了。",
                workspace_id="stage-conclusion-over-ask",
            )

        self.assertEqual(response.action, "create-case")
        self.assertIsNotNone(response.case_state)
        self.assertEqual(response.case_state.output_kind, "review-card")
        self.assertEqual(response.case_state.workflow_state, "done")
        self.assertIn("## 我现在的判断", response.rendered_card)
        self.assertIn("## 如果继续往下聊，优先补这几项", response.rendered_card)
        self.assertNotIn("我先按这几个方向理解", response.rendered_card)

    def test_senior_pm_process_flow_can_resume_after_non_product_trial(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "这是一个 ToB 审批系统，主要在 PC 端使用。审批专员在日常操作里经常遇到跨部门审批漏人，部门负责人对 SLA 结果负责，我现在还没决定是不是要做产品。",
                workspace_id="senior-pm-flow",
            )
            second_response = shell.handle_message(
                "我们可以先试流程约束和培训，本月不急着上线。",
                workspace_id="senior-pm-flow",
            )
            third_response = shell.handle_message(
                "已经试过两周流程提醒，但效果回落，还是继续产品化。",
                workspace_id="senior-pm-flow",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(first_response.case_state.output_kind, "continue-guidance-card")
        self.assertIn("如果先按这个方向继续", first_response.rendered_card)

        self.assertEqual(second_response.action, "reply-case")
        self.assertEqual(second_response.case_state.output_kind, "decision-gate-card")
        self.assertEqual(second_response.case_state.workflow_state, "blocked")
        self.assertIn("优先评估非产品路径", second_response.rendered_card)

        self.assertEqual(third_response.action, "reply-case")
        self.assertEqual(third_response.case_state.output_kind, "review-card")
        self.assertEqual(third_response.case_state.workflow_state, "done")
        self.assertIn("验证设计", third_response.rendered_card)

    def test_stage_conclusion_missed_gate_sample_can_turn_into_decision_gate(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "这是一个 ToB 门店工作台，主要在网页端使用。前台在提一个提醒相关需求，但我还没判断要不要投入产品能力。",
                workspace_id="stage-conclusion-missed-gate",
            )
            follow_up_response = shell.handle_message(
                "这个需求我不是完全不想做，但现在研发资源就是很紧。"
                "它更像一个 nice to have，我也没想好现在值不值得为它投入产品能力。",
                workspace_id="stage-conclusion-missed-gate",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(follow_up_response.action, "reply-case")
        self.assertEqual(follow_up_response.case_state.output_kind, "decision-gate-card")
        self.assertEqual(follow_up_response.case_state.workflow_state, "blocked")
        self.assertIn("这件事要不要继续往产品方案走", follow_up_response.rendered_card)
        self.assertIn("倾向：暂缓", follow_up_response.rendered_card)

    def test_stage_conclusion_defer_sample_can_turn_into_deferred_block(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "这是一个 ToB 的 PC 后台，前台和管理员在用。我们需要优化权限配置流程，避免前台误操作。",
                workspace_id="stage-conclusion-defer",
            )
            follow_up_response = shell.handle_message(
                "我觉得这个需求可以不用现在做，研发资源比较紧张，更像是一个 nice to have。",
                workspace_id="stage-conclusion-defer",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(follow_up_response.action, "reply-case")
        self.assertEqual(follow_up_response.case_state.output_kind, "stage-block-card")
        self.assertEqual(follow_up_response.case_state.workflow_state, "deferred")
        self.assertIn("这轮先记为暂缓", follow_up_response.rendered_card)
        self.assertIn("如果后面条件变了，再接着往下看", follow_up_response.rendered_card)

    def test_colloquial_b_side_mobile_web_flow_can_be_understood(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "我们这边偏 B 端，门店店员最近老反馈 H5 上核销这步容易漏，我感觉该看看。",
                workspace_id="colloquial-b-side",
            )
            second_response = shell.handle_message(
                "这事其实是一线店员在用，店长盯结果，老板也开始关注了。",
                workspace_id="colloquial-b-side",
            )

        self.assertEqual(first_response.action, "create-case")
        self.assertEqual(first_response.case_state.output_kind, "continue-guidance-card")
        self.assertIn("店员", first_response.case_state.context_profile["target_user_roles"])
        self.assertEqual(first_response.case_state.context_profile["business_model"], "tob")
        self.assertEqual(first_response.case_state.context_profile["primary_platform"], "mobile-web")

        self.assertEqual(second_response.action, "reply-case")
        self.assertIn(second_response.case_state.output_kind, {"review-card", "decision-gate-card"})
        self.assertIn("店长", second_response.rendered_card)

    def test_colloquial_process_efficiency_issue_can_trigger_process_pre_framing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            response = shell.handle_message(
                "最近门店店员老反馈 H5 上核销后还要回头查订单，我感觉这事有点影响效率，但还没想清楚是不是要做。",
                workspace_id="process-efficiency-flow",
            )

        self.assertEqual(response.case_state.output_kind, "continue-guidance-card")
        self.assertIn("流程执行或责任链不稳定", response.rendered_card)
        self.assertIn("平时到底是谁在执行这个动作，谁会对结果负责？", response.rendered_card)

    def test_scattered_colloquial_inputs_can_still_converge(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shell = PMMethodAgentShell(base_dir=tmpdir)
            first_response = shell.handle_message(
                "这个事我还没想太清楚，就是最近老有人说审批容易漏。",
                workspace_id="scattered-flow",
            )
            second_response = shell.handle_message(
                "偏 ToB，主要还是网页上在跑。",
                workspace_id="scattered-flow",
            )
            third_response = shell.handle_message(
                "一线审批专员在用，负责人盯时效，最近投诉多了一点，所以我才开始想看这个。",
                workspace_id="scattered-flow",
            )

        self.assertIn(first_response.case_state.output_kind, {"continue-guidance-card", "context-question-card"})
        self.assertTrue(
            "现在更值得先补" in first_response.rendered_card
            or "先补这几项" in first_response.rendered_card
        )
        self.assertEqual(second_response.action, "reply-case")
        self.assertIn(
            second_response.case_state.output_kind,
            {"continue-guidance-card", "context-question-card", "review-card"},
        )
        self.assertEqual(third_response.action, "reply-case")
        self.assertIn(third_response.case_state.output_kind, {"review-card", "decision-gate-card", "stage-block-card"})
        self.assertNotIn("证据=", third_response.rendered_card)
        self.assertIn("我看到的信号", third_response.rendered_card)

    def test_realistic_toc_partial_metric_reply_can_render_half_step_question(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            first_case = create_case(
                raw_input=(
                    "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，"
                    "新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。"
                ),
                store=store,
            )
            interpreter = LLMReplyInterpreter(
                adapter=StubLLMAdapter(
                    content='{"partial_pending_questions":["成功指标是什么"],"categories":["evidence"],"parser_confidence":"strong"}'
                )
            )
            second_case = reply_to_case(
                case_id=first_case.case_id,
                reply_text="我觉得这件事如果能提升一点发帖率就值得看，但具体目标还没想清。",
                store=store,
                reply_interpreter=interpreter,
            )

        from pm_method_agent.renderers import render_case_state

        rendered_card = render_case_state(second_case)
        self.assertEqual(second_case.output_kind, "review-card")
        self.assertEqual(second_case.metadata.get("follow_up_focus"), "先把刚补到一半的点说完整")
        self.assertIn("发帖率方向已经提到了，再补一句：做到什么程度，你会觉得这轮值得继续？", rendered_card)
        self.assertNotIn("- 成功指标是什么", rendered_card)

    def test_realistic_toc_partial_baseline_reply_can_render_half_step_question(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            first_case = create_case(
                raw_input=(
                    "这是一个 ToC 内容社区 App，新用户注册后 3 天内发帖率偏低，"
                    "新用户和内容运营都在关注这个问题，运营怀疑他们不知道首帖该发什么。"
                ),
                store=store,
            )
            interpreter = LLMReplyInterpreter(
                adapter=StubLLMAdapter(
                    content='{"partial_pending_questions":["当前基线指标是什么"],"categories":["evidence"],"parser_confidence":"strong"}'
                )
            )
            second_case = reply_to_case(
                case_id=first_case.case_id,
                reply_text="现在发帖率确实不高，但我手上没有特别准的数据。",
                store=store,
                reply_interpreter=interpreter,
            )

        from pm_method_agent.renderers import render_case_state

        rendered_card = render_case_state(second_case)
        self.assertEqual(second_case.output_kind, "review-card")
        self.assertEqual(second_case.metadata.get("last_partial_pending_questions"), ["当前基线指标是什么"])
        self.assertIn("发帖率方向已经提到了，再补一个现在的基线值，大概数量级也可以。", rendered_card)
        self.assertNotIn("- 当前基线指标是什么", rendered_card)

    def test_realistic_tob_partial_non_product_reply_can_keep_gate_priority(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = default_store(tmpdir)
            first_case = create_case(
                raw_input=(
                    "这是一个 ToB 审批系统，主要在 PC 端使用。审批专员在日常操作里经常遇到跨部门审批漏人，"
                    "部门负责人对 SLA 结果负责，我现在还没决定是不是要做产品。"
                ),
                store=store,
            )
            interpreter = LLMReplyInterpreter(
                adapter=StubLLMAdapter(
                    content='{"partial_pending_questions":["不改产品能否先解决 60%"],"categories":["decision"],"parser_confidence":"strong"}'
                )
            )
            second_case = reply_to_case(
                case_id=first_case.case_id,
                reply_text="我也在想能不能先靠晨会提醒和流程约束顶一下，但还没比较清楚。",
                store=store,
                reply_interpreter=interpreter,
            )

        from pm_method_agent.renderers import render_case_state

        rendered_card = render_case_state(second_case)
        self.assertEqual(second_case.output_kind, "decision-gate-card")
        self.assertIn("优先评估非产品路径", rendered_card)


if __name__ == "__main__":
    unittest.main()
