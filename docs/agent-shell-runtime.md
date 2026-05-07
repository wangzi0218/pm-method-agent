# 最小 Agent 外壳运行时

## 目标

当前阶段不直接绑定某个具体 AI 宿主，而是先补一个最小统一入口运行时。

这样做的原因是：

- 先验证单入口触发是否自然
- 先验证活跃 case 和项目背景如何承接
- 先把 skill / agent 的核心逻辑沉淀在仓库内部

等这层稳定后，再挂到具体 skill、IDE agent 或其他宿主上。

## 当前实现

当前仓库已经补上：

- `src/pm_method_agent/agent_shell.py`
- `src/pm_method_agent/workspace_service.py`
- `pm-method-agent agent`
- `pm-method-agent workspace`

这层运行时负责：

- 统一接收用户当前一句话
- 判断更像新建分析、继续分析、补项目背景、读取建议、读取历史还是查看工作区
- 维护当前工作区的活跃 case
- 维护当前工作区绑定的 project profile
- 调用现有的 case service、project profile service 和渲染器

## LLM 回退事件

当某个 LLM 增强组件失败时，runtime event log 会记录 `llm-fallback`，但不会默认把整轮运行标记为失败。

事件 payload 会包含：

- `component` / `component_label`：失败发生在哪一层，例如回复理解、前置收敛、文案增强。
- `failure_kind`：归一化后的失败类型，例如 `timeout`、`network-error`、`invalid-json`、`empty-result`、`contract-violation`。
- `user_message`：给网页、IDE 或 agent 外壳展示的一句话解释。
- `affects_main_flow`：当前默认是 `false`，表示该增强失败不直接改变主线阶段推进。

这层事件的作用，是让外壳和调试工具知道“哪一层回退了”，而不是要求用户阅读底层异常文本。

对外展示时，外壳应优先消费 runtime payload 中的 `event_summaries`。它已经把底层事件收成 `kind`、`stage`、`text`、`severity` 和 `actionable`，适合直接放进网页运行时面板或 IDE 侧边栏。

如果外壳需要解释状态枚举，优先读取 `runtime_contract` 或 `GET /runtime/contract`。它会列出稳定的运行状态、循环状态、终止语义、事件类型和继续动作，避免每个外壳自己维护一套硬编码翻译。

如果要展示“还有什么没闭环”，优先读取 `open_items`。它会统一表达待审批、未完成 hook 和未完成工具调用，避免外壳自己分别拆 `pending_approvals`、`pending_hooks` 和 `pending_tool_calls`。

每一轮新输入开始时，runtime 会先做一次恢复检查：未完成的 hook 和工具调用会被自动收口并写回账本，待人工确认的审批不会自动关闭。检查结果会写入 `recovery_summary`，如果上一轮确实有未闭环事项，还会产生 `runtime-recovery-applied` 事件，外壳可以直接通过 `event_summaries` 展示“系统刚刚处理了什么、还有什么需要人确认”。

如果要展示“这一轮到底怎么走的”，优先读取 `query_loop`。它不是新的业务判断层，而是从 `event_log`、`last_terminal_event`、`open_items` 和 `recovery_summary` 推导出来的查询循环摘要，用来回答：这一轮编号是什么、现在是否结束、最后停在哪一步、还有多少待闭环事项、关键步骤有哪些。

如果要给用户一个“现在怎么继续”的提示，优先读取 `resume_suggestions`。它会基于待审批、阻塞状态、暂缓状态、失败状态和活跃案例，给出少量下一步建议。`query_loop` 解释发生了什么，`resume_suggestions` 告诉用户接下来可以怎么接。

如果外壳要真正执行建议，优先走 `POST /workspaces/{workspace_id}/runtime/resume-actions` 或 CLI 的 `resume` 子命令。这个入口会把建议动作分发到消息入口、审批入口或运行时查看入口，但不会替用户补写内容，也不会绕过审批。

如果要展示“恢复点在哪里”，优先读取 `resume_point`，不要直接把底层 `resume_from` 展示给用户。`resume_point` 会把方法阶段、当前案例、待审批、工具动作等恢复来源收成 `label`、`title` 和 `text`。

## 当前状态模型

### `workspace`

这一层不是单个 case，也不是长期用户档案，而是“当前工作上下文”。

当前最小字段包括：

- `workspace_id`
- `active_case_id`
- `active_project_profile_id`
- `recent_case_ids`
- `metadata.approval_preferences`

这意味着系统已经能：

- 记住你当前主要在聊哪个 case
- 记住你当前所在项目的大背景
- 在后续一句补充里默认接住当前上下文
- 列出最近几个案例，并在它们之间切换
- 给当前工作区保存局部审批偏好，例如自动批准某些低风险动作

### `case`

`case` 仍然是方法分析的最小单元。

它负责记录：

- 当前阶段
- 已回答的问题
- 已触发或已解决的决策关口
- 多轮输入和卡片历史

### `project profile`

这一层负责承接跨 case 的相对稳定背景，例如：

- 产品类型
- 主要平台
- 业务领域
- 长期约束
- 长期关注指标

当前运行时会把这三层拆开，而不是把所有上下文都塞进单个 case。

## 当前支持的交互动作

### 1. `create-case`

适用于：

- 新点子
- 草稿
- 抱怨
- 现象描述

### 2. `reply-case`

适用于：

- 对当前活跃案例的补充说明
- 对当前卡片的继续回答

### 3. `project-profile-updated`

适用于：

- 补项目背景
- 补长期约束
- 补长期关注指标

### 4. `show-guidance`

适用于：

- “我现在下一步该做什么”
- “最该补什么”
- “现在怎么推进”

### 5. `show-history`

适用于：

- “看看之前的判断”
- “这个 case 做过哪些决定”

### 6. `show-workspace`

适用于：

- “看看最近几个案例”
- “当前工作区里都有什么”
- “我现在在看哪个案例”

### 7. `switch-case`

适用于：

- “切到上一个案例”
- “切到 case-xxxxxx”
- “把当前案例切回刚才那个”

## 当前分流规则

当前实现不是靠一个大 prompt 来决定全部行为，而是由本地运行时先做入口分流，再在局部环节使用 LLM 增强理解。

当前会优先识别这几类输入：

- 新问题或新草稿
- 当前案例的补充回答
- 项目背景补充
- 元问题或使用指导
- 历史查看
- 工作区查看与案例切换

当前还专门做了两类兜底：

- 元问题不会污染当前活跃案例
- 显式纠正会覆盖旧角色，而不是一味并集

## 当前使用方式

源码直跑：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "前台最近老是漏提醒患者，我在想是不是要处理一下。"
```

继续补一句：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "这是一个 ToB 移动端产品，前台使用，管理者负责结果。"
```

查看当前工作区：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli workspace demo
```

更新当前工作区审批偏好：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --format json \
  workspace demo \
  --approval-preferences-json '{"auto_approve_actions":["project-profile-service.update-or-create"]}'
```

切到上一个案例：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "切到上一个案例。"
```

也可以显式切换：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli workspace demo \
  --switch-case-id case-xxxxxx
```

补项目背景：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "这个项目是 ToB 医疗服务平台，主要跑在移动端。"
```

询问当前建议：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "我现在下一步该做什么？"
```

也可以通过 HTTP service 调用同一层运行时：

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "前台最近老是漏提醒患者，我在想是不是要处理一下。"
  }'
```

读取最近案例：

```bash
curl http://127.0.0.1:8000/workspaces/demo/cases
```

## 和未来 skill / agent 的关系

这层运行时不是最终交付形态，而是：

- skill / agent 外壳之前的统一逻辑层

更准确地说：

- 未来 skill 负责触发和展示
- `agent shell runtime` 负责判断和承接

这样后续不管挂：

- IDE skill
- AI 工具中的 agent
- MCP 外壳

都不需要把触发识别和工作区状态再做一遍。

## 当前边界

这一层现在已经够用来承接：

- CLI 体验
- 本地 agent / skill 演示
- HTTP 集成验证

但它还不是最终宿主层。当前仍然没有补：

- 长期用户偏好记忆
- 多项目并行下的更细粒度切换策略
- 真正的 IDE 插件或 MCP 外壳

## 下一步建议

基于当前实现，后续更适合按这个顺序继续：

1. 继续补复杂角色关系和长尾回复解释。
2. 再把这一层挂到真实 skill / agent 宿主。
3. 再补更细的用户偏好与长期记忆。
4. 最后再补网页或 MCP 适配外壳。
