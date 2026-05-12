# v0.2 真实问题回归记录

这份记录用于回答一个问题：`v0.2` 是否只在 demo 医疗场景里看起来可用，还是能承接更真实、更分散的产品草稿。

它不是标准答案集。每个样本更关注系统有没有守住方法边界：能不能承接上下文、能不能识别该停下来的地方、能不能避免把用户的方案当成正确答案。

## 本轮覆盖范围

本轮重点覆盖 6 类容易退化的场景：

- 方案先行：用户直接提出浮层、入口、导出等做法。
- 问题模糊：只有抱怨或现象，还没有完整背景。
- 半步回答：用户只补了一部分信息，系统不能重复追问所有问题。
- 记忆误用：工作区已有项目背景，但新问题明确换了产品类型或平台。
- 跨行业复杂角色：不只医疗、内容社区，还包括供应链、仓库、财务、采购等角色。
- 低优先级暂缓：用户明确说反馈少、资源紧、晚做损失不大。

## 自动化样本

这些样本已经进入 `tests/test_human_like_flows.py`。

| 样本 | 验证重点 | 期望结果 |
| --- | --- | --- |
| `test_v02_regression_tob_process_issue_can_hold_non_product_path` | ToB 流程问题、非产品路径 | 系统能停在决策关口，不默认产品化。 |
| `test_v02_regression_toc_growth_metric_can_move_to_validation` | ToC 增长指标、验证前提 | 系统能承接指标和停止条件，不误套企业产品判断。 |
| `test_v02_regression_solution_first_mobile_case_keeps_problem_framing` | 移动端方案先行 | 系统能提醒先确认真实问题，不直接进入浮层方案。 |
| `test_v02_regression_reused_project_background_can_be_overridden_by_new_context` | 记忆误用防线 | 已有 ToB 项目背景时，新输入里的 ToC App 背景优先。 |
| `test_v02_regression_cross_industry_roles_can_continue_same_case` | 跨行业复杂角色 | 供应链、仓库员、财务、采购负责人能被识别，并承接同一案例。 |
| `test_v02_regression_low_priority_request_can_defer_without_productizing` | 低优先级暂缓 | 用户说不急、资源紧、晚三个月损失不大时，系统进入暂缓语义。 |

## 本轮发现并修复的问题

### 1. 供应链场景容易被误判成新案例

试跑时，第一轮输入是供应链入库复核问题，第二轮补充月末积压、仓库员、财务和采购负责人。系统一开始会把第二轮当成新案例，因为连续承接关键词主要覆盖医疗、门店和内容社区。

修复方式：扩展连续承接关键词，加入 `仓库`、`财务`、`采购`、`供应链`、`入库`、`复核`、`账实`。

### 2. 跨行业角色识别不够完整

同一供应链样本里，系统能识别采购负责人，但漏掉仓库员和财务。

修复方式：扩展角色词表，加入 `仓库员`、`仓管员`、`仓库主管`、`财务`、`财务负责人`。

## 当前通过命令

```bash
PYTHONPATH=src python3 -m unittest tests.test_human_like_flows
```

发布前仍建议跑完整回归：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
bash scripts/web_demo_acceptance.sh
```

## 仍然没有承诺的事

本轮只增强了本地规则和回归样本，不代表系统已经能完整理解所有行业角色。

后续如果要继续扩行业，应该优先让 LLM 参与语义归一化，同时保留这些本地回归样本作为底线，而不是无限扩硬编码词表。

