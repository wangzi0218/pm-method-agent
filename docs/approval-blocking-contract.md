# 阻塞与审批提示契约

这份文档只回答一个问题：

`当 PM Method Agent 不能直接继续时，外壳应该怎么把这种状态正确展示给用户。`

这里最容易混淆的，是两类完全不同的“停下来”：

- 方法主线里的阻塞
- 运行时层里的阻塞或审批

如果不把这两类状态分开，用户会很难理解：

- 现在是信息还不够
- 还是权限 / 规则 / 工具动作被挡住了

## 一句话建议

第一版外壳至少要区分三种情况：

1. `分析主线阻塞`
2. `规则阻塞`
3. `运行时审批待处理`

这三种状态不要共用一套提示文案。

## 三类状态到底有什么区别

### 1. 分析主线阻塞

这是方法层的阻塞。

常见表现：

- 当前信息不够，不能继续推进
- 当前卡在决策关口，需要用户明确选择
- 当前阶段缺少关键补充

典型输出：

- `decision-gate-card`
- `stage-block-card`

这类阻塞意味着：

- 系统还在正常工作
- 只是方法判断上不能继续往下走
- 用户应该补信息、做选择、或接受暂缓

### 2. 规则阻塞

这是运行时硬约束挡下来的阻塞。

常见表现：

- 当前动作被 runtime policy 禁止
- 当前意图不允许执行
- 当前命令、读写路径或内部动作直接被规则挡住

典型返回：

- `action = policy-blocked`
- 一张“规则阻塞卡”

这类阻塞意味着：

- 不是分析本身有问题
- 是当前运行环境不允许继续执行这个动作

### 3. 运行时审批待处理

这是“不是完全禁止，但不能直接放行”的状态。

常见表现：

- 工具动作需要人工确认
- 命中审批规则，但允许后续继续
- 当前工作区里挂起了待处理操作

典型接口：

- `GET /workspaces/{workspace_id}/runtime/approvals`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/approve`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/reject`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/expire`

这类状态意味着：

- 当前不是“分析卡住”
- 而是“某个执行动作正在等人确认”

## 外壳第一版至少要看的字段

### 方法主线阻塞

优先看：

- `case.workflow_state`
- `case.output_kind`
- `case.decision_gates`
- `rendered_card`

最直接的判断方式：

- 如果 `case.workflow_state == blocked`
- 且 `case.output_kind` 是 `decision-gate-card` 或 `stage-block-card`

就把它当成分析主线阻塞。

### 规则阻塞

优先看：

- `action`
- `message`
- `rendered_card`
- `runtime_session.last_terminal_event.terminal_state`

最直接的判断方式：

- 如果 `action == policy-blocked`

就把它当成规则阻塞。

### 审批待处理

优先看：

- `runtime_session.pending_approvals`
- `runtime_session.runtime_status`
- `runtime_session.last_terminal_event`

如果外壳单独拉审批列表，再看：

- `pending_approvals[*].approval_id`
- `pending_approvals[*].tool_name`
- `pending_approvals[*].action_name`
- `pending_approvals[*].violation.reason`

## 不同状态该怎么提示用户

### 情况 1：分析主线阻塞

推荐提示方式：

- 继续展示主卡片
- 明确说“当前还缺什么”或“需要你先选什么”

更适合的语气：

- “这一步还需要你补一项背景”
- “这一关需要先定方向，系统才能继续往下推进”

不建议写成：

- “执行失败”
- “系统错误”

因为这不是错误。

### 情况 2：规则阻塞

推荐提示方式：

- 把它和分析卡片分开显示
- 明确说“当前动作被规则挡下”

更适合的语气：

- “这一步没有被执行，因为当前运行规则不允许”
- “当前策略挡下了这个动作，分析内容本身没有丢失”

不建议写成：

- “需求分析被否决”

因为这不是方法判断，而是运行时约束。

### 情况 3：审批待处理

推荐提示方式：

- 显示一条轻提示
- 让用户选择批准、拒绝或稍后处理

更适合的语气：

- “有一个动作正在等待确认”
- “这一步需要人工确认后才能继续执行”

不建议把审批提示直接伪装成分析主卡内容。

## IDE / skill 第一版建议

### 方法主线阻塞

更推荐：

- 仍然把 `rendered_card` 当主内容展示
- 用户继续自然回复

因为对 IDE / skill 来说，这类阻塞本质上还是“继续对话的一部分”。

### 规则阻塞

更推荐：

- 在主区显示一条单独的规则提示
- 保留当前上下文，不要清空当前案例

### 审批待处理

更推荐：

- 在辅助区显示“待确认操作”
- 不要把审批内容和分析主卡揉在一起

## 网页壳第一版建议

### 左侧列表

可以正常显示最近案例，不需要因为阻塞就做特殊列表结构。

但建议加两个简单状态：

- 当前案例是否阻塞
- 当前工作区是否有待确认审批

### 中间主区

推荐优先级：

1. 先显示分析主卡
2. 再显示规则阻塞提示
3. 审批提示放到次级区域

不要反过来让审批条盖住主卡正文。

### 右侧或底部抽屉

最适合放：

- 历史记录
- 待确认操作
- 已处理审批

## 第一版最小交互动作

### 动作 1：继续回答分析阻塞

做法：

1. 用户看完阻塞卡
2. 继续补一句自然语言
3. 外壳继续调 `POST /workspaces/{workspace_id}/messages`

### 动作 2：处理待确认审批

做法：

1. 外壳先拉 `GET /workspaces/{workspace_id}/runtime/approvals`
2. 展示最少信息：`approval_id / tool_name / reason`
3. 用户选批准、拒绝或稍后处理
4. 调对应审批接口
5. 再刷新当前状态

### 动作 3：规则阻塞后给出下一步

做法：

1. 不继续重试同一动作
2. 先把阻塞原因显示出来
3. 如果有替代路径，再给轻提示

## 当前不建议的做法

### 1. 把所有“不能继续”都叫阻塞

不建议。

原因：

- 用户分不清到底该补信息，还是该处理审批

### 2. 把审批提示当成主卡正文

不建议。

原因：

- 容易污染分析体验
- 用户会误以为审批本身是分析结论

### 3. 规则阻塞后自动反复重试

不建议。

原因：

- 被 runtime policy 挡下来的动作，重复重试没有意义

## 第一版最小映射规则

如果外壳只想写最小判断逻辑，建议先按这个顺序：

1. 如果 `action == policy-blocked`，显示规则阻塞提示。
2. 否则如果 `runtime_session.pending_approvals` 不为空，显示待确认审批提示。
3. 否则如果 `case.workflow_state == blocked`，显示分析主线阻塞卡。
4. 其他情况按正常分析卡展示。

## 和其他文档的关系

- 如果你想看整体接法，先看 [integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)
- 如果你想看 IDE / skill 交互，再看 [ide-skill-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/ide-skill-minimal-contract.md)
- 如果你想看网页壳页面拆分，再看 [web-shell-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-shell-minimal-contract.md)
- 如果你想看运行时策略本身，再看 [runtime-policy.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/runtime-policy.md)
