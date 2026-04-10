# 本地命令执行壳设计

## 目标

这一层不是为了把项目变成通用终端。

它的目标更具体：

- 给 hook enforcement 一个真实的执行入口
- 给命令级策略和写入范围策略一个可验证的落点
- 让 CLI、HTTP 和未来网页壳都能复用同一套本地执行链路

## 当前实现

当前仓库已经补上：

- `src/pm_method_agent/command_executor.py`

并且已经把公共运行时链路抽到：

- `src/pm_method_agent/tool_runtime.py`

核心对象：

- `LocalCommandExecutor`

当前返回：

- `CommandExecutionResult`

## 当前执行链路

当前一条本地命令会按这个顺序执行：

1. 恢复或创建 `runtime session`
2. 记录当前 query
3. 执行 `pre-operation` hook
4. 如果 hook 放行，再请求工具调用
5. 本地执行命令
6. 把结果写回执行账本和终止语义

也就是说，现在命令执行已经走的是：

- runtime session
- hook enforcement
- execution ledger
- terminal semantics

而不只是单独的 `subprocess.run(...)`

更准确地说：

- `tool runtime` 是底座
- `local-command` 是其中一个具体 handler

当前仓库还已经补上其他 handler：

- `local-text-file-read`
- `local-text-file-write`

## 当前结果语义

当前已经区分这些结果：

- `command-executed`
- `command-blocked`
- `command-failed`
- `command-timeout`

这让外部入口可以明确区分：

- 命令没被允许执行
- 命令执行了，但业务上失败
- 命令执行超时

## 当前入口

### CLI

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli command \
  --format json \
  --workspace-id demo \
  -- python3 -c "print('hello')"
```

### HTTP

```http
POST /runtime/commands/execute
```

示例请求体：

```json
{
  "workspace_id": "demo",
  "command_args": ["python3", "-c", "print('hello')"],
  "write_paths": ["src/pm_method_agent/runtime_policy.py"],
  "timeout_seconds": 15
}
```

## 当前边界

当前这一层还是最小版。

它现在还没有：

- 目录级命令模板
- 命令输出流式事件
- 更细的环境变量控制
- 多步命令事务
- 真正的外部工具插件化

## 下一步

这层后续更适合继续补：

1. 让 HTTP 和未来网页壳可直接消费命令执行状态
2. 给命令执行补流式事件和更细的 stdout/stderr 截断策略
3. 把命令执行器和更通用的工具执行器统一到同一层
4. 补更明确的命令模板与目录级执行约束
