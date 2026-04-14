# 对外接入示例

这份文档面向两类人：

- 想把 `PM Method Agent` 接进 IDE、skill、网页或内部服务的人
- 已经知道项目定位，但还不确定应该调哪些接口的人

它不讨论内部实现细节，只关心：

`不同外壳应该怎么接，才能少走弯路。`

如果你准备做网页 demo，建议先看：

- [web-demo-boundaries.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-boundaries.md)

先把边界定住，再看接口和页面拆分，会更稳。

## 一句话建议

当前最推荐的接法不是“每个外壳都自己拼状态”，而是：

- 外壳只负责触发、展示和少量宿主适配
- `PM Method Agent` 自己负责工作区、案例、阶段推进和卡片输出

也就是：

- 能走 `POST /workspaces/{workspace_id}/messages`
- 就尽量不要自己手动编排 `POST /cases` 和 `POST /cases/{case_id}/reply`

## 先记住三类接法

### 1. IDE / skill / agent 外壳

推荐接口：

- `POST /workspaces/{workspace_id}/messages`
- `GET /workspaces/{workspace_id}/cases`
- `POST /workspaces/{workspace_id}/active-case`

为什么：

- 这类入口最像“持续对话”
- 更适合直接承接工作区和活跃案例
- 不需要外层自己维护 case id 的推进逻辑

### 2. 网页壳

推荐接口：

- `POST /workspaces/{workspace_id}/messages`
- `GET /workspaces/{workspace_id}/cases`
- `GET /cases/{case_id}`
- `GET /cases/{case_id}/history`

为什么：

- 网页通常需要列表页、详情页和历史记录
- 工作区接口更适合左侧最近案例
- 案例接口更适合详情区和刷新

补一句边界提醒：

- 第一版网页壳更适合做本地轻入口，不建议一上来就做成完整托管平台

### 3. 服务端 / 脚本 / 自动化任务

推荐接口：

- `POST /cases`
- `POST /cases/{case_id}/reply`
- `GET /cases/{case_id}`

为什么：

- 这类入口往往不需要完整工作区体验
- 更适合显式控制“创建案例 -> 补一轮信息 -> 取结果”

## IDE / skill 最小接法

这类入口最常见的目标，是把它做成一个“用户写一句草稿，就开始帮忙推进分析”的能力。

最小流程通常只要三步。

### 第一步：发送用户当前输入

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。"
  }'
```

外壳建议优先读取这些字段：

- `message`
- `rendered_card`
- `workspace`
- `case`

如果你只是先做一个可用外壳，这一轮直接展示 `rendered_card` 就够了。

### 第二步：继续补充一轮自然语言

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "这是一个 ToB 的 HIS 产品，主要通过网页端使用，前台在操作，店长会看结果。"
  }'
```

这一层不要自己猜“现在该补场景还是该补目标”。

更稳的做法是：

- 让用户继续自然说话
- 把原话直接交给 `workspaces/messages`
- 用返回的 `rendered_card` 和 `case.stage` 决定展示

### 第三步：需要恢复上下文时，拉最近案例

```bash
curl http://127.0.0.1:8000/workspaces/demo/cases
```

适合用在：

- IDE 重启后恢复
- skill 面板显示最近案例
- 用户主动切换另一个需求

## 网页壳最小接法

网页壳最容易犯的错误，是一开始就强依赖结构化块，把展示做得很重。

当前更推荐分两步走。

### 第一步：先直接消费 `rendered_*`

适合场景：

- 内部演示
- 早期验证
- 还没决定最终 UI 结构

最常用字段：

- `rendered_card`
- `rendered_history`
- `rendered_workspace`

优点：

- 接得快
- 不用自己先定义卡片渲染协议
- 更适合现在这个阶段的产品验证

### 第二步：再逐步切到结构化字段

适合场景：

- 你已经确定要做固定布局
- 需要把不同模块拆成多个独立 UI 区块
- 需要做筛选、排序或更细的状态提示

这时更应该重点用：

- `case.stage`
- `case.workflow_state`
- `case.output_kind`
- `case.context_profile`
- `case.findings`
- `case.decision_gates`
- `workspace.recent_case_ids`

建议做法不是“一次性完全抛弃 `rendered_*`”，而是：

- 先让左侧列表用结构化字段
- 右侧主卡片继续显示 `rendered_card`
- 再按需要逐块替换

## 什么时候该用 `rendered_*`

更适合直接用 `rendered_*` 的情况：

- 你想先快速做出一个可用 demo
- 你只需要把当前卡片展示出来
- 你还没打算设计稳定的前端块结构
- 你主要在验证分析质量，不是在验证 UI 编排

## 什么时候该用结构化字段

更适合直接用结构化字段的情况：

- 你要做列表筛选和聚合
- 你要高亮当前阶段、阻塞状态或决策关口
- 你要把“基础信息 / 关键判断 / 关口 / 建议动作”拆成多个组件
- 你要做二次加工，而不是原样展示卡片

## 一个网页壳的最小页面拆分

如果你要做网页壳，当前最稳的拆法可以很轻：

### 左侧

- 当前工作区
- 最近案例
- 当前活跃案例

推荐接口：

- `GET /workspaces/{workspace_id}/cases`

### 中间主区

- 当前卡片
- 当前阶段
- 当前判断

推荐接口：

- `POST /workspaces/{workspace_id}/messages`
- `GET /cases/{case_id}`

### 右侧或底部抽屉

- 历史记录
- 已回答问题
- 阶段推进记录

推荐接口：

- `GET /cases/{case_id}/history`

## 一个 skill 外壳的最小展示逻辑

如果你是做 skill，而不是完整网页，建议先保持简单：

### 用户输入一条消息后

- 直接调 `POST /workspaces/{workspace_id}/messages`
- 把返回的 `rendered_card` 展示出来
- 把 `message` 当成系统提示或说明文案

### 用户继续回复时

- 继续把自然语言原话发回同一个 `workspace_id`
- 不要让 skill 自己决定“这是补场景还是补目标”

### 用户想切回之前案例时

- 调 `GET /workspaces/{workspace_id}/cases`
- 让用户选一个案例
- 再调 `POST /workspaces/{workspace_id}/active-case`

## 一个服务端脚本的最小串联

如果你不是做交互入口，而是做自动化脚本或批处理，更适合直接操作案例。

### 1. 创建案例

```bash
curl -X POST http://127.0.0.1:8000/cases \
  -H "Content-Type: application/json" \
  -d '{
    "input": "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
    "mode": "auto",
    "context_profile": {
      "business_model": "tob",
      "primary_platform": "mobile-web",
      "target_user_roles": ["前台", "诊所管理者"]
    }
  }'
```

### 2. 拿到 `case_id` 后继续补充

```bash
curl -X POST http://127.0.0.1:8000/cases/case-xxxxxx/reply \
  -H "Content-Type: application/json" \
  -d '{
    "reply": "现在主要靠前台手工翻表提醒，最近两周漏了 6 次。"
  }'
```

### 3. 读取最终结果

```bash
curl http://127.0.0.1:8000/cases/case-xxxxxx
```

## 当前不建议的接法

### 1. 外层自己维护完整阶段状态机

不建议。

原因：

- 很容易和内核自己的阶段推进冲突
- 后面一旦规则调整，外壳逻辑也会一起失效

### 2. 每轮都新建一个 case

不建议。

原因：

- 会直接丢掉多轮承接能力
- 也会让真实体验退化成普通问答

### 3. 一开始就完全依赖结构化字段渲染

也不建议。

原因：

- 当前阶段更重要的是先验证方法内核和交互质量
- 不是先把外壳做得很重

## 当前最适合的接入顺序

更推荐这样推进：

1. 先用 `agent` 或 `workspaces/messages` 跑通真实草稿。
2. 再决定你是做 skill、IDE 外壳还是网页壳。
3. 先消费 `rendered_*` 做轻展示。
4. 最后再按需要拆成更细的结构化组件。

## 相关文档

- [getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)
- [http-service.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/http-service.md)
- [deployment-modes.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/deployment-modes.md)
- [agent-interaction.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-interaction.md)
- [approval-blocking-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/approval-blocking-contract.md)
- [ide-skill-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/ide-skill-minimal-contract.md)
- [web-shell-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-shell-minimal-contract.md)
- [web-demo-information-architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-information-architecture.md)
