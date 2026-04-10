# 本地工具运行时设计

## 目标

如果只有一个命令执行器，后续每加一个本地工具，就会再复制一遍：

- runtime session
- hook
- execution ledger
- terminal semantics

`tool runtime` 要解决的，就是把这条公共链路抽出来。

## 当前实现

当前仓库已经补上：

- `src/pm_method_agent/tool_runtime.py`

核心对象包括：

- `LocalToolRequest`
- `LocalToolExecutionOutcome`
- `LocalToolExecutionResult`
- `LocalToolRuntime`

## 当前职责分工

### tool runtime

负责：

- 创建和恢复 `runtime session`
- 执行 `pre-operation` hook
- 记录工具调用账本
- 写入终止语义
- 输出统一的工具执行结果

### tool handler

负责：

- 真正执行某个具体本地工具
- 返回这个工具自己的执行结果

## 当前第一类 handler

当前已经落地的 handler 包括：

- `local-command`
- `local-text-file-write`

这意味着当前已经站住了“底座 + 多个具体工具”的结构，而不是只有一个特殊命令壳。

## 当前入口

当前可以通过这些入口触发：

- `pm_method_agent.cli command`
- `pm_method_agent.cli tool`
- `POST /runtime/commands/execute`
- `GET /runtime/tools`
- `POST /runtime/tools/execute`

其中：

- `/runtime/tools/execute` 更接近底座视角
- `/runtime/commands/execute` 目前保留为更直接的兼容入口

## 下一步

这层后续更适合继续补：

1. 增加更多本地工具 handler
2. 给 handler 增加目录级约束和默认模板
3. 让网页壳直接消费工具执行状态
4. 继续往更通用的 tool runtime 演进
