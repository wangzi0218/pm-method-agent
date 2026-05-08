# 文档索引

这不是一份需要从头读到尾的目录。

如果你第一次接触 `PM Method Agent`，建议先按你的目的选一条路径。

## 我想先试用

- [快速开始](getting-started.md)：从哪里开始，CLI 和网页演示怎么选。
- [真实问题试跑](real-case-testing.md)：怎么拿自己的真实问题测试效果。
- [典型体验用例](evaluation-cases.md)：不知道输入什么时，可以从这些例子开始。
- [手动冒烟](manual-smoke.md)：维护者快速检查本地链路是否正常。

## 我想理解它的产品边界

- [v0.2 产品定义](product-v0-2.md)：这一版到底想解决什么问题。
- [v0.2 发布准备清单](v0-2-readiness.md)：这一版具备什么、不承诺什么、发布前要验什么。
- [v0.2 产品规则](v0-2-product-rules.md)：当前已定、暂定和未定的产品规则。
- [网页演示边界](web-demo-boundaries.md)：网页演示能做什么、不能做什么。
- [输出风格](output-style.md)：审查卡和对话输出应该长什么样。

## 我想理解方法本身

- [方法不确定性框架](method-uncertainty-framework.md)：产品问题定义中常见的不确定性类型。
- [阶段结论判定清单](stage-conclusion-checklist.md)：什么时候继续问，什么时候先给阶段结论。
- [阶段结论样本](stage-conclusion-samples.md)：过问和漏关口的样本。
- [半步回答抽查清单](partial-follow-up-checklist.md)：用户只回答一部分时，系统应该怎么承接。
- [连续追问闭环](follow-up-loop-design.md)：多轮追问和阶段继续规则。
- [互动记忆设计](interaction-memory-design.md)：项目背景、当前案例和长期偏好怎么被记住。
- [记忆写入防线](memory-write-guardrails.md)：哪些信息能记、什么时候必须让用户确认。

## 我想接入或开发

- [接入示例](integration-examples.md)：CLI、网页壳和脚本接入怎么走。
- [本地 HTTP 服务](http-service.md)：服务端点和最小调用示例。
- [统一 agent 入口](agent-shell-runtime.md)：工作区、案例和多轮承接的入口设计。
- [会话服务设计](session-service-design.md)：多轮会话和案例状态如何保存。
- [部署形态](deployment-modes.md)：本地、网页、混合和云端形态怎么区分。
- [IDE / skill 最小契约](ide-skill-minimal-contract.md)：未来 IDE 或 skill 入口需要满足什么。
- [网页壳最小契约](web-shell-minimal-contract.md)：网页外壳需要消费哪些数据。
- [网页信息架构](web-demo-information-architecture.md)：网页演示的信息层级。

## 我想理解架构

- [整体架构](architecture.md)：项目的主架构。
- [主代理与能力层](agent-architecture.md)：主代理和专项能力之间的关系。
- [主代理交互](agent-interaction.md)：阶段推进和交互状态。
- [高级 Agent Runtime](advanced-agent-runtime.md)：更完整的 agent runtime 方向。
- [数据契约](contracts.md)：核心对象和字段约定。
- [场景档案](context-profile.md)：产品类型、平台、角色等基础信息。

## 我想理解模型、规则和工具层

- [LLM 接入](llm-adapter.md)：兼容 OpenAI 接口格式的模型接入方式。
- [LLM 边界场景](llm-boundary-scenarios.md)：哪些能力适合交给模型，哪些不适合。
- [模型与运行时边界](llm-runtime-boundary.md)：哪些控制逻辑必须留在运行时。
- [prompt 分层](prompt-layering.md)：prompt 来源、优先级和维护方式。
- [规则分层](rule-layering.md)：项目、仓库、目录和个人规则如何生效。
- [运行时策略](runtime-policy.md)：运行时硬约束。
- [hook 执行](hook-enforcement.md)：hook 生命周期与阻断闭环。
- [操作前置校验](operation-enforcement.md)：动作、命令和写入路径如何先被检查。
- [工具运行时](tool-runtime.md)：本地工具和平台工具的统一执行层。
- [命令执行壳](command-executor.md)：本地命令执行的安全边界。
- [审批阻塞契约](approval-blocking-contract.md)：外壳如何展示阻塞和待确认操作。

## 我想看发布和路线

- [实现路线图](implementation-roadmap.md)：当前做到哪一步，后续怎么走。
- [发布检查](release-readiness.md)：公开发布前要检查什么。
- [提交与发布流程](release-process.md)：提交、tag 和 release note 怎么处理。
- [v0.1.0 发布说明](releases/v0.1.0.md)：首个公开版本说明。
- [v0.2.0 发布说明草稿](releases/v0.2.0.md)：下一版发布说明草稿。

## 我想整理这些文档

- [文档地图](documentation-map.md)：所有 Markdown 的读者、优先级、当前定位和后续优化顺序。

## 补充设计

- [brainstorm 融合方向](brainstorm-integration.md)：如何把 brainstorm 能力接入主线。
- [brainstorm 最小设计](brainstorm-minimal-design.md)：最小 brainstorm 形态。
