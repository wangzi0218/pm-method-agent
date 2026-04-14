# 最小前端 Demo 信息架构

这份文档只回答一个问题：

`如果现在要做一个最小网页 demo，页面结构和交互优先级应该怎么排。`

它不是视觉设计稿，也不是正式前端技术方案。

它更像一份收口文档，用来避免第一版网页 demo 做成：

- 页面太多
- 状态太散
- 交互太重
- 一开始就试图覆盖所有运行时能力

如果你还没先明确这版网页 demo 到底该承接什么、暂时不该承接什么，建议先看：

- [web-demo-boundaries.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-boundaries.md)

## 一句话建议

第一版网页 demo 不要做成“完整平台”。

更稳的目标是：

- 只有一个主工作区页面
- 一个可选历史抽屉
- 一个可选审批抽屉
- 先把“发消息 -> 看卡片 -> 继续补充 -> 切案例”跑顺

## 第一版目标

第一版网页 demo 更适合验证三件事：

1. 用户能不能用自然语言顺畅触发分析
2. 主卡片输出是否足够支撑阅读和继续互动
3. 最近案例、历史记录和阻塞提示是否足够帮助用户继续推进

第一版不需要优先验证：

- 复杂筛选
- 多页面配置中心
- 完整工具市场
- 复杂审批工作台
- 花哨的结构化块渲染

## 最小页面结构

推荐只保留一个主页面：

- `/workspace/:workspaceId`

可选弹层或抽屉：

- 历史抽屉
- 审批抽屉

第一版不建议再拆：

- 独立案例详情页
- 独立项目背景配置页
- 独立运行时管理页

## 主页面三栏结构

### 左栏：工作区与最近案例

目标：

- 告诉用户“我现在在哪个工作区”
- 告诉用户“当前正在看哪个案例”
- 允许快速切回最近几个案例

建议内容：

- 工作区名称
- 当前活跃案例
- 最近案例列表
- 一个“新开分析”入口

建议优先级：

- 必须有最近案例列表
- 工作区额外配置可以后放

### 中栏：主交互区

目标：

- 承接用户输入
- 展示当前主卡片
- 让用户继续补充一句话

建议内容：

- 输入框
- 当前系统说明 `message`
- 主卡片 `rendered_card`

第一版中栏就是整个 demo 的核心。

如果中栏不能顺畅承接多轮对话，其他区做再多都没有意义。

### 右栏或底部抽屉：辅助信息

目标：

- 展示历史
- 展示待确认审批
- 展示当前状态补充信息

建议内容：

- 历史记录入口
- 待确认审批入口
- 当前阶段 / 当前状态的小标签

第一版不要求一直常驻展开。

更推荐：

- 默认收起
- 有需要时再展开

## 第一版交互优先级

### P0：必须顺

1. 发一条新消息
2. 显示分析卡
3. 继续补一句
4. 同一案例继续推进

### P1：强烈建议有

1. 查看最近案例
2. 切换活跃案例
3. 查看历史
4. 看见阻塞状态

### P2：后面再补

1. 项目背景专门编辑入口
2. 审批偏好设置
3. 结构化卡片分块渲染
4. 更细的运行时信息展示

## 第一版最小路由

更推荐只保留：

### 1. `/workspace/:workspaceId`

负责：

- 左栏最近案例
- 中栏输入与主卡片
- 辅助抽屉入口

### 2. 可选：`/workspace/:workspaceId/case/:caseId`

只有在你明确需要深链接案例时再补。

如果只是做最小 demo，不一定需要这一层。

原因：

- `active_case_id` 已经足够支撑第一版体验
- 太早上详情路由，前端状态会变复杂

## 页面级状态建议

第一版前端只建议自己维护这些状态：

- `workspaceId`
- `activeCaseId`
- `recentCases`
- `currentCase`
- `renderedCard`
- `renderedHistory`
- `pendingApprovals`
- `composerText`
- `isHistoryOpen`
- `isApprovalOpen`

不建议第一版就自己维护：

- 完整阶段状态机
- 决策关口处理树
- pre-framing 候选方向本地排序
- 审批执行账本的复杂筛选

## 页面加载顺序

第一版更推荐这样加载：

### 首屏

先拉：

- `GET /workspaces/{workspace_id}/cases`

用来渲染：

- 左栏最近案例
- 当前活跃案例高亮

### 进入主区

如果有 `active_case_id`，再拉：

- `GET /cases/{case_id}`

用来渲染：

- 当前主卡片

### 用户发消息后

调用：

- `POST /workspaces/{workspace_id}/messages`

然后直接更新：

- 左栏案例列表
- 中栏主卡片
- 当前活跃案例

### 用户打开历史

再拉：

- `GET /cases/{case_id}/history`

### 用户打开审批抽屉

再拉：

- `GET /workspaces/{workspace_id}/runtime/approvals`

## 最小空状态设计

### 空工作区

建议显示：

- 一句说明：这里可以直接输入一个需求草稿
- 一个示例输入
- 一个主输入框

不要在空状态里堆太多帮助文案。

### 无历史

建议显示：

- “当前案例还没有历史记录”

### 无待审批

建议显示：

- “当前没有待确认操作”

## 第一版最小提示系统

网页 demo 第一版建议只保留三类提示：

### 1. 主线阻塞提示

来源：

- `rendered_card`
- `case.workflow_state == blocked`

表现：

- 继续展示主卡
- 给一个小标签说明“当前需要补信息 / 做选择”

### 2. 规则阻塞提示

来源：

- `action == policy-blocked`

表现：

- 单独提示，不覆盖主卡正文

### 3. 审批待处理提示

来源：

- `pending_approvals`

表现：

- 右上角小提示或抽屉入口

## 第一版不建议做的交互

### 1. 一上来就支持多工作区复杂切换

不建议。

先把单工作区体验跑顺更重要。

### 2. 一上来就支持所有卡片结构化渲染

不建议。

先用 `rendered_card` 更稳。

### 3. 审批和历史都做成独立页面

不建议。

抽屉就够了。

### 4. 把项目背景编辑做成一个重表单

不建议。

第一版更适合继续通过自然语言补背景。

## 一个最小用户路径

第一版网页 demo 最值得验证的用户路径应该是：

1. 用户打开工作区
2. 在中栏输入一条真实草稿
3. 系统返回主卡片
4. 用户继续补一句
5. 左栏出现最近案例
6. 用户切到另一个案例再切回来
7. 用户打开历史抽屉查看之前的推进记录

只要这条路径顺了，第一版 demo 就已经站住了。

## 和其他文档的关系

- 如果你还没决定从哪个入口开始，先看 [getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)
- 如果你想看整体接法，先看 [integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)
- 如果你想看网页壳字段契约，先看 [web-shell-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-shell-minimal-contract.md)
- 如果你想看阻塞和审批提示，继续看 [approval-blocking-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/approval-blocking-contract.md)

## 当前最稳的 demo 目标

如果你只给第一版网页 demo 定一个目标，就定这个：

`让用户在一个页面里，把真实草稿顺畅推进两到三轮。`
