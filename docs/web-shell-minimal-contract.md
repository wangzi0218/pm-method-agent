# 网页壳最小页面契约

这份文档只回答一个问题：

`如果要给 PM Method Agent 做一个网页壳，第一版页面应该怎么拆，分别吃哪些字段。`

它不是前端设计稿，也不讨论视觉风格。

它的目标是：

- 先把页面结构和数据边界定住
- 避免网页壳一开始就接得过重
- 让前端和方法内核之间先有一个稳定的最小契约

## 一句话建议

第一版网页壳不要急着把所有卡片都拆成细碎组件。

更稳的方式是：

1. 左侧列表先吃结构化字段
2. 中间主卡片先直接展示 `rendered_card`
3. 右侧历史区先直接展示 `rendered_history`
4. 等交互站稳后，再逐步把中间区块拆成结构化组件

## 第一版最小页面

推荐先拆成三块：

### 1. 左侧：工作区与最近案例

这里负责：

- 当前工作区
- 当前活跃案例
- 最近案例列表

推荐接口：

- `GET /workspaces/{workspace_id}/cases`

建议优先读取这些字段：

- `workspace.workspace_id`
- `workspace.active_case_id`
- `cases.active_case_id`
- `cases.recent_cases[*].case_id`
- `cases.recent_cases[*].stage`
- `cases.recent_cases[*].workflow_state`
- `cases.recent_cases[*].summary`

适合直接显示的最小信息：

- 案例编号
- 当前阶段
- 当前状态
- 一句简短判断

为什么左侧更适合先用结构化字段：

- 列表天然需要筛选和高亮
- `rendered_workspace` 更适合调试，不适合长期做正式列表

### 2. 中间：当前主卡片

这里负责：

- 当前轮的主输出
- 当前阶段标题
- 当前判断

推荐接口：

- `POST /workspaces/{workspace_id}/messages`
- `GET /cases/{case_id}`

第一版建议优先读取这些字段：

- `case.case_id`
- `case.stage`
- `case.workflow_state`
- `case.output_kind`
- `case_runtime.summary`
- `case_runtime.fallback_active`
- `case_runtime.fallback_components`
- `rendered_card`

第一版推荐直接展示：

- `rendered_card`

原因：

- 当前产品阶段更重要的是先验证方法内核和交互体验
- 不是先定义一整套前端块协议
- `rendered_card` 已经足够支撑真实试用

### 3. 右侧或底部抽屉：历史、运行态与恢复

这里负责：

- 会话历史
- 当前工作区的运行态摘要
- 阶段变更
- 已处理关口

推荐接口：

- `GET /cases/{case_id}/history`
- `GET /workspaces/{workspace_id}/runtime/session`

建议优先读取这些字段：

- `history.case_id`
- `history.stage`
- `history.workflow_state`
- `history.conversation_turns`
- `history.stage_history`
- `history.answered_questions`
- `history.resolved_gates`
- `runtime_session.runtime_status`
- `runtime_session.current_loop_state`
- `runtime_session.resume_from`
- `runtime_session.last_terminal_event`
- `runtime_session.event_log`
- `rendered_history`

第一版推荐直接展示：

- `rendered_history`

## 页面级最小状态

如果你要做网页壳，前端自己维护的状态建议先尽量少。

第一版保留这些就够：

- `workspaceId`
- `activeCaseId`
- `messageInput`
- `recentCases`
- `currentCase`
- `currentRenderedCard`
- `currentRenderedHistory`

不建议第一版就在前端自己维护：

- 完整阶段状态机
- 决策关口推进逻辑
- 前置收敛的候选方向排序

这些更适合继续由内核负责。

## 三个最小页面动作

### 动作 1：发送一条新消息

推荐接口：

- `POST /workspaces/{workspace_id}/messages`

前端最少只要做这些事：

1. 把用户输入原样发出去
2. 取回 `rendered_card`
3. 更新 `case.case_id`
4. 更新左侧最近案例

推荐优先消费的返回字段：

- `message`
- `workspace`
- `case`
- `rendered_card`

### 动作 2：切换到历史案例

推荐接口：

- `POST /workspaces/{workspace_id}/active-case`
- `GET /cases/{case_id}`

前端最少只要做这些事：

1. 切活跃案例
2. 读取该案例最新卡片
3. 更新中间区显示

### 动作 3：展开历史记录

推荐接口：

- `GET /cases/{case_id}/history`

前端最少只要做这些事：

1. 请求历史
2. 展示 `rendered_history`

## 第一版字段优先级

如果你只能先接一部分字段，建议按这个优先级来：

### P0：必须接

- `workspace.active_case_id`
- `cases.recent_cases`
- `case.case_id`
- `case.stage`
- `case.workflow_state`
- `case.output_kind`
- `rendered_card`

### P1：强烈建议接

- `rendered_history`
- `case_runtime`
- `case.context_profile`
- `case.next_actions`
- `case.decision_gates`

### P2：后面再接也可以

- `case.findings`
- `case.pre_framing_result`
- `case.metadata`
- `workspace.metadata`

## 什么时候该从 `rendered_card` 切到结构化块

推荐在下面这些条件同时满足后再切：

- 你已经确定主卡片的布局长期稳定
- 你已经确认不同 `output_kind` 的展示差异
- 你已经不只是做 demo，而是在做长期维护的网页壳

切换顺序更建议这样：

1. 左侧列表先结构化
2. 顶部阶段条和状态条再结构化
3. 主卡片正文最后再拆

不要反过来一上来就把中间主卡片完全拆掉。

另外，网页壳现在更适合直接消费 `case_runtime`，而不是自己去拆 `case.metadata`：

- `case_runtime.summary` 适合顶栏或状态条
- `case_runtime.fallback_active` 适合做轻提示
- `case_runtime.fallback_components` 适合说明这轮是回复解释、前置收敛还是文案增强回退到了本地规则

## 当前不建议的网页壳做法

### 1. 一开始就按所有 `output_kind` 分别做独立复杂组件

不建议。

原因：

- 当前还在收口真实交互
- 太早固化展示协议，后面会反复返工

### 2. 前端自己判断应该进入哪个阶段

不建议。

原因：

- 会和内核状态机冲突
- 后面规则调整时最容易失效

### 3. 左侧列表直接用 `rendered_workspace` 解析文本

不建议。

原因：

- 结构化字段已经足够做列表
- 列表比正文更适合先走稳定字段

## 一个最小响应映射示例

### `GET /workspaces/demo/cases`

更适合给左侧列表：

- `workspace.active_case_id`
- `cases.recent_cases`

### `POST /workspaces/demo/messages`

更适合给中间主区：

- `case`
- `rendered_card`
- `message`

### `GET /cases/{case_id}/history`

更适合给右侧历史区：

- `history`
- `rendered_history`

## 和其他文档的关系

- 如果你还没决定从哪个入口开始，先看 [getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)
- 如果你还没决定是做 skill、网页还是脚本，先看 [integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)
- 如果你想看阻塞和审批提示怎么拆，继续看 [approval-blocking-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/approval-blocking-contract.md)
- 如果你想看网页 demo 第一版页面和路由怎么排，继续看 [web-demo-information-architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-information-architecture.md)
- 如果你想看具体接口，再看 [http-service.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/http-service.md)

## 当前最稳的网页壳起点

如果你只记住一句实现建议，就记住这个：

`左侧先结构化，中间先渲染卡片，右侧先渲染历史。`

这样既不会把网页壳做得太重，也不会把方法内核的阶段推进绕开。
