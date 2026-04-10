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
- `local-directory-list`
- `local-text-file-read`
- `local-text-search`
- `local-text-file-write`
- `platform-workspace-overview`
- `platform-case-read`
- `platform-project-profile-read`
- `platform-project-profile-upsert`

这意味着当前已经站住了“底座 + 多个具体工具”的结构，而不是只有一个特殊命令壳。

同时，工具注册层已经开始暴露稳定元数据，包括：

- 工具类型
- 工具说明
- 执行范围
- 输入参数契约
- 是否支持读取路径声明
- 是否支持命令参数
- 是否支持写入路径声明
- 默认超时

当前这层已经不只区分“哪个工具”，也开始区分：

- `local`
- `platform`

也就是：

- 本地工具负责接用户环境
- 平台工具负责接工作区、案例、项目背景这类平台内状态

当前平台工具也已经接进统一 runtime：

- 会写入 runtime session
- 会经过 pre-operation hook
- 会留下执行账本
- 可被动作级策略直接阻断

对于“需要人工确认”的动作，当前也已经有最小闭环：

- 被拦下时，不只返回阻断结果
- runtime session 会额外挂起一条 `pending_approvals`
- 同时会写入 `approval_ledger`
- 返回体里会带上 `pending_approval`
- 后续可以按 `approval_id` 批准并继续执行原请求
- 也可以显式拒绝或标记过期
- 对已经处理过的审批再次操作时，会返回明确语义，而不是只报“找不到”

当前审批默认处理规则也已经开始分层：

- 项目级 runtime policy 可以定义自动批准、自动过期和必须人工处理
- workspace 可以补自己的自动批准偏好
- runtime 会在真正挂起前，统一裁决这条审批该进入哪条路径

另外，当前事件日志、工具调用和 hook 调用的编号，已经改成由 `runtime_metadata` 中的单调计数器统一分配，而不是按当前列表长度临时生成。

这样做是为了避免：

- 日志截断后事件编号重复
- 账本截断后工具调用编号重复
- hook 完成后再次请求时编号回退

## 当前入口

当前可以通过这些入口触发：

- `pm_method_agent.cli command`
- `pm_method_agent.cli tool`
- `pm_method_agent.cli approvals`
- `pm_method_agent.cli approve`
- `pm_method_agent.cli reject`
- `pm_method_agent.cli expire`
- `POST /runtime/commands/execute`
- `GET /runtime/tools`
- `GET /runtime/tools/{tool_name}`
- `POST /runtime/tools/execute`
- `GET /workspaces/{workspace_id}/runtime/approvals`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/approve`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/reject`
- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/expire`

其中：

- `/runtime/tools/execute` 更接近底座视角
- `/runtime/commands/execute` 目前保留为更直接的兼容入口
- `/runtime/tools` 和 `/runtime/tools/{tool_name}` 更适合做工具发现和外壳接入

当前 `local-text-file-read` 和 `local-text-file-write` 都已经把路径声明接进了 pre-operation hook：

- 目录枚举工具会带上 `read_paths`
- 读工具会带上 `read_paths`
- 写工具会带上 `write_paths`

所以运行时现在能区分：

- 这个工具能不能执行
- 这个动作本身是不是允许
- 它要读哪个路径
- 它要写哪个路径

## 下一步

这层后续更适合继续补：

1. 给更多工具补上只读 / 只写 / 命令之外的能力分类
2. 给 handler 增加更细的读取策略和目录模板
3. 让网页壳直接消费工具执行状态
4. 继续往更通用的 tool runtime 演进
