# 从哪里开始

这份文档只回答一件事：

`如果你第一次使用 PM Method Agent，应该从哪个入口开始。`

它不展开内部架构，也不要求你先理解状态机、工具运行时或规则层。

## 一句话建议

大多数人都可以按这个顺序理解：

1. 先用 `agent` 入口体验真实多轮分析。
2. 再看 `HTTP` 服务，决定要不要接进 IDE、网页或自己的工具。
3. 只有在需要调试底座时，才去看 `rules`、`tool`、`command` 这些开发者入口。

## 你该选哪个入口

### 1. 我只是想先体验它

最适合的入口：

- `CLI agent`

适合你如果：

- 你是产品经理、设计师、业务负责人
- 你想快速试一个真实需求草稿
- 你想感受系统会不会追问、会不会卡关、会不会给出像样的分析卡

最小命令：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "前台最近老是漏提醒患者，我在想是不是要处理一下。"
```

再补一条背景：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "这是一个 ToB 医疗服务平台，主要通过网页端使用，前台在操作，店长会看结果。"
```

你会看到：

- 场景补充卡
- 前置收敛卡
- 分析卡
- 决策关口卡

这是当前最接近未来真实产品体验的入口。

### 2. 我想把它接进 IDE、skill 或 AI 工具

最适合的入口：

- 本地 `HTTP` 服务

适合你如果：

- 你想把它接进自己的 agent 外壳
- 你希望 skill 或 IDE 插件通过一个稳定接口来调用它
- 你不想让外层自己去维护 case、workspace 和阶段推进

先启动服务：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli serve
```

再发一条消息：

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。"
  }'
```

这一层更适合承接：

- IDE agent
- skill / workflow
- 本地网页壳
- 外部脚本

如果你只是想先用浏览器体验，不想自己拼接口，也可以在启动服务后直接打开：

```text
http://127.0.0.1:8000/
```

这版网页 demo 已经能直接走主链路：

- 发一句真实草稿
- 看当前主卡片
- 继续补一句
- 切回最近案例

### 3. 我想看底层已经提供了哪些能力

最适合的入口：

- `rules`
- `tool`
- `command`

适合你如果：

- 你在调试规则层
- 你在验证本地工具
- 你要确认运行时策略、审批流和工具注册信息

常用命令：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli rules --base-dir . --show-prompt
```

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli tool --list
```

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli tool \
  --tool-name local-text-file-read \
  --payload-json '{"workspace_id":"demo","path":"README.md"}'
```

这组入口更偏开发验证，不是第一次体验时的推荐起点。

## 推荐体验顺序

如果你第一次接触这个项目，更推荐这样体验：

### 第一步：先试一个真实草稿

比如：

```text
最近淘宝售后相关反馈不少，但我现在没想清楚，这次到底是想提升退货发起率、降低售后投诉率，还是提升 88VIP 用户对权益兑现的感知。
```

观察两件事：

- 系统有没有先帮你收住当前最大的不确定性
- 输出读起来是不是像协作中的产品同事，而不是模板机器人

### 第二步：再试补充一轮信息

比如继续补：

```text
这轮主要还是面向 88VIP 用户，问题集中出现在退货和包运费兑现这两个场景。
```

观察两件事：

- 系统能不能承接上一轮，而不是把每轮都当新问题
- 它会不会因为补充信息而自然进入下一个阶段

### 第三步：最后再决定是否接服务层

如果你只是体验方法，不一定要立刻接 `HTTP`。

如果你已经确定想把它接进：

- IDE
- skill
- 网页壳
- 团队内部服务

这时再切到 `HTTP` 文档看接口，会更顺。

## 是否需要配置 LLM

当前不需要。

默认规则解释器已经可以跑完整主线，适合：

- 本地体验
- 回归测试
- 文档示例

如果你希望启用兼容 OpenAI 格式的模型服务，可以再补：

```bash
export PMMA_LLM_ENABLED=1
export PMMA_LLM_BASE_URL=https://api.deepseek.com
export PMMA_LLM_API_KEY=your-api-key
export PMMA_LLM_MODEL=deepseek-chat
```

但建议顺序仍然是：

1. 先确认不用模型时，主线是否已经站得住。
2. 再打开模型增强。

## 对外接入时最常看的几份文档

- [README.md](/Users/wannz/Documents/sourcetree/pm-method-agent/README.md)：项目定位、适合谁、最小例子
- [integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)：IDE / skill、网页壳和服务端脚本分别该怎么接
- [web-demo-boundaries.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-boundaries.md)：网页 demo 第一版到底负责什么，不负责什么
- [ide-skill-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/ide-skill-minimal-contract.md)：如果要做 IDE / skill 外壳，第一版交互应该怎样触发、展示和切案例
- [web-shell-minimal-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-shell-minimal-contract.md)：如果要做网页壳，第一版页面和字段该怎么拆
- [approval-blocking-contract.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/approval-blocking-contract.md)：如果用户遇到阶段阻塞、规则阻塞或审批待处理，外壳应该怎么提示
- [web-demo-information-architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-information-architecture.md)：如果要做最小网页 demo，第一版页面、路由和交互优先级该怎么排
- [http-service.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/http-service.md)：本地服务接口和最小调用示例
- [deployment-modes.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/deployment-modes.md)：CLI、IDE、网页和混合模式的关系
- [agent-interaction.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-interaction.md)：主代理如何决定下一步做什么
- [manual-smoke.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/manual-smoke.md)：想批量试用例时怎么做

## 当前最推荐的起点

如果你只打算记住一个起点，就记住这个：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent --workspace-id demo "你的问题草稿"
```

先把它当成一个会推进需求分析流程的 agent 来用，而不是一组零散命令。
