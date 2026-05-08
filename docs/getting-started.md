# 快速开始

这篇写给第一次试用 `PM Method Agent` 的人。

如果你是产品经理，先不用理解运行时、接口或架构。你只需要准备一句真实的需求草稿，然后看它能不能帮你把问题收住。

## 先用哪种方式

推荐顺序很简单：

1. 想快速体验，用 `agent` 命令。
2. 想在浏览器里体验，用本地网页演示。
3. 想接入自己的工具，再看本地 HTTP 服务。
4. 想调试底层能力，再看规则、工具和命令入口。

## 方式一：直接对话

适合你如果：

- 你有一句还没想透的需求草稿
- 你想看系统会不会追问
- 你想测试它能不能连续承接几轮补充

先发一句真实输入：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "前台最近老是漏提醒患者，我在想是不是要处理一下。"
```

如果它要求补场景，可以继续说：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "这是一个 ToB 医疗服务平台，主要通过网页端使用，前台在操作，店长会看结果。"
```

你不需要把上一轮完整复制一遍。同一个 `workspace-id` 会继续承接当前案例。

## 方式二：打开本地网页演示

适合你如果：

- 不想记命令
- 想看卡片、历史、案例切换和记忆建议
- 想更接近未来真实产品形态

启动服务：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli serve --port 8011
```

打开浏览器：

```text
http://127.0.0.1:8011
```

页面里可以直接输入草稿，也可以点 `装载示例` 先看一组演示案例。

## 方式三：一次性给全场景

如果你已经知道产品类型、平台和关键角色，可以直接给完整信息：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model tob \
  --primary-platform mobile-web \
  --target-user-role 前台 \
  --target-user-role 诊所管理者 \
  --product-domain 医疗服务平台 \
  "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

这种方式更适合看单轮审查卡，不如 `agent` 入口接近真实多轮使用。

## 试用时看什么

不要只看它说得顺不顺，要重点看这些判断是否有帮助：

- 有没有把现象、解释和方案分开
- 有没有指出证据弱的地方
- 有没有识别关键角色和责任关系
- 有没有挑战“是否一定要做产品”
- 有没有给出下一步最小补充动作
- 你补充一轮后，它有没有接住上一轮

如果它只是给一段泛泛建议，没有让你更容易做判断，那就是这个场景还需要继续改进。

## 是否需要接入模型

不需要。

默认本地规则链路已经可以跑完整主线，适合先体验、测试和回归。

如果你想增强语义理解和表达，可以再配置兼容 OpenAI 接口格式的模型服务：

```bash
export PMMA_LLM_ENABLED=1
export PMMA_LLM_BASE_URL=https://api.deepseek.com
export PMMA_LLM_API_KEY=your-api-key
export PMMA_LLM_MODEL=deepseek-chat
```

建议先不用模型跑一轮，再打开模型增强。这样更容易判断：哪些能力来自方法内核，哪些能力来自模型表达。

## 如果你想接入自己的工具

先启动本地 HTTP 服务：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli serve
```

发送一条工作区消息：

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": "最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。"
  }'
```

外部客户端优先消费这些字段：

- `case`
- `case_runtime`
- `rendered_card`
- `rendered_history`

更完整的接入方式见 [接入示例](integration-examples.md) 和 [本地 HTTP 服务](http-service.md)。

## 下一步读什么

- 想拿真实问题试：看 [真实问题试跑](real-case-testing.md)。
- 想知道当前版本边界：看 [v0.2 发布准备清单](v0-2-readiness.md)。
- 想知道网页能做什么：看 [网页演示边界](web-demo-boundaries.md)。
- 想找全部文档：看 [文档索引](README.md)。
