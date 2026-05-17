# MCP 候选工具清单

> 文档状态：v0.3 设计草案。用于收敛 MCP 外壳边界；当前不代表已经实现 MCP 服务。

这份文档只回答一个问题：

`如果未来把 PM Method Agent 暴露成 MCP server，第一批 tools 应该长什么样，哪些必须加审批？`

## 基本判断

MCP 在这里不是新的产品入口，也不是新的方法内核。

它更适合做成一层 AI-native 适配：

- 让其他 agent 能调用 PM Method Agent。
- 复用已有 HTTP / session / runtime 能力。
- 暴露少量稳定工具，而不是把内部对象全部摊开。
- 对写入、切换、审批等动作保留明确边界。

一句话：

`MCP server 应该很薄，核心判断仍然留在 PM Method Agent 内核。`

## 工具分级

候选 tools 先分成四类。

| 类型 | 说明 | 默认风险 |
| --- | --- | --- |
| 只读查询 | 读取工作区、案例、历史、运行时状态 | 低 |
| 分析推进 | 发送用户消息，可能创建或推进案例 | 中 |
| 记忆写入 | 确认项目背景、用户偏好或长期约束 | 高 |
| 运行时治理 | 审批、命令、策略、恢复动作 | 高 |

`v0.3` 如果实现 MCP，建议先做只读查询和分析推进。记忆写入与运行时治理可以先保留设计，不急着开放。

## P0 候选工具

### 1. `pmma_analyze_message`

用途：

- 接收一条自然语言消息。
- 复用工作区和活跃案例。
- 返回当前卡片、案例状态和运行时摘要。

对应现有能力：

- `POST /workspaces/{workspace_id}/messages`

建议入参：

```json
{
  "workspace_id": "clinic-workbench",
  "message": "最近前台老是漏提醒患者，我在想是不是要处理一下。",
  "source": "ide-skill",
  "context_excerpt": "可选：当前选中文本或 issue 摘要"
}
```

建议返回：

```json
{
  "action": "create-case",
  "message": "已按新的输入创建分析案例。",
  "rendered_card": "...",
  "workspace_id": "clinic-workbench",
  "active_case_id": "case-xxxx",
  "case_stage": "problem-definition",
  "workflow_state": "blocked"
}
```

审批要求：

- 默认不需要审批。
- 如果入参包含需要写入长期记忆的明确动作，不能在这个 tool 里直接写入，应返回记忆建议。

### 2. `pmma_list_cases`

用途：

- 读取工作区最近案例。
- 供 IDE、agent 或 MCP client 显示“刚才那个需求”。

对应现有能力：

- `GET /workspaces/{workspace_id}/cases`

建议入参：

```json
{
  "workspace_id": "clinic-workbench",
  "limit": 10
}
```

审批要求：

- 不需要审批。

### 3. `pmma_get_case`

用途：

- 读取某个案例详情。
- 返回卡片、阶段、上下文和关键状态。

对应现有能力：

- `GET /cases/{case_id}`

建议入参：

```json
{
  "case_id": "case-xxxx"
}
```

审批要求：

- 不需要审批。

### 4. `pmma_get_case_history`

用途：

- 读取案例历史。
- 让外部 agent 理解前几轮用户补过什么。

对应现有能力：

- `GET /cases/{case_id}/history`

建议入参：

```json
{
  "case_id": "case-xxxx"
}
```

审批要求：

- 不需要审批。

## P1 候选工具

### 5. `pmma_switch_active_case`

用途：

- 切换工作区活跃案例。

对应现有能力：

- `POST /workspaces/{workspace_id}/active-case`

建议入参：

```json
{
  "workspace_id": "clinic-workbench",
  "case_id": "case-xxxx"
}
```

审批要求：

- 默认不需要审批。
- 但 MCP client 应在展示层明确告诉用户当前已切换案例，避免用户误以为还在刚才那个问题里。

### 6. `pmma_get_workspace_overview`

用途：

- 获取工作区概览。
- 包括活跃案例、最近案例、项目背景、记忆建议摘要。

对应现有能力：

- `GET /workspaces/{workspace_id}` 或现有 workspace overview 组合能力。

建议入参：

```json
{
  "workspace_id": "clinic-workbench"
}
```

审批要求：

- 不需要审批。

### 7. `pmma_get_runtime_status`

用途：

- 获取当前工作区运行时状态。
- 给外部 agent 判断是否有阻塞、审批、失败或恢复建议。

对应现有能力：

- `GET /workspaces/{workspace_id}/runtime`
- `GET /workspaces/{workspace_id}/runtime/resume-actions`
- `GET /workspaces/{workspace_id}/runtime/approvals`

建议入参：

```json
{
  "workspace_id": "clinic-workbench"
}
```

审批要求：

- 不需要审批。

## P2 候选工具

### 8. `pmma_confirm_memory_write`

用途：

- 用户明确确认后，把某条建议写入项目背景、用户偏好或长期记忆。

对应现有能力：

- 现有项目背景服务与记忆建议能力。

建议入参：

```json
{
  "workspace_id": "clinic-workbench",
  "suggestion_id": "mem-xxxx",
  "target": "project-profile"
}
```

审批要求：

- 必须确认。
- 不能由上游 agent 静默调用。
- MCP client 必须展示要写入的原文或摘要。

### 9. `pmma_update_project_profile`

用途：

- 显式更新项目背景。

对应现有能力：

- `project-profile-service.update-or-create`

建议入参：

```json
{
  "workspace_id": "clinic-workbench",
  "project_name": "诊所工作台",
  "context_profile": {
    "business_model": "tob",
    "primary_platform": "pc",
    "target_user_roles": ["前台", "店长"]
  }
}
```

审批要求：

- 建议确认。
- 如果是首次创建项目背景，可轻确认。
- 如果覆盖已有稳定背景，必须明确确认。

### 10. `pmma_approve_runtime_action`

用途：

- 批准运行时待处理动作。

对应现有能力：

- `POST /workspaces/{workspace_id}/runtime/approvals/{approval_id}/approve`

建议入参：

```json
{
  "workspace_id": "clinic-workbench",
  "approval_id": "approval-xxxx"
}
```

审批要求：

- 这个 tool 本身不能被静默自动调用。
- 必须由用户明确授权。

## 暂不建议开放的工具

### 1. 任意命令执行

不建议在第一版 MCP 中开放通用命令执行。

原因：

- 风险高。
- 容易和 MCP client 的权限模型叠加出复杂问题。
- 当前项目核心还不是执行本地命令，而是产品判断。

如果未来开放，也必须走 runtime policy、hook 和审批。

### 2. 直接写文件

不建议第一版开放。

原因：

- PM Method Agent 当前还不是 PRD 写入器。
- 直接写文件会把产品判断和文档编辑混在一起。

### 3. 自动生成完整 PRD

不建议第一版开放。

原因：

- 这会诱导用户跳过问题定义和决策挑战。
- 和当前“先判断是否值得做”的定位冲突。

## 与 HTTP 服务的关系

MCP 第一版不应该重写业务逻辑。

推荐结构：

```text
MCP tool
  -> HTTP service / session service
  -> PM Method Agent core
  -> rendered_card + structured state
```

好处：

- MCP、网页、CLI、skill 共用同一套内核。
- 后续修阶段推进和文案，不需要改多个入口。
- 权限和审批可以复用 runtime 层。

## 最小实现顺序

如果后续决定实现 MCP，建议顺序是：

1. `pmma_analyze_message`
2. `pmma_list_cases`
3. `pmma_get_case`
4. `pmma_get_case_history`
5. `pmma_get_runtime_status`
6. 再评估 `pmma_switch_active_case`
7. 最后才看记忆写入和审批工具

## 验收标准

第一版 MCP 如果做出来，应满足：

- 能从一句自然语言草稿创建或继续案例。
- 能读取最近案例和当前案例。
- 能看见当前是否阻塞、暂缓或完成。
- 不会静默写入长期记忆。
- 不会绕过 PM Method Agent 的阶段推进。
- 不开放任意命令执行和直接文件写入。

如果 MCP 只是变成“把 prompt 发给模型”的薄包装，那就没有达到目标。

