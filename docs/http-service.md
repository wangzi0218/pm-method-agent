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

## 当前接口

### `GET /health`

用途：

- 检查服务是否可用
- 查看当前是否启用了 LLM 运行时

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

### `GET /workspaces/{workspace_id}/cases`

用途：

- 读取当前工作区最近案例
- 查看当前活跃案例
- 让网页或 agent 外壳快速恢复上下文

返回内容除了结构化 `cases` 外，还会附带：

- `rendered_workspace`

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
