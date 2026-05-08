# 文档地图

这份文档用来回答一个问题：

`这么多 Markdown，分别写给谁看，下一步应该先优化哪一批？`

它不是新的产品设计文档，而是后续整理文档体系时的工作台。

## 分层原则

文档先按读者分层，再按优先级优化。

### 用户文档

写给第一次接触项目的人，尤其是产品经理、设计师、产品负责人和业务负责人。

这类文档应该先讲：

- 这个工具能帮我判断什么
- 我什么时候该用
- 我怎么开始
- 我会得到什么
- 当前不能指望它做什么

这类文档不应该一上来讲运行时、接口契约、工具注册、hook 或 prompt 分层。

### 开发文档

写给想接入、改造或贡献代码的人。

这类文档可以保留技术概念，但要明确：

- 这篇文档解决什么工程问题
- 当前哪些已经实现
- 哪些只是设计方向
- 外部接入需要依赖哪些稳定契约

### 设计文档

写给继续推进产品能力和 agent 能力的人。

这类文档可以保留推演过程，但需要标清楚：

- 当前结论是什么
- 哪些规则已经落地
- 哪些仍是后续计划
- 不要让读者误以为所有设计都已经可用

### 发布文档

写给准备提交、打 tag、写 release note 的人。

这类文档要足够具体，能直接判断：

- 能不能发布
- 发布的版本定位是什么
- 必须跑哪些验收
- 哪些能力不能承诺

## 优先级定义

- `P0`：外部用户第一时间会读，必须优先优化。
- `P1`：影响真实试用和版本理解，应在 `v0.2` 前继续整理。
- `P2`：贡献者和后续开发会读，需要逐步规范。
- `P3`：内部设计备忘或历史材料，先标状态，后续再决定是否合并、归档或重写。

## P0：先让人看懂项目

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [README.md](../README.md) | 产品经理、第一次访问仓库的人 | 项目首页 | 已完成产品经理视角重写，后续看真实阅读反馈 |
| [getting-started.md](getting-started.md) | 第一次试用的人 | 入口说明 | 已完成第一轮重写，重点回答“我该选哪个入口” |
| [docs/README.md](README.md) | 所有人 | 文档索引 | 已完成按读者和目的分流 |
| [real-case-testing.md](real-case-testing.md) | 产品经理、体验者 | 真实问题试跑指南 | 已完成第一轮重写，重点说明如何拿自己的问题试 |

## P1：让 v0.2 边界更清楚

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [product-v0-2.md](product-v0-2.md) | 产品负责人、贡献者 | `v0.2` 产品目标 | 已完成产品版本说明重写，减少过程性描述 |
| [v0-2-readiness.md](v0-2-readiness.md) | 发布负责人、贡献者 | `v0.2` 发布准备清单 | 已完成清单化重写 |
| [v0-2-product-rules.md](v0-2-product-rules.md) | 产品设计者、实现者 | `v0.2` 产品规则 | 标出已实现、暂定、未定，减少重复规则 |
| [web-demo-boundaries.md](web-demo-boundaries.md) | 试用者、开发者 | 网页演示边界 | 已完成第一轮重写，明确能做什么、不能做什么和为什么这样设计 |
| [evaluation-cases.md](evaluation-cases.md) | 体验者、测试者 | 典型体验用例 | 已完成第一轮重写，改成更像真实产品工作的试跑样本 |
| [manual-smoke.md](manual-smoke.md) | 维护者 | 手动冒烟 | 保留工程口吻，但让步骤更短、更可复制 |
| [output-style.md](output-style.md) | 产品体验设计者 | 输出风格约束 | 已完成第一轮重写，强调自然、克制、可行动 |

## P2：让贡献者知道系统怎么工作

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [architecture.md](architecture.md) | 开发者、贡献者 | 整体架构 | 每章补“当前实现状态” |
| [agent-architecture.md](agent-architecture.md) | agent 设计者 | 主代理与能力层关系 | 明确当前仍是单协调器，不是完整多代理 |
| [agent-interaction.md](agent-interaction.md) | 开发者、产品设计者 | 主代理状态机 | 与实际 follow-up 和 memory 实现对齐 |
| [agent-shell-runtime.md](agent-shell-runtime.md) | 开发者 | 统一 agent 入口 | 保留技术细节，补入口示例和当前限制 |
| [session-service-design.md](session-service-design.md) | 开发者 | 多轮会话服务 | 标清已实现字段和设计字段 |
| [http-service.md](http-service.md) | 接入者、开发者 | 本地 HTTP 服务 | 改成“最小接入指南 + API 摘要” |
| [integration-examples.md](integration-examples.md) | 接入者 | 接入示例 | 按 CLI、网页、脚本、未来 IDE 分组 |
| [deployment-modes.md](deployment-modes.md) | 部署和接入设计者 | 部署形态 | 明确本地、网页、混合、云端的边界 |

## P2：模型、规则和运行时治理

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [llm-adapter.md](llm-adapter.md) | 开发者 | 模型接入 | 保留 OpenAI 接口格式，减少模型品牌绑定 |
| [llm-boundary-scenarios.md](llm-boundary-scenarios.md) | 产品设计者、开发者 | LLM 使用边界 | 增加“交给模型 / 不交给模型 / 混合判断”表格 |
| [llm-runtime-boundary.md](llm-runtime-boundary.md) | 架构设计者 | 模型与运行时边界 | 保留为核心架构文档，补当前落地状态 |
| [prompt-layering.md](prompt-layering.md) | prompt 维护者 | prompt 分层 | 标清优先级和维护纪律 |
| [rule-layering.md](rule-layering.md) | 规则维护者 | 规则来源分层 | 与项目、仓库、目录、个人规则对齐 |
| [runtime-policy.md](runtime-policy.md) | 开发者 | 运行时策略 | 保留硬约束清单，补示例 |
| [hook-enforcement.md](hook-enforcement.md) | 开发者 | hook 生命周期 | 明确哪些 hook 已接入真实运行时 |
| [operation-enforcement.md](operation-enforcement.md) | 开发者 | 操作前置校验 | 与工具运行时和审批阻塞契约对齐 |
| [approval-blocking-contract.md](approval-blocking-contract.md) | 外壳开发者 | 阻塞提示契约 | 改成更易接 UI 的状态和文案规范 |

## P2：本地工具和平台工具

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [tool-runtime.md](tool-runtime.md) | 开发者 | 工具运行时 | 补工具发现、执行、审批、账本的最小闭环图 |
| [command-executor.md](command-executor.md) | 开发者 | 本地命令执行壳 | 标清安全边界和默认禁用范围 |
| [context-profile.md](context-profile.md) | 产品设计者、开发者 | 场景基础信息 | 改成产品经理能理解的“场景档案”概念 |
| [contracts.md](contracts.md) | 开发者 | 数据契约 | 保持技术文档，补版本稳定性说明 |

## P3：方法和交互设计备忘

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [method-uncertainty-framework.md](method-uncertainty-framework.md) | 产品方法设计者 | 方法不确定性框架 | 可作为方法论文档，后续提炼成用户可读版本 |
| [stage-conclusion-checklist.md](stage-conclusion-checklist.md) | 产品设计者、测试者 | 阶段结论判定 | 与自动化测试样本互相引用 |
| [stage-conclusion-samples.md](stage-conclusion-samples.md) | 测试者 | 阶段结论样本 | 保留样本库属性，减少解释性长文 |
| [partial-follow-up-checklist.md](partial-follow-up-checklist.md) | 测试者、产品设计者 | 半步回答抽查 | 与 follow-up loop 文档合并或互链 |
| [follow-up-loop-design.md](follow-up-loop-design.md) | 产品设计者、开发者 | 连续追问闭环 | 标清哪些规则已实现 |
| [interaction-memory-design.md](interaction-memory-design.md) | 产品设计者 | 互动记忆设计 | 与已实现的 memory suggestions / records 对齐 |
| [memory-write-guardrails.md](memory-write-guardrails.md) | 产品设计者、开发者 | 记忆写入防线 | 保留为重要约束文档，补用户可见规则摘要 |
| [brainstorm-integration.md](brainstorm-integration.md) | 产品设计者 | brainstorm 融合方向 | 标成后续能力，不放到当前主线承诺里 |
| [brainstorm-minimal-design.md](brainstorm-minimal-design.md) | 产品设计者 | brainstorm 最小设计 | 后续决定是否并入复合能力文档 |
| [advanced-agent-runtime.md](advanced-agent-runtime.md) | 架构设计者 | 高级 agent runtime | 明确是后续方向，不代表 `v0.2` 已完成 |

## P3：外壳和网页结构设计

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [ide-skill-minimal-contract.md](ide-skill-minimal-contract.md) | IDE / skill 接入者 | IDE / skill 最小契约 | 标清还未正式发布 skill 包 |
| [web-shell-minimal-contract.md](web-shell-minimal-contract.md) | 网页外壳开发者 | 网页壳契约 | 与当前网页演示实现对齐 |
| [web-demo-information-architecture.md](web-demo-information-architecture.md) | 产品设计者、前端开发者 | 网页信息架构 | 后续和实际页面体验一起更新 |

## 发布和历史文档

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [release-readiness.md](release-readiness.md) | 发布负责人 | 发布检查 | 保留 `v0.1` 和 `v0.2` 判断，避免重复 readiness 内容 |
| [release-process.md](release-process.md) | 发布负责人 | 提交、tag 和 release 流程 | 继续保持命令可复制 |
| [releases/v0.1.0.md](releases/v0.1.0.md) | 使用者、维护者 | 历史版本说明 | 保持不改，作为历史记录 |
| [releases/v0.2.0.md](releases/v0.2.0.md) | 使用者、维护者 | `v0.2.0` 发布说明草稿 | 等正式 tag 前再校准 |

## 根目录历史材料

| 文档 | 读者 | 当前定位 | 下一步 |
| --- | --- | --- | --- |
| [method-skill-design.md](../method-skill-design.md) | 项目维护者 | 早期方法和 skill 拆分设计 | 标成历史材料，后续可归档到 `docs/archive/` |

## 建议执行顺序

### 第一轮：P0 用户入口

目标是让产品经理能顺利开始试用。

当前状态：已完成第一轮优化。

已处理：

1. `README.md`
2. `docs/getting-started.md`
3. `docs/README.md`
4. `docs/real-case-testing.md`

### 第二轮：P1 v0.2 版本边界

目标是让 `v0.2` 对外叙事稳定。

当前状态：已完成主要用户可见文档优化，`v0.2-product-rules.md` 保留为规则明细文档。

已处理：

1. `docs/product-v0-2.md`
2. `docs/v0-2-readiness.md`
3. `docs/web-demo-boundaries.md`
4. `docs/evaluation-cases.md`

### 第三轮：P2 开发和接入文档

目标是让贡献者知道怎么接入、怎么改、哪些契约不能破坏。

当前状态：已完成第一轮状态标注和本地路径清理，后续再逐篇深改。

后续建议顺序：

1. `docs/http-service.md`
2. `docs/integration-examples.md`
3. `docs/agent-shell-runtime.md`
4. `docs/llm-runtime-boundary.md`
5. `docs/tool-runtime.md`

### 第四轮：P3 设计文档归档和合并

目标是减少重复和历史噪音。

当前状态：已完成第一轮状态标注，后续再做合并和归档。

后续建议动作：

- 给设计备忘加“当前状态”
- 合并重复主题
- 把历史材料放进归档目录
- 不再让用户从这些文档开始读
