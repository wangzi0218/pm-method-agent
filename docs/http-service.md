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

## 当前返回结构

当前服务优先返回两类内容：

- `case`
- `rendered_card` 或 `rendered_history`

这样做的原因是：

- 结构化数据方便后续不同入口消费
- 已渲染卡片方便当前快速验证和调试

后续如果需要更细粒度的前端展示，可以逐步把视图层从 `rendered_*` 下沉为更明确的数据块。

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
