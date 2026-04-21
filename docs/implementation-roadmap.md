# 实现路线图

## 目标

把当前的概念设计，推进成一个可复用、GitHub 友好、并且实现路径清晰的开源项目。

## 第一阶段：基础层

交付物：

- 仓库 README
- 架构文档
- 契约文档
- 可机读的数据结构定义

完成标志：

- 新贡献者能在 10 分钟内理解项目问题域、架构方向和升级路径

当前状态：

- 已完成

## 第二阶段：核心运行时

建设内容：

- 一个 `pm-method-agent` 统一入口
- 一个场景基础信息输入层
- 一个案例状态对象
- 一个阶段路由器
- 三个内部模块：问题定义、决策挑战、验证设计
- 一套默认的审查卡输出形态
- 一份主代理交互设计

完成标志：

- 同一个需求被反复分析时，输出结构仍然稳定一致
- 主代理能够按阶段推进，而不是机械跑完整流程

当前状态：

- 已完成基础版本
- 当前已具备 case 状态、阶段推进、关口控制和默认审查卡

## 第三阶段：评测集

建设内容：

- 10 到 20 个真实或高仿真的需求案例
- 一套真实问题试跑方法，支持用模糊草稿、抱怨、指标异常和方案先行输入做体验检查
- 覆盖企业产品、消费者产品、桌面端、移动端、小程序、不同渠道和不同用户角色的场景组合
- 每个案例的期望输出特征
- 针对证据等级和决策关口的回归检查

完成标志：

- 分析提示词或分析模块逻辑调整后，可以用稳定案例做回归验证
- 体验用例已经能覆盖 ToB、ToC、PC、移动端、流程型和增长型问题

当前状态：

- 已完成基础评测集与真实试跑文档
- 当前已有 smoke tests 与更贴近自然输入的人类化流程测试
- 已开始沉淀五类方法不确定性的真实草稿回归样本，并持续用国民级应用 mock 做误判抽查

当前可直接参考：

- [docs/evaluation-cases.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/evaluation-cases.md)
- [docs/real-case-testing.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/real-case-testing.md)

## 第四阶段：封装交付

这一阶段不应把 CLI、网页和 agent 拆成彼此独立的产品。

更合理的目标是先补服务层，再挂接多种入口。

建议交付形态：

- 命令行工具
- 本地 HTTP 服务
- 主代理入口
- 可选网页界面
- 内部或对外 API

完成标志：

- 外部用户不需要先读内部文档，也能开始使用系统
- 至少具备一次“可以公开推 GitHub”的最低交付质量
- CLI、网页和 agent 入口复用同一套方法内核与服务层

建议这一阶段按顺序推进：

1. 先补服务层和会话承接能力
2. 再补 LLM 适配层和解释器注入点
3. 再补本地 HTTP 服务
4. 再定义交互层与记忆层
5. 再做主代理 / skill 入口
6. 再按需要补交互网页
7. 最后视需要开放 API 或 MCP 接入层

当前状态：

- 已完成服务层和会话承接能力
- 已完成 OpenAI-compatible 的 LLM 适配骨架
- 已完成本地 HTTP 服务
- 已完成工作区、项目背景和统一 agent 入口
- 已完成第一轮对外入口文档、接入示例与外壳契约收口
- 已完成网页 demo 的边界收口文档，开始把“网页是什么、不是什么、默认怎么部署”说清楚
- 已开始真实网页 demo 实现，并已接入现有 HTTP 服务
- 已完成网页 demo 多轮阅读流、历史区、运行时区和信息层级的第一轮产品化打磨
- 当前处于第四阶段的后段：入口形态已经具备，下一步更值得回到产品层，把“连续追问闭环”和“可持续使用”收成明确目标
- 当前尚未补 MCP 外壳、真实网页壳实现和更完整的外部集成示例

发布前检查可参考：

- [docs/release-readiness.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-readiness.md)

下一阶段设计可参考：

- [docs/agent-shell-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-shell-runtime.md)
- [docs/http-service.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/http-service.md)
- [docs/interaction-memory-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/interaction-memory-design.md)
- [docs/session-service-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/session-service-design.md)
- [docs/llm-adapter.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/llm-adapter.md)
- [docs/llm-boundary-scenarios.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/llm-boundary-scenarios.md)
- [docs/llm-runtime-boundary.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/llm-runtime-boundary.md)
- [docs/advanced-agent-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/advanced-agent-runtime.md)

本阶段下一步更适合继续：

1. 先把 `v0.2` 产品目标和非目标定清，重点定义“模糊草稿进入后，系统如何连续推进到阶段结论”。
2. 继续补连续追问闭环，明确什么时候追问、一次问几项、回答后如何只从卡点继续。
3. 把“哪些能力由 runtime 持有、哪些能力交给 LLM、哪些能力走混合判定”的边界收紧，再接追问自然化和长尾语义增强。
4. 把项目背景、工作区记忆和长期偏好做成用户可理解的产品能力，而不只是底层状态对象。
5. 再回到实现层，继续把 query loop、恢复策略和更细的工具闭环接进统一 runtime。

## 第五阶段：复合升级

只有在前两个阶段稳定之后，才进入这一阶段。

可选升级项：

- 在 `problem_definition` 前增加有限发散的前置收敛层
- 分析模块并行执行
- 专项智能体委派
- 更丰富的决策关口和案例历史界面

约束条件：

- 升级运行时形态时，不应破坏已有稳定契约

进一步设计可参考：

- [docs/brainstorm-integration.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/brainstorm-integration.md)
- [docs/brainstorm-minimal-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/brainstorm-minimal-design.md)

当前状态：

- 已完成 brainstorm 方向设计文档
- 还未进入稳定的复合代理实现阶段

建议进入这一阶段的前提：

- 工作区与统一入口的对外契约稳定
- LLM 增强边界稳定
- 长尾交互回归样本足够覆盖

## 第六阶段：高级 Agent Runtime

这一阶段关注的，不再只是“能多轮对话”，而是系统是否具备更完整的代理运行时。

如果没有这一层，产品即使接入了 LLM、多轮状态和主代理入口，也仍然更像“有状态问答器”，而不是“可恢复、可编排、可审计的 agent 系统”。

### 6.1 运行时闭环

需要重点补齐：

- 明确的 `query loop`，而不是把每轮都当作独立问答
- 跨轮状态对象，记录恢复点、turn 计数、压缩摘要、hook 执行状态、预算状态
- 把模型输出视为事件流，而不只是最终文案
- 中断后的未完成工具结果补齐与执行账本闭环
- 区分完成、失败、恢复、继续、取消等终止语义
- 长会话的 `context budget` 与主动压缩策略

当前状态：

- 已有基础多轮状态和恢复点
- 已有最小 `runtime session`、事件日志和执行账本骨架
- 已把事件、工具调用和 hook 调用的 id 分配收敛到单调计数器，避免截断或恢复后重复编号
- 已补上 `failed / interrupted / cancelled` 的正式终止语义
- 已补最小 `context budget` 压缩闭环，开始区分 `raw history / working memory / summary memory`
- 已补最小 CLI / HTTP 观察口，能直接查看 runtime session、压缩状态和工作记忆
- 已补最小 LLM 降级闭环，模型不可用时会自动回退到本地规则，并记录 `llm-fallback` 事件
- 已开始把回复解释、前置收敛、文案增强三层的降级状态收敛到统一案例元数据
- 还没有完整的 query loop、事件流语义和更细的工具恢复闭环

建议交付物：

- `runtime session object` 契约
- `event log / execution ledger` 契约
- 中断恢复与压缩策略设计文档
- 至少一版本地可观察的生命周期状态

### 6.2 Prompt 治理层

未来一旦进入更完整的 agent 形态，prompt 本身也必须工程化，而不是继续靠零散追加。

需要重点补齐：

- 把身份描述、行为规则、工具约束、输出纪律分层组织
- 明确 prompt 的优先级来源，例如默认、项目、自定义、追加、agent 专属
- 把危险动作、越权动作、验证纪律写成显式规则
- 避免让 prompt 承担本该由 runtime 处理的职责
- 保证团队可以稳定维护，而不是每次修 bug 都往 prompt 里追加一句话

当前状态：

- 已有最小 `prompt composition` 实现，并已接入主要 LLM 入口
- 已有项目级和追加级 prompt 注入点
- 已有最小规则加载器，能吸收用户本地、仓库级、目录级和结构化策略规则
- 已有最小 runtime policy，能执行意图级和内部动作级的一部分运行时硬约束
- 已补命令白名单、命令阻断和写入范围的策略骨架
- 已补统一的 operation enforcement，开始收敛动作、命令和写入路径的前置校验结果
- 已补最小 hook enforcement，开始把前置校验挂到真实运行时生命周期
- 已补最小本地命令执行壳，开始把 hook 和执行账本挂到真实执行入口
- 已补最小本地 tool runtime，开始把具体工具和公共执行链路分层
- 已补本地工具注册元数据，开始给外壳暴露稳定的工具发现契约
- 已补读 / 写 / 命令三类最小本地工具组合
- 已补最小读取路径策略，开始把只读工具接进 runtime policy 与 hook enforcement
- 已补最小目录枚举工具，开始让 agent 能在受控范围内先看目录结构，再决定读哪些文件
- 已补最小文本搜索工具，开始形成“列目录 → 搜关键词 → 读文件”的本地检索链路
- 已补统一工具注册层，开始把本地工具和平台工具收敛到同一套发现与执行入口
- 已补第一个可写平台工具，并接进 runtime、hook 和动作级策略
- 还没有更完整的 prompt 来源治理、验证纪律清单和回归策略

建议交付物：

- `prompt layers` 设计文档
- prompt 来源优先级表
- 危险动作与验证纪律清单
- prompt 变更回归策略

### 6.3 Sub-agent 编排层

如果后续引入 sub-agent，这一层必须先设计好，不然多代理只会增加噪音和状态泄漏。

需要重点补齐：

- fork 时的 cache-safe 参数与 prompt cache 共享策略
- 子代理默认隔离 mutable state
- 区分 research、implementation、verification、synthesis 等角色
- coordinator 真正承担综合理解，而不是只转发 worker 结果
- verification 与 implementation 分离
- agent 生命周期可观测、可中止、可清理
- 父级 abort 能传播到子代理，避免孤儿任务残留

当前状态：

- 还未进入真实 sub-agent 运行时
- 当前主代理更接近单协调器 + 结构化能力层

建议交付物：

- sub-agent 生命周期模型
- coordinator / worker / verifier 角色契约
- 父子状态传播与终止语义设计
- 最小可运行的多代理实验流

### 这一阶段的判断标准

达到以下标准后，才可以说项目开始从“有状态 agent 入口”走向“真正的 agent runtime”：

- 系统能够回答“当前为什么停在这里、接下来要恢复什么”
- 中断、失败、继续、恢复在系统内是不同语义，而不是同一类文案
- prompt 不再承担运行时本该负责的控制职责
- 子代理协作是可观测、可审计、可清理的
