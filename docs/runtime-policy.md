# Runtime Policy 设计

## 目标

规则加载器解决的是：

- 系统能不能看见规则

`runtime policy` 解决的是：

- 系统会不会真的按规则执行

如果只有规则加载，没有 runtime policy，系统仍然只能把规则塞进 prompt，让模型“尽量理解”。

这还不够稳。

## 一句话定义

`runtime policy` 是规则系统里的硬约束层。

它负责把一部分可判定、可执行的规则，从“说明”变成“真正的运行时拦截或放行”。

## 当前实现

当前仓库已经补上：

- `src/pm_method_agent/runtime_policy.py`

并已经接入：

- `src/pm_method_agent/agent_shell.py`

这意味着第一版已经能做最小硬约束执行。

## 当前支持的策略

当前第一版支持这些字段：

- `blocked_intents`
- `blocked_actions`
- `approval_required_actions`
- `allow_new_cases`
- `allow_case_switching`
- `allow_project_profile_updates`

这些字段通过：

- `.pmma/policy.json`

进入运行时。

## 当前生效方式

当前 agent shell 在识别出用户意图后，会先经过 runtime policy 检查。

除此之外，当前关键执行步骤在真正落到内部动作前，也会再经过一层动作级检查。

如果命中硬规则：

- 不继续执行主线动作
- 返回一张简短的“规则阻塞卡”
- 把终止语义写入 runtime session
- 把被拦下来的内部动作写回执行账本，保证账本闭环

当前已经能区分两类典型结果：

- `blocked`
- `cancelled`

当前动作级策略已经开始生效的典型位置包括：

- `session-service.create-case`
- `session-service.reply-to-case`
- `project-profile-service.update-or-create`
- `renderer.case-state`

## 示例

例如：

```json
{
  "runtime_policy": {
    "blocked_intents": ["switch-case"],
    "blocked_actions": ["session-service.create-case"],
    "approval_required_actions": ["project-profile-service.*"],
    "allow_new_cases": false,
    "allow_project_profile_updates": false
  }
}
```

这表示：

- 不允许切换案例
- 不允许直接执行 `session-service.create-case`
- 所有 `project-profile-service.*` 动作都需要先人工确认
- 不允许直接新建案例
- 不允许直接更新项目背景

## 为什么先做这一层，而不是直接做 hook

因为 hook 适合做：

- 校验
- 阻断
- 自动触发补动作

但在真正接 hook 之前，系统必须先回答：

- 哪些规则属于硬约束
- 这些硬约束作用在哪个运行时节点
- 违反时应该是 `blocked` 还是 `cancelled`

这些问题本来就属于 runtime policy，而不是 hook 本身。

## 当前边界

第一版 runtime policy 还很小。

它当前还没有覆盖：

- 目录级命令白名单
- 强制测试策略
- 危险动作审批
- 文件路径写入限制
- sub-agent 生命周期约束

也就是说，当前已经站住了“入口级 + 内部动作级”的最小硬约束，但还没有进到更通用的工具执行和 hook enforcement。

## 和 prompt 的关系

prompt layer 负责：

- 让模型理解规则

runtime policy 负责：

- 让系统执行规则

两者不是替代关系，而是分工关系。

## 和 hook 的关系

更合理的长期结构是：

1. 规则加载器吸收规则
2. prompt layer 让模型理解规则
3. runtime policy 执行运行时硬约束
4. hook 执行可判定、可阻断、可自动化的确定性检查

## 下一步

这层后续更适合继续补：

1. 目录级运行时策略
2. 强制测试和验证纪律
3. 命令、路径和写入范围策略
4. hook enforcement 层
5. sub-agent 的父子规则传播
