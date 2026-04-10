import os
import unittest
from tempfile import TemporaryDirectory

os.environ.setdefault("PMMA_DISABLE_ENV_AUTOLOAD", "1")

from pm_method_agent.agent_shell import PMMethodAgentShell


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
        self.assertIn("更像哪几类问题", first_response.rendered_card)

        self.assertEqual(second_response.action, "reply-case")
        self.assertEqual(second_response.case_state.output_kind, "review-card")
        self.assertEqual(second_response.case_state.workflow_state, "done")
        self.assertIn("## 关键判断", second_response.rendered_card)

        self.assertEqual(third_response.action, "reply-case")
        self.assertEqual(third_response.case_state.output_kind, "decision-gate-card")
        self.assertEqual(third_response.case_state.workflow_state, "blocked")
        self.assertIn("建议=暂缓", third_response.rendered_card)

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
        self.assertIn("## 建议补充", response.rendered_card)
        self.assertIn("成功指标是什么", response.rendered_card)
        self.assertNotIn("输入里已经带出方案", response.rendered_card)

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
        self.assertIn("更建议先沿哪条继续", first_response.rendered_card)

        self.assertEqual(second_response.action, "reply-case")
        self.assertEqual(second_response.case_state.output_kind, "decision-gate-card")
        self.assertEqual(second_response.case_state.workflow_state, "blocked")
        self.assertIn("优先评估非产品路径", second_response.rendered_card)

        self.assertEqual(third_response.action, "reply-case")
        self.assertEqual(third_response.case_state.output_kind, "review-card")
        self.assertEqual(third_response.case_state.workflow_state, "done")
        self.assertIn("验证设计", third_response.rendered_card)

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


if __name__ == "__main__":
    unittest.main()
