# 文档索引

这份索引页只做一件事：

`帮你快速找到现在最该看的文档。`

如果你是第一次接触这个项目，不需要从架构文档开始读。

更推荐按下面这条顺序走。

## 第一次使用

- [getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)：第一次该从哪个入口开始
- [integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)：IDE / skill、网页壳和脚本接入分别怎么走
- [http-service.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/http-service.md)：本地 HTTP 服务和最小调用示例

## 外壳接入

- [web-demo-boundaries.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-boundaries.md)：网页 demo 的边界、能力范围和默认部署前提
- [ide-skill-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/ide-skill-minimal-contract.md)：IDE / skill 第一版交互契约
- [web-shell-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-shell-minimal-contract.md)：网页壳第一版页面与字段契约
- [approval-blocking-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/approval-blocking-contract.md)：分析阻塞、规则阻塞、审批待处理的提示方式
- [web-demo-information-architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-information-architecture.md)：最小网页 demo 的页面和交互优先级

## 方法与体验

- [method-uncertainty-framework.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/method-uncertainty-framework.md)：五类方法不确定性框架
- [product-v0-2.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/product-v0-2.md)：当前产品层目标、范围和成功标准
- [evaluation-cases.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/evaluation-cases.md)：典型体验用例
- [manual-smoke.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/manual-smoke.md)：手动冒烟方式
- [real-case-testing.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/real-case-testing.md)：真实问题试跑方法
- [partial-follow-up-checklist.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/partial-follow-up-checklist.md)：半步回答的抽查清单
- [output-style.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/output-style.md)：输出风格与卡片结构

## 主线运行时

- [agent-interaction.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-interaction.md)：主代理状态机与阶段推进
- [follow-up-loop-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/follow-up-loop-design.md)：连续追问闭环和阶段继续规则
- [agent-shell-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-shell-runtime.md)：统一 agent 入口与工作区承接
- [session-service-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/session-service-design.md)：多轮会话与服务层
- [interaction-memory-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/interaction-memory-design.md)：互动与记忆设计

## 规则与执行

- [runtime-policy.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/runtime-policy.md)：运行时硬约束
- [hook-enforcement.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/hook-enforcement.md)：hook 生命周期与阻断闭环
- [operation-enforcement.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/operation-enforcement.md)：动作、命令、读写路径的统一前置校验
- [command-executor.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/command-executor.md)：本地命令执行壳
- [tool-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/tool-runtime.md)：本地工具运行时
- [rule-layering.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/rule-layering.md)：规则来源与作用域
- [prompt-layering.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/prompt-layering.md)：prompt 分层与优先级

## 模型与边界

- [llm-adapter.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/llm-adapter.md)：OpenAI-compatible 的 LLM 接入方式
- [llm-boundary-scenarios.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/llm-boundary-scenarios.md)：哪些能力适合交给 LLM，哪些不适合
- [llm-runtime-boundary.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/llm-runtime-boundary.md)：哪些能力由 runtime 持有，哪些能力适合 LLM 或混合判定

## 架构与路线图

- [architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/architecture.md)：整体架构
- [agent-architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-architecture.md)：主代理与专项能力关系
- [deployment-modes.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/deployment-modes.md)：本地、网页、混合模式
- [implementation-roadmap.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/implementation-roadmap.md)：当前做到哪一步，以及后续计划
- [advanced-agent-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/advanced-agent-runtime.md)：更完整的 agent runtime 设计

## 发布与版本

- [release-readiness.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-readiness.md)：首次公开发布检查项
- [release-process.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-process.md)：提交、推送和版本建议
- [releases/v0.1.0.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/releases/v0.1.0.md)：版本说明

## 补充设计

- [contracts.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/contracts.md)
- [context-profile.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/context-profile.md)
- [brainstorm-integration.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/brainstorm-integration.md)
- [brainstorm-minimal-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/brainstorm-minimal-design.md)
