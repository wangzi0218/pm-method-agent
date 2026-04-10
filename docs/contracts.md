# 契约定义

## 文档目的

本文档定义 `PM Method Agent` 的稳定契约层，用于保证它既能产品化，也能在后续平滑升级。

如果没有这些契约，系统很容易退化成一个“每次都说得不太一样”的普通聊天机器人。

## 核心规则

系统允许推断，但必须始终区分以下几类信息：

- 已观察到的输入
- 基于输入得出的解释
- 建议采取的动作
- 当前仍缺失的证据

## Case State 契约

“案例状态”是当前需求或问题分析过程中的统一状态对象。

它至少应包含：

- 最小场景信息，也就是场景基础信息
- 原始问题描述
- 当前工作流状态
- 当前输出卡片类型
- 归一化后的摘要
- 当前所处阶段
- 已知证据
- 未知项
- 结论项
- 决策关口
- 推荐的下一步动作

具体见 [schemas/case-state.schema.json](/Users/wannz/Documents/sourcetree/pm-method-agent/schemas/case-state.schema.json)。

推荐补充字段：

- `workflow_state`：当前主代理处于哪个运行状态
- `output_kind`：当前要输出哪种卡片
- `blocking_reason`：如果被阻塞，阻塞原因是什么
- `pending_questions`：当前建议用户补充的问题列表

如果进入多轮会话模式，建议继续补充：

- `stage_history`：阶段推进历史
- `conversation_turns`：用户与系统的回合记录
- `answered_questions`：已经被用户补充过的问题
- `resolved_gates`：已经完成的人类决策关口
- `latest_user_reply`：当前这一轮用户的最新补充

这些字段不要求在 CLI 单轮模式下全部实现，但服务层设计应为它们预留位置。

## 场景基础信息契约

“场景基础信息”是方法分析前的轻量场景定义层，用来避免系统在错误上下文里做“看似合理”的判断。

建议支持的关键字段：

- `business_model`：`tob`、`toc`、`internal`
- `primary_platform`：`pc`、`mobile-web`、`native-app`、`mini-program`、`multi-platform`
- `distribution_channel`：产品主要通过什么渠道交付或分发
- `product_domain`：产品所处业务域
- `target_user_roles`：关键用户角色列表
- `constraints`：会显著影响判断的限制条件

这层信息不要求一开始全部完整，但如果缺少它们会显著影响判断，系统就应主动提示用户补齐。

## 分析模块输出契约

每个分析模块都必须按统一结构输出结论项。

核心字段包括：

- `dimension`：这个结论项属于哪个方法维度
- `claim`：分析结论本身
- `claim_type`：事实、推断、挑战、选项，还是缺失信息
- `evidence_level`：证据等级，分为 none、weak、medium、strong
- `evidence`：支撑该结论的具体内容
- `unknowns`：当前还缺什么
- `risk_if_wrong`：如果这个判断错了，风险有多大
- `suggested_next_action`：当前最小但有价值的下一步动作

具体见 [schemas/analyzer-finding.schema.json](/Users/wannz/Documents/sourcetree/pm-method-agent/schemas/analyzer-finding.schema.json)。

## 面向用户的输出形态

虽然底层是结构化数据，但面向用户的默认呈现应当是“轻量结构化审查卡”。

推荐包含：

- 基础信息
- 当前判断
- 关键判断
- 决策关口
- 建议先做
- 建议补充

在主代理模式下，还应支持以下卡片类型：

- 场景补充卡
- 阶段阻塞卡
- 决策关口卡
- 完整审查卡

具体风格见 [docs/output-style.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/output-style.md)。

## 决策关口契约

只有当“是否继续推进当前阶段”真的需要人工判断时，才应该生成决策关口。

典型的 gate 场景包括：

- 当前问题定义是否已经足够扎实，可以继续
- 是否应该优先尝试非产品解法
- 当前 case 是该进入验证，还是应该暂缓

每个 gate 至少应包含：

- `gate_id`
- `stage`
- `question`
- `options`
- `recommended_option`
- `reason`
- `blocking`

具体见 [schemas/decision-gate.schema.json](/Users/wannz/Documents/sourcetree/pm-method-agent/schemas/decision-gate.schema.json)。

## 证据充分度分级

证据充分度必须显式标注。这里的目标不是哲学意义上的“证明真相”，而是让系统诚实表达：当前结论值得被相信到什么程度。

### `none`

适用场景：

- 结论基本只是猜测
- 输入本身并不直接支持这个判断
- 没有任何额外佐证

### `weak`

适用场景：

- 只来自一条用户描述、一个案例或单一视角
- 证据方向合理，但覆盖太窄

### `medium`

适用场景：

- 有多条一致信号指向同一结论
- 已经有一部分客观材料，比如重复案例、流程材料或粗粒度数据

### `strong`

适用场景：

- 结论已经被客观证据、重复观察或可验证记录支撑
- 剩余不确定性已经不会实质影响当前阶段决策

## 和通用 AI Chat 的最小差异化标准

这个产品不应该假装自己无所不知。它真正的价值来自方法约束，而不是“更会聊天”。

一份合格输出至少应满足：

1. 把事实和推断分开
2. 标注证据充分度
3. 显式指出缺失证据
4. 在需要时先补齐场景基础信息
5. 不把低杠杆问题甩给人类决策
6. 给出当前最小且有价值的下一步动作
7. 以审查卡而不是长报告的形态呈现

如果做不到这几点，那它就太接近普通 AI 对话工具了。

## 建议的评测检查项

针对每一个真实案例，建议检查：

- 是否把问题和方案分开了
- 是否在必要时先对齐了场景和产品基础信息
- 是否对低置信度判断做了明确标注
- 是否避免了“假确定性”
- 是否识别出了至少一条有价值的缺失证据
- 是否只在真正重要的地方让人类做决策
