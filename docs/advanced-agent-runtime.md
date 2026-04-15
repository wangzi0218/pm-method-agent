# 高级 Agent Runtime 设计

## 文档目标

这份文档讨论的，不是“多轮对话如何继续”，而是：

`PM Method Agent` 如何从“有状态的主代理入口”，继续演进成“可恢复、可观测、可编排、可治理的 agent runtime”。

这份设计主要回答三类问题：

1. 运行时闭环是否完整
2. prompt 是否具备工程化治理能力
3. sub-agent 是否有可控的生命周期与协作边界

## 当前判断

以当前仓库状态来看，系统已经具备这些基础：

- 统一主代理入口
- `workspace / case / project profile` 三层状态
- 多轮会话承接
- 阶段推进与决策关口
- LLM 增强理解与文案
- CLI 与 HTTP 两类入口

但它还没有进入完整的 agent runtime 阶段。

更准确地说，当前更接近：

- `agent shell`
- `runtime skeleton`

而不是：

- `full agent runtime`

当前还缺的关键层包括：

- 显式 `query loop`
- 跨轮预算与压缩管理
- 模型输出事件流
- 更完整的工具执行账本
- prompt 分层治理
- sub-agent 生命周期编排

不过从当前仓库状态看，运行时已经不再只是空骨架：

- 已有最小 `context budget`
- 已开始把历史分成 `raw history / working memory / summary memory`
- 已能通过 CLI / HTTP 直接观察 runtime session、压缩状态和最近工作记忆
- 已能在模型服务不可用时自动回退到本地规则，并把降级事件写进 runtime event log
- 已开始把回复解释、前置收敛、文案增强的降级状态收敛到统一案例元数据

## 一句话定义

高级 agent runtime 的目标，不是让系统“看起来更像 agent”，而是让系统在复杂交互里仍然保持：

- 可恢复
- 可解释
- 可验证
- 可审计
- 可维护

## 第一部分：运行时闭环

### 1. query loop

如果系统把每一轮输入都当作独立问答，即使有状态存储，也不算真正进入 agent runtime。

更合理的运行方式应当是：

1. 读取当前 runtime session
2. 恢复上一个未结束的执行意图
3. 判断本轮输入属于新任务、继续任务、决策回复、状态纠正还是元问题
4. 进入统一 query loop
5. 在 loop 内推进阶段、工具调用、事件记录和上下文压缩
6. 产出本轮终局事件与可展示结果

建议最小循环：

```text
receive input
-> restore session
-> classify turn
-> run loop step
-> emit events
-> persist runtime state
-> render response
```

### 2. 跨轮状态对象

当前仓库已经有 `workspace / case / project profile`，这是好的起点，但还不够。

建议新增一个更高一层的 `runtime session`，用来承接执行态信息。

建议字段：

- `session_id`
- `workspace_id`
- `active_case_id`
- `runtime_status`
- `current_query_id`
- `current_loop_state`
- `turn_count`
- `resume_from`
- `context_budget`
- `compression_state`
- `pending_hooks`
- `pending_tool_calls`
- `last_terminal_event`
- `children_agent_ids`
- `runtime_metadata`

其中最关键的是：

- `resume_from`
  用来表示下次恢复时要回到哪个执行点，而不只是哪个阶段

- `context_budget`
  用来表示当前上下文预算，而不是等超长后临场截断

- `pending_tool_calls`
  用来保证中断恢复时知道哪些动作已发出、哪些还未闭环

### 3. 终止语义

当前系统已经区分了一部分：

- `completed`
- `blocked`
- `deferred`
- `continued`
- `failed`
- `interrupted`
- `cancelled`

当前这些语义已经在 runtime session 里有了最小实现，但还没有全部映射到更完整的外部交互层和恢复策略。

建议正式区分这些终止语义：

- `completed`
  当前轮次已经完整完成

- `blocked`
  当前轮次因缺信息或缺决策而停住

- `failed`
  本轮执行失败，且需要显式恢复或人工介入

- `interrupted`
  执行过程中被打断，但仍可恢复

- `continued`
  本轮只是承接推进，没有形成真正终局

- `cancelled`
  用户或父级显式取消

- `deferred`
  方法上建议暂缓

如果不区分这些语义，系统在复杂场景里就会把“失败”“中断”“暂缓”“等补信息”都渲染成相似文案，后续很难恢复和审计。

### 4. 模型输出事件流

当前系统仍然主要把模型输出当作：

- 结构化解释结果
- 文案增强结果

这对当前阶段够用，但对完整 runtime 来说还不够。

后续建议把模型输出视为事件流的一部分，而不是只看最终文本。

建议事件类型：

- `turn_received`
- `turn_classified`
- `loop_started`
- `stage_resumed`
- `context_compressed`
- `tool_call_requested`
- `tool_call_completed`
- `tool_call_failed`
- `llm_interpretation_completed`
- `gate_resolved`
- `terminal_state_emitted`

这样做的价值是：

- 可以回放执行过程
- 可以做失败恢复
- 可以做 UI 级别的状态展示
- 可以做后续的运行质量评估

### 5. 工具执行账本

如果后续引入更多工具或 sub-agent，而没有执行账本，系统就会出现一个典型问题：

- 文案看起来结束了
- 但某个工具调用其实还没闭环

建议引入 `execution ledger`：

- 每个 tool call 都要有唯一 id
- 每个 tool call 都要有生命周期状态
- 中断恢复时，系统先检查账本是否闭环

当前仓库已经有了最小骨架：

- `requested`
- `completed`
- `failed`

并且会在下一轮开始时，先自动收口上轮遗留的未闭环项。

建议最小字段：

- `call_id`
- `query_id`
- `tool_name`
- `request_payload`
- `status`
- `started_at`
- `finished_at`
- `result_ref`
- `error`

### 6. context budget

长会话最容易出问题的地方不是“太长”，而是系统没有主动管理上下文。

建议不要等到超长时再临场截断，而是从一开始就设计预算。

建议拆成三层：

- `raw history budget`
- `working memory budget`
- `summary memory budget`

对应策略：

- 原始对话逐步归档
- 当前工作记忆保留高价值事件
- 历史阶段性压缩成结构化摘要

压缩原则：

- 保留未完成关口
- 保留角色关系
- 保留已验证事实
- 保留已失败路径
- 保留当前恢复点

## 第二部分：Prompt 治理

### 1. prompt 不应继续承担什么

在 agent 系统里，最常见的退化方式就是：

- 每发现一个边界问题
- 就往 prompt 里再塞一句话

短期看很快，长期一定失控。

因此必须明确：

prompt 不应承担这些职责：

- 生命周期管理
- 工具结果闭环
- 中断恢复
- 终止语义判定
- 预算管理
- 权限边界执行

这些应由 runtime 负责。

### 2. prompt 分层

建议把 prompt 至少拆成五层：

### `base`

系统基础身份与目标。

### `policy`

行为规则、越权限制、危险动作约束、验证纪律。

### `project`

项目级方法要求、产品领域约束、团队约定输出风格。

### `task`

当前 query 的目标、上下文、阶段与成功标准。

### `agent-role`

当前代理的专属职责，例如主协调器、研究代理、验证代理。

这样做的目的不是“更复杂”，而是为了让后续维护时知道：

- 哪些是全局规则
- 哪些是项目级规则
- 哪些只是当前任务附加要求

### 3. prompt 优先级

建议明确优先级来源，而不是让不同来源的 prompt 互相覆盖。

建议优先级从高到低：

1. 安全与权限规则
2. runtime 强约束
3. agent role 规则
4. 项目级配置
5. 用户追加要求
6. 默认基础 prompt

这里有一个关键点：

`runtime 强约束` 不应只是 prompt 文本，而应尽量体现在代码和契约里。

### 4. prompt 维护纪律

建议为 prompt 变更建立最小纪律：

- 每次新增规则，必须说明对应缺陷类型
- 优先尝试 runtime 修正，而不是直接加 prompt
- 新增 prompt 规则要能映射到测试或回归样本
- 尽量避免“语义重复但措辞不同”的规则堆积

## 第三部分：Sub-agent 编排

### 1. 什么时候才值得引入 sub-agent

不是只要系统变复杂，就该上多代理。

只有在满足这些条件时，sub-agent 才真正有价值：

- 主协调器已经稳定
- 生命周期和账本已经可观察
- 上下文预算已经可管理
- 不同子任务确实可以分工

否则多代理只会让状态更难看清。

### 2. 推荐角色

建议未来如果引入 sub-agent，先固定四类角色：

- `research`
- `implementation`
- `verification`
- `synthesis`

其中：

- `research` 负责补事实、补背景、补候选方向
- `implementation` 负责产出具体变更或方案块
- `verification` 负责独立检查，不与 implementation 合并
- `synthesis` 负责最终整合，但不直接替代 coordinator

### 3. coordinator 的职责

主协调器不能退化成“把 worker 结果转发给用户”。

它至少必须承担：

- 任务拆分
- 结果冲突消解
- 优先级判断
- 最终裁决
- 生命周期收口

如果 coordinator 不承担这些职责，多代理系统就只是“并发调用的包装层”。

### 4. mutable state 隔离

子代理默认应隔离可变状态。

建议原则：

- 共享只读上下文
- 显式写回结果
- 不直接共享父级的可变执行态

否则最容易出现：

- 子代理互相污染上下文
- 父级恢复时无法判断哪个状态可信

### 5. verification 必须独立

`verification` 不应与 `implementation` 合并。

因为两者天然存在偏差：

- implementation 倾向于证明自己方案合理
- verification 应该倾向于找错、找漏、找未闭环

如果把两者混在一起，系统就很容易高估自己完成度。

### 6. 生命周期与 abort 传播

未来一旦有 sub-agent，必须保证：

- 子代理可观测
- 子代理可中止
- 子代理可清理
- 父级 abort 能传播到子级

否则就会产生：

- 孤儿任务
- 重复执行
- 已取消任务继续写状态

建议最小状态：

- `created`
- `running`
- `waiting`
- `completed`
- `failed`
- `cancelled`
- `orphaned`

## 推荐推进顺序

基于当前项目状态，更稳的顺序是：

1. 先补 `runtime session` 契约
2. 再补 `terminal semantics`
3. 再补 `event log / execution ledger`
4. 再补 `context budget`
5. 再做 `prompt layering`
6. 最后再做真正的 `sub-agent orchestration`

## 当前版本最值得先做什么

如果只做一个最小切口，我更建议先做这三件事：

1. 新增 `runtime session` 数据结构
2. 明确 `completed / blocked / failed / interrupted / deferred` 语义
3. 为每轮执行补一个最小 `event log`

因为这三件事一旦有了，后面的 prompt 治理和 sub-agent 编排才有稳定地基。

## 判断是否真的进入下一阶段

可以用这几个问题自查：

- 系统是否知道“当前为什么停在这里”
- 系统是否知道“下次要从哪里恢复”
- 系统是否知道“哪些动作已闭环，哪些还没闭环”
- 系统是否能区分“失败”和“暂缓”
- prompt 是否还在承担 runtime 本该负责的职责
- 如果未来引入 sub-agent，父级是否能真正清理子任务

如果这些问题还答不清，就还不算进入完整的 agent runtime 阶段。
