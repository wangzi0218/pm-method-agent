# Operation Enforcement 设计

## 目标

`runtime policy` 定义的是规则。

`operation enforcement` 负责的是：

- 在真正执行前统一判断这些规则
- 把判断结果变成稳定的结构化输出
- 让 `agent shell`、HTTP、未来 hook 和执行器复用同一套前置校验

如果没有这一层，后续每接一个入口，就会再写一遍：

- 这里先查动作规则
- 那里再查命令规则
- 另一个地方再查读取路径
- 另一个地方再查写入路径

久了就会出现规则漂移。

## 当前实现

当前仓库已经补上：

- `src/pm_method_agent/operation_enforcement.py`

这一层当前统一承接四类检查：

- 动作级检查
- 命令级检查
- 读取路径级检查
- 写入路径级检查

## 当前输出

统一判断结果会返回：

- `allowed`
- `terminal_state`
- `reason`
- `violation_kind`
- `checks`

其中 `checks` 会保留每一步检查的结果，便于：

- 调试
- UI 展示
- hook 复用
- 后续审计

## 当前决策类型

当前统一使用这几类决策：

- `allowed`
- `blocked`
- `approval-required`

这里的重点不是文案，而是让外部系统知道：

- 可以直接继续
- 必须阻断
- 需要人工确认后再继续

## 当前接入点

这一层目前已经接到：

- `agent shell` 的内部动作执行前
- HTTP 的运行时策略校验接口

而真正的运行时挂接方式，当前已经开始通过 `hook enforcement` 承接。

对应接口：

- `GET /runtime/policy`
- `POST /runtime/policy/evaluate`

## 为什么这层要独立出来

因为后续真正接 hook 时，最容易出问题的不是“怎么执行”，而是：

- 到底该不该执行
- 命中的是哪一条规则
- 当前是阻断还是确认

这些判断应该先在 runtime 内统一，而不是散在 hook 脚本里。

## 下一步

这层后续更适合继续补：

1. 把 shell / hook / 外部执行器都接到同一个 enforcement 入口
2. 给命令和路径检查补来源信息与命中规则说明
3. 把确认型阻断升级成真正可恢复的审批流
4. 为 sub-agent 执行补父子级规则传播
