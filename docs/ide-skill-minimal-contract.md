# IDE / Skill 最小交互契约

这份文档只回答一个问题：

`如果把 PM Method Agent 接进 IDE 或 skill，第一版交互到底该怎么表现。`

它不讨论宿主平台的具体 SDK，也不讨论 UI 样式。

它主要关心：

- 用户怎样触发
- skill 该展示什么
- 什么时候继续承接，什么时候切案例
- 遇到阻塞或审批时，外壳应该怎么处理

## 一句话建议

第一版 IDE / skill 外壳不要试图“自己变聪明”。

更稳的方式是：

1. 用户继续自然说话
2. 外壳统一把消息交给 `POST /workspaces/{workspace_id}/messages`
3. 外壳优先展示 `message` 和 `rendered_card`
4. 案例推进、阶段切换和大部分追问顺序继续交给内核

## 第一版应该支持的四类动作

### 1. 新建或继续分析

这是最核心的动作。

推荐接口：

- `POST /workspaces/{workspace_id}/messages`

用户常见说法例如：

- “帮我看看这个需求值不值得做”
- “最近前台老漏提醒，我在想是不是该处理一下”
- “补充一下，这是一个 ToB 产品”
- “这轮我更关心的是投诉，不是参与率”

外壳不要自己区分这是：

- 新建 case
- 继续 case
- 补背景
- 补目标

更稳的做法是直接把原话交给内核。

### 2. 查看当前建议

推荐接口：

- 仍然优先用 `POST /workspaces/{workspace_id}/messages`

用户常见说法例如：

- “我现在下一步该做什么”
- “最该补什么”
- “继续”

如果你接的是 HTTP 层，不需要自己推导“当前应该展示 guidance 还是 history”。

### 3. 切换案例

推荐接口：

- `GET /workspaces/{workspace_id}/cases`
- `POST /workspaces/{workspace_id}/active-case`

用户常见说法例如：

- “切到上一个案例”
- “看下刚才那个需求”
- “切到 case-xxxxxx”

第一版建议：

- 如果宿主支持列表操作，就通过列表切换
- 如果宿主更像聊天窗口，也可以继续把自然语言发给 `workspaces/messages`

### 4. 处理审批或阻塞

推荐接口：

- `GET /workspaces/{workspace_id}/runtime/approvals`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/approve`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/reject`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/expire`

这一层适合：

- 有真实工具动作的 skill
- 需要在 IDE 里弹审批确认的外壳

如果第一版只是做需求分析体验，不一定马上要把审批流露给最终用户。

## 第一版最小展示结构

IDE / skill 外壳不需要像网页壳那样拆很多区块。

第一版更推荐保留三块：

### 1. 用户输入区

这里负责：

- 输入草稿
- 继续补充
- 发起追问回答

外壳不需要给用户额外加“问题定义 / 决策挑战 / 验证设计”切换开关。

### 2. 主响应区

这里建议优先展示：

- `message`
- `rendered_card`

建议顺序：

1. 先展示 `message`
2. 再展示 `rendered_card`

因为：

- `message` 更像当前系统动作说明
- `rendered_card` 更像本轮主内容

### 3. 辅助区

这里可以逐步支持：

- 最近案例
- 当前活跃案例
- 历史记录入口
- 审批提示

第一版如果宿主空间很小，这一块甚至可以先只做一个“查看最近案例”入口。

## 返回字段优先级

如果外壳只想先吃最少字段，建议按这个优先级来：

### P0：必须接

- `action`
- `message`
- `workspace.workspace_id`
- `workspace.active_case_id`
- `case.case_id`
- `case.stage`
- `case.workflow_state`
- `rendered_card`

### P1：强烈建议接

- `rendered_history`
- `runtime_session.runtime_status`
- `runtime_session.pending_approvals`
- `project_profile`

### P2：后面再接也可以

- `runtime_session.execution_ledger`
- `runtime_session.event_log`
- `case.metadata`
- `workspace.metadata`

## 第一版消息呈现建议

### 情况 1：返回了 `rendered_card`

最稳的展示方式：

- 把 `message` 当成系统说明
- 把 `rendered_card` 当成主响应

### 情况 2：返回了 `rendered_history`

适合：

- 用户明确要看历史
- 外壳提供“展开历史”入口

### 情况 3：只有 `message`，没有主卡片

一般表示：

- 当前只是记录背景
- 或者这轮更像系统确认动作

这时第一版可以直接显示 `message`，不必强行补一张卡。

## 第一版不建议做的事

### 1. 外壳自己判断触发意图

不建议。

比如不要在外壳写死：

- 看到“背景”就一定走项目背景更新
- 看到“历史”就一定不进主线

原因：

- 很容易和内核的入口分流冲突
- 也会让后续规则调整变得更难维护

### 2. 外壳自己管理阶段推进

不建议。

比如不要自己决定：

- 现在应该进入问题定义
- 现在应该弹决策关口
- 现在应该跳过前置收敛

这些都应该继续由内核处理。

### 3. 把用户每一轮输入都当成新任务

不建议。

原因：

- 会直接失去 `workspace` 和活跃案例承接能力
- 最后体验会退化成普通问答

## 最小交互流程

### 流程 1：正常分析

1. 用户发一条草稿
2. skill 调 `POST /workspaces/{workspace_id}/messages`
3. 展示 `message + rendered_card`
4. 用户继续补一句
5. skill 继续发回同一个 `workspace_id`

### 流程 2：切案例

1. 用户点开最近案例列表，或输入“切到上一个案例”
2. skill 读取 `GET /workspaces/{workspace_id}/cases`
3. 用户选中目标案例
4. skill 调 `POST /workspaces/{workspace_id}/active-case`
5. 主区刷新为新案例的 `rendered_card`

### 流程 3：审批处理

1. 外壳发现当前工作区有待确认操作
2. 展示一条轻提示
3. 用户选择批准、拒绝或稍后处理
4. 外壳调对应审批接口
5. 再刷新当前卡片或状态

## 一条最小宿主策略

如果你只给 skill / IDE 外壳定一条规则，最稳的是这条：

`宿主负责把话送进去，把卡片拿出来，不负责重新定义主线。`

## 和其他文档的关系

- 如果你还没决定从哪个入口开始，先看 [getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)
- 如果你想看不同外壳的整体接法，先看 [integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)
- 如果你想看网页壳怎么拆，继续看 [web-shell-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-shell-minimal-contract.md)
- 如果你想看阻塞和审批该怎么提示，继续看 [approval-blocking-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/approval-blocking-contract.md)
- 如果你想看统一入口运行时本身，继续看 [agent-shell-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-shell-runtime.md)
