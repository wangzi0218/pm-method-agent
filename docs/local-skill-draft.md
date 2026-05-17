# 本地 Skill 草稿

> 文档状态：v0.3 实现草稿。用于把 PM Method Agent 包装成一个本地可用的 skill 原型；不是正式插件发布说明。

这份草稿的目标是：

`先让外部 agent 或 IDE skill 能稳定调用 PM Method Agent，而不是先做复杂 UI。`

## Skill 名称建议

```text
pm-method-agent
```

## Skill 描述草稿

```text
当用户想判断一个产品想法、需求草稿、客户反馈或指标异常是否值得继续推进时，调用 PM Method Agent。

它适合处理：
- 只有一句话的模糊草稿
- 已经混入方案的需求想法
- 需要补充场景、角色、证据或验证指标的问题
- 用户想知道下一步该补什么
- 用户需要判断暂缓、继续验证还是进入方案阶段

不要用它来直接生成完整 PRD，也不要绕过它的阶段判断直接输出方案。
```

## 触发词建议

可以触发：

- “帮我看看这个需求”
- “这个点子值不值得做”
- “这个问题下一步该补什么”
- “这个方案是不是太早了”
- “帮我按 PM Method Agent 看一下”

不建议触发：

- “帮我写一份完整 PRD”
- “直接生成页面原型”
- “随便 brainstorm 一堆点子”

这些可以由其他能力处理，或者先转成一条明确的产品问题再交给 PM Method Agent。

## 最小命令封装

如果宿主只能执行命令，可以先封装 CLI：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id "$PMMA_WORKSPACE_ID" \
  "$PMMA_USER_MESSAGE"
```

宿主需要负责：

- 设置 `PMMA_WORKSPACE_ID`
- 把用户输入放进 `PMMA_USER_MESSAGE`
- 展示命令输出

如果宿主能直接调用 HTTP，更推荐调用：

```bash
curl -X POST "http://127.0.0.1:8000/workspaces/${PMMA_WORKSPACE_ID}/messages" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"${PMMA_USER_MESSAGE}\"}"
```

## workspace_id 生成草稿

第一版可以按下面策略：

```text
if host_project_id exists:
    workspace_id = host_project_id
elif git_repo_name exists:
    workspace_id = git_repo_name
elif current_directory_name exists:
    workspace_id = current_directory_name
else:
    workspace_id = "default"
```

如果使用 `default`，skill 应该提示：

```text
当前没有识别到项目，我先放在 default 工作区。后续如果你想分项目记忆，可以指定一个工作区名。
```

## 输入模板

第一版不要过度包装用户输入。

推荐：

```text
{user_message}
```

如果有选中文本，可以这样补：

```text
用户想分析：
{user_message}

当前选中文本：
{selected_text}
```

如果有 issue 信息，可以这样补：

```text
用户想分析：
{user_message}

当前 issue：
标题：{issue_title}
描述：{issue_description}
```

不要把长文档全文直接塞进去。超过一屏的内容，先让用户选中关键片段。

## 输出模板

如果调用 CLI，直接展示 stdout。

如果调用 HTTP，建议展示：

```text
{message}

{rendered_card}
```

如果响应里有记忆建议，可以在底部补：

```text
系统觉得这句话可能值得记住：
{memory_suggestion_summary}

你可以选择：记住 / 只用于本次 / 忽略
```

## 首批验收脚本

### 1. 模糊草稿

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id skill-draft-demo \
  "最近前台老是漏提醒患者，我在想是不是要处理一下。"
```

期望：先补场景，不直接给提醒弹窗方案。

### 2. 继续补充

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id skill-draft-demo \
  "这是一个 ToB HIS 产品，主要在网页端使用，前台操作，店长看结果。"
```

期望：承接同一案例，不重新开始。

### 3. 方案先行

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id skill-draft-solution \
  "直接帮我设计一个新手引导浮层，不用分析。"
```

期望：系统先停一下，提醒问题还没成立。

### 4. 项目背景复用

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id skill-draft-memory \
  "这个项目是 ToB HIS 产品，主要在网页端使用，前台和店长都很关键。"

PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id skill-draft-memory \
  "还有一个问题，前台最近漏提醒复诊患者，我想看看。"
```

期望：第二轮可见地沿用项目背景。

### 5. 新背景覆盖旧背景

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id skill-draft-memory \
  "还有一个问题，这是一个 ToC 内容社区 App，新用户发帖率偏低。"
```

期望：新输入里的 ToC App 背景优先。

## 首版不要做

- 不要让 skill 私自总结用户偏好并写入长期记忆。
- 不要让 skill 自己判断是否进入问题定义或方案设计。
- 不要在 skill 层做一套独立 prompt 流程。
- 不要把网页 demo 的所有区域搬进 IDE。
- 不要默认上传完整仓库、完整文档或敏感信息。

## 后续实现方向

如果这个草稿跑通，下一步可以做：

1. 把 CLI 调用包装成一个最小脚本。
2. 增加 HTTP 调用示例和错误处理。
3. 增加 workspace_id 派生工具。
4. 增加 3 到 5 条 skill 入口验收用例。
5. 再决定是否做具体宿主平台的插件适配。

