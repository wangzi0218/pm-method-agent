# HTTP 服务层设计

## 目标

当前项目的长期形态应当优先表现为 `skill / agent`，而不是要求用户直接操作命令行或直接调用内部模块。

为了支撑这种上层形态，需要先补一层稳定、可复用的本地服务入口。

这一层当前优先选择 `HTTP`，不是因为网页优先，而是因为它最适合作为：

- CLI 与后续入口共用的统一调用层
- 本地 agent / skill 的底层服务
- 未来网页、托管服务和 MCP 适配层的基础运行时

## 为什么当前先选 HTTP

现阶段先做 HTTP，有几个实际好处：

- 调试成本低
- 不依赖特定 AI 宿主
- 最容易被网页、脚本、IDE 插件和本地 agent 复用
- 后续接 MCP 时，不需要重写方法内核

换句话说，HTTP 在这里是“底座”，不是最终用户心智。

## 当前实现范围

当前仓库已经补上最小本地 HTTP 服务：

- `src/pm_method_agent/http_service.py`
- `pm-method-agent serve`

默认监听：

- `127.0.0.1:8000`

它直接复用现有：

- `session_service`
- `renderers`
- `reply_interpreter`
- `llm_adapter`

也就是说，HTTP 服务不是新的分析器，而是对现有运行时的一层统一暴露。

当前还顺手挂上了一个最小网页 demo：

- `GET /`
- `GET /demo`

这两个入口默认返回同一个本地网页壳，适合直接在浏览器里体验：

- 发消息
- 看主卡片
- 继续补充
- 切换最近案例
- 查看历史和待处理审批

## 最小开始方式

如果你只是想确认这一层怎么接，不需要先把所有接口都看完。

更推荐按下面三步直接跑：

### 1. 启动服务

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli serve
```

### 2. 发第一条消息

如果你更想直接用网页，而不是先发 `curl`，这时可以直接打开：

```text
http://127.0.0.1:8000/
```

网页 demo 和下面这些接口共用同一个服务层，不会额外维护第二套状态。

如果你只是想先快速装一组可切换的演示案例，也可以直接调用：

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/demo-seed \
  -H "Content-Type: application/json" \
  -d '{
    "theme": "医疗",
    "scenario_count": 3
  }'
```

这条接口会优先尝试用当前配置的 OpenAI-compatible 模型生成中文示例草稿；如果模型不可用，会自动回退到内置样本。

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。"
  }'
```

### 3. 再补一条背景

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "这是一个 ToB 的 HIS 产品，主要通过网页端使用，前台在操作，店长会看结果。"
  }'
```

如果你只想先知道“我该从哪个入口开始”，建议先看：

- [getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)

如果你已经确定要做 IDE、skill、网页或脚本接入，建议继续看：

- [integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)

## 当前接口

### `GET /`

用途：

- 返回最小网页 demo
- 作为本地浏览器入口，直接承接当前工作区体验

### `GET /demo`

用途：

- 返回与 `/` 相同的网页 demo
- 给后续可能的入口路由预留一个更明确的别名

### `GET /assets/web-demo.css`

用途：

- 返回网页 demo 的静态样式

### `GET /assets/web-demo.js`

用途：

- 返回网页 demo 的前端逻辑
- 负责消息发送、案例切换、历史和审批展示

### `POST /workspaces/{workspace_id}/demo-seed`

用途：

- 为当前工作区一键装载一组演示案例
- 优先使用当前配置的模型服务生成中文示例草稿
- 如果模型不可用，自动回退到内置样本
- 让网页 demo 可以直接展示最近案例、主卡片、历史和运行时摘要

示例请求体：

```json
{
  "theme": "医疗",
  "scenario_count": 3
}
```

### `GET /health`

用途：

- 检查服务是否可用
- 查看当前是否启用了 LLM 运行时

### `GET /runtime/policy`

用途：

- 读取当前运行时策略的有效值
- 给网页壳、调试工具或本地 agent 展示当前硬约束

### `POST /runtime/policy/evaluate`

用途：

- 在真正执行前，统一评估动作、命令、读取路径和写入路径是否允许继续
- 给未来 hook、网页壳或本地执行器复用同一套前置校验结果

示例请求体：

```json
{
  "action_name": "project-profile-service.update-or-create",
  "command_args": ["git", "status"],
  "read_paths": ["docs/internal/runtime-policy.md"],
  "write_paths": ["src/pm_method_agent/runtime_policy.py"]
}
```

### `POST /runtime/commands/execute`

用途：

- 通过统一执行壳运行本地命令
- 在真正执行前先经过 hook 与运行时策略校验
- 给 CLI、网页壳或未来本地 agent 提供一致的命令执行底座

示例请求体：

```json
{
  "workspace_id": "demo",
  "command_args": ["python3", "-c", "print('hello')"],
  "write_paths": ["src/pm_method_agent/runtime_policy.py"],
  "timeout_seconds": 15
}
```

### `GET /workspaces/{workspace_id}/runtime/approvals`

用途：

- 查看当前工作区待确认的运行时操作
- 让网页壳或本地 agent 在“阻断后”知道下一步该怎么继续

### `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/approve`

用途：

- 批准一条待确认操作
- 按原请求继续执行对应工具
- 保持 runtime session、事件日志和执行账本闭环

### `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/reject`

用途：

- 显式拒绝一条待确认操作
- 让这条审批退出待处理队列
- 把拒绝状态写入审批账本

### `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/expire`

用途：

- 显式把一条待确认操作标记为过期
- 让网页壳或平台侧可以清理长期未处理项
- 保留“已经过期”的正式状态，而不是直接丢失记录

### `POST /cases`

用途：

- 创建一个新案例

示例请求体：

```json
{
  "input": "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
  "mode": "auto",
  "context_profile": {
    "business_model": "tob",
    "primary_platform": "mobile-web",
    "target_user_roles": ["前台", "诊所管理者"]
  }
}
```

### `GET /cases/{case_id}`

用途：

- 获取当前案例状态与最新卡片

### `POST /cases/{case_id}/reply`

用途：

- 在已有案例上补充自然语言回答并继续推进

示例请求体：

```json
{
  "reply": "现在前台是手动翻表提醒，最近两周漏了 6 次。",
  "context_profile_updates": {
    "product_domain": "医疗服务平台"
  }
}
```

### `GET /cases/{case_id}/history`

用途：

- 获取会话历史、阶段变更和已处理关口

### `POST /project-profiles`

用途：

- 创建项目背景

### `GET /project-profiles/{project_profile_id}`

用途：

- 读取项目背景

### `POST /project-profiles/{project_profile_id}`

用途：

- 更新项目背景

### `GET /workspaces/{workspace_id}`

用途：

- 读取当前工作区状态
- 读取当前工作区审批偏好
- 读取当前工作区的最小记忆层摘要

### `GET /workspaces/{workspace_id}/approval-preferences`

用途：

- 读取当前工作区审批偏好
- 查看哪些动作会在这个工作区被自动批准

### `POST /workspaces/{workspace_id}/approval-preferences`

用途：

- 更新当前工作区审批偏好
- 当前第一版主要支持 `auto_approve_actions`

### `GET /workspaces/{workspace_id}/user-profile`

用途：

- 读取当前工作区记录下来的最小用户偏好
- 查看系统已经记住了哪些长期交互习惯

### `POST /workspaces/{workspace_id}/user-profile`

用途：

- 更新当前工作区的最小用户偏好
- 当前支持的典型字段包括：
  - `preferred_output_style`
  - `preferred_language`
  - `decision_style`
  - `frequent_product_domains`
  - `common_constraints`

### `GET /workspaces/{workspace_id}/cases`

用途：

- 读取当前工作区最近案例
- 查看当前活跃案例
- 让网页或 agent 外壳快速恢复上下文

返回内容除了结构化 `cases` 外，还会附带：

- `rendered_workspace`
- `user_profile`

其中 `cases` 内部也会带一层当前工作区的记忆摘要，包括：

- `project_profile`
- `user_profile`
- `workspace_memory`

### `POST /workspaces/{workspace_id}/active-case`

用途：

- 显式切换当前活跃案例

示例请求体：

```json
{
  "case_id": "case-xxxxxx"
}
```

### `POST /workspaces/{workspace_id}/messages`

用途：

- 通过工作区上下文驱动统一 agent 入口

### `POST /agent/messages`

用途：

- 不显式操作 case id，直接以统一入口发送一条用户消息
- 适合先验证统一入口，再决定是否自己维护 workspace

## 当前返回结构

当前服务优先返回两类内容：

- `case`
- `rendered_card` 或 `rendered_history`

对于 agent 入口，还会返回：

- `action`
- `workspace`
- `project_profile`
- `message`

对于案例相关接口，现在还会返回：

- `case_runtime`

这层字段的目标，是把 `LLM` 增强状态、回退组件和运行摘要收成一份稳定契约，给网页、IDE 外壳或其他客户端直接消费，而不是让它们自己去拆 `case.metadata`。

对于运行时策略校验接口，还会返回：

- `decision`
- `runtime_policy`

对于本地命令执行接口，还会返回：

- `result`

对于通用本地工具接口，还会返回：

- `tool_name`
- `result`

这样做的原因是：

- 结构化数据方便后续不同入口消费
- 已渲染卡片方便当前快速验证和调试

后续如果需要更细粒度的前端展示，可以逐步把视图层从 `rendered_*` 下沉为更明确的数据块。

当前 `action` 已覆盖的主要类型包括：

- `create-case`
- `reply-case`
- `project-profile-updated`
- `show-guidance`
- `show-history`
- `show-workspace`
- `switch-case`
- `policy-blocked`

## 当前本地工具接口

### `GET /runtime/tools`

用途：

- 查看当前已经暴露的工具

当前第一版已暴露：

- `local-command`
- `local-directory-list`
- `local-text-file-read`
- `local-text-search`
- `local-text-file-write`
- `platform-workspace-overview`
- `platform-case-read`
- `platform-project-profile-read`
- `platform-project-profile-upsert`

返回内容除了工具名和说明，还会带上：

- `execution_scope`
- `input_schema`
- `supports_read_paths`
- `supports_write_paths`
- `supports_command_args`
- `default_timeout_seconds`

这样不同外壳就不用再自己猜每个工具该怎么调用。
同时也能开始区分：

- 哪些工具要走本地环境
- 哪些工具直接读取平台状态
- 哪些平台工具会改写平台内状态

### `GET /runtime/tools/{tool_name}`

用途：

- 查看单个本地工具的完整元数据
- 给 CLI、网页或 agent 壳做按需发现

### `POST /runtime/tools/execute`

用途：

- 通过通用工具入口执行一个工具
- 当前第一版已支持本地工具和平台工具两类执行面

## 当前推荐接入方式

如果你是在做不同形态的外壳，当前建议这样用：

### CLI 或脚本

- 直接调用 `pm_method_agent.cli`
- 或直接走本地 HTTP

### IDE agent / skill

- 优先使用 `POST /workspaces/{workspace_id}/messages`
- 需要展示最近案例时，补 `GET /workspaces/{workspace_id}/cases`
- 需要显式切换上下文时，补 `POST /workspaces/{workspace_id}/active-case`

### 网页

- 可以直接复用工作区接口和案例接口
- 当前先消费 `rendered_*` 也没问题
- 后续再逐步切换到结构化块渲染

## 和 MCP 的关系

HTTP 不是对 MCP 的替代，而是 MCP 的基础层之一。

更合理的长期结构是：

1. 方法内核
2. 会话服务层
3. HTTP 服务
4. MCP 适配层
5. skill / agent / 网页入口

也就是说：

- 现在先做 HTTP
- 后续再补 MCP
- 用户最终更可能感知到的是 skill / agent，而不是 HTTP 本身

## 当前边界

这一版 HTTP 服务仍然是本地开发与集成验证入口。

它当前不负责：

- 鉴权
- 多租户
- 线上部署策略
- 限流
- 持久化数据库

这些能力应当等到真正进入托管服务阶段后再补。

## 一个最小串联示例

1. 先发第一条消息：

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。"
  }'
```

2. 再补项目背景：

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "这是一个 ToB 的 HIS 产品，主要通过网页端使用，前台在操作，店长会看结果。"
  }'
```

3. 查看最近案例：

```bash
curl http://127.0.0.1:8000/workspaces/demo/cases
```
