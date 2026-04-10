# Hook Enforcement 设计

## 目标

`operation enforcement` 负责统一判断。

`hook enforcement` 负责把这套判断真正挂到运行时生命周期里。

也就是说：

- 前者回答“该不该执行”
- 后者回答“这次检查在运行时里怎么被记录、怎么闭环”

## 当前实现

当前仓库已经补上：

- `src/pm_method_agent/hook_enforcement.py`

当前默认只注册一类内建 hook：

- `runtime-policy-enforcement`

它会在内部动作真正执行前跑一次 `pre-operation` 检查。

## 当前生命周期

当前 hook 已经有最小闭环：

- `hook-call-requested`
- `hook-call-completed`
- `hook-call-failed`

对应运行时状态对象里的：

- `pending_hooks`

以及事件日志里的：

- `event_log`

## 当前行为

如果 hook 判断允许继续：

- hook 记为完成
- 再进入真正的工具调用阶段

如果 hook 判断需要阻断或人工确认：

- hook 仍然记为已完成，因为它已经成功产出判断
- 主流程返回 `policy-blocked`
- 不再继续请求后面的工具调用

这点很重要，因为“被规则挡下”不应该伪装成“工具执行失败”。

## 当前接入点

这一层目前已经接到：

- `agent shell` 的 `_run_ledger_step`
- `LocalCommandExecutor` 的命令执行前

所以现在一个内部动作如果被规则挡下，运行时里会先出现：

- hook 请求
- hook 完成
- 终止语义输出

而不是：

- 先请求工具
- 再把工具标成失败

## 下一步

这一层后续更适合继续补：

1. 支持更多可注册的内建 hook
2. 给 hook 结果补来源信息与命中规则说明
3. 把 hook 接到更多真实工具执行器
4. 为 sub-agent 运行补父子 hook 传播
