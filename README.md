# PM Method Agent

`PM Method Agent` 是一个面向产品分析前置阶段的方法层智能体，用来在设计和开发开始前提升问题定义质量。

它不是一个泛泛而谈的 AI 对话助手，也不是想替代产品经理本身，而是通过结构化分析、证据分级和受控的人类决策点，把前期思考过程变得更严谨、更可复用。

## 它解决什么问题

很多需求在真正进入设计和开发前，就已经埋下了判断偏差：

- 现象、解释、方案混在一起
- 真正受影响的人没有被识别清楚
- 紧急程度和影响范围缺少证据支撑
- 用户当前的替代方案和绕路行为没有被看到
- 非产品手段是否更合适没有被认真挑战
- 成功标准定义得太晚

`PM Method Agent` 的目标，就是把这些过去经常被省略的方法动作，沉淀成一套可复用的分析系统。

## 它不是什么

- 不是一个泛化的“陪聊型” AI 产品顾问
- 不是一个直接替你写完整 PRD 的文案工具
- 不是一个默认所有问题都要产品化的需求生成器

## 它更适合谁

这个项目更适合这些人：

- 需要频繁判断“这个问题到底值不值得做”的产品经理
- 希望在方案设计前，先把问题定义收紧的设计师、产品负责人、业务负责人
- 习惯和 AI 协作，但不希望最后只得到一段泛泛建议的人
- 需要把“经验判断”逐步沉淀成可复用方法的人

## 它不太适合谁

这个项目不太适合这些场景：

- 你只想快速生成一份完整 PRD 文案
- 你已经有非常稳定的问题定义流程，不需要额外的方法约束
- 你希望系统替你直接拍板，而不愿意保留必要的人类判断
- 你的问题本身更像执行排期、项目管理或纯研发实现，不属于问题定义阶段

## 为什么要做人类与 AI 的协作产品

这个项目的前提不是“让 AI 替代产品经理”，而是把 AI 放在更合适的位置：

- AI 更适合做结构化拆解、提醒盲点、维持输出一致性
- 人类更适合做场景判断、业务取舍、责任承担和最终决策

如果把前期判断完全交给人，容易受经验惯性和表达状态影响。

如果把前期判断完全交给 AI，又很容易出现另一类问题：

- 说得很多，但没有真正帮助判断
- 看起来完整，但关键前提其实是猜的
- 默认顺着需求往下写方案，而没有认真挑战问题本身

这个项目想做的，是让两者各自承担更适合自己的部分。

## 这种协作方式的收益与限制

收益主要在这里：

- 能把原本容易被省略的方法动作稳定下来
- 能降低“说了很多但没有推进判断”的空转感
- 能把产品分析从个人经验，逐步沉淀成团队可复用的结构
- 能让用户在 CLI、网页或 AI 工具里获得更一致的分析体验

限制也需要提前说清：

- AI 仍然不能替代真实业务上下文
- 输入太弱时，系统最多只能帮助追问，不能凭空产出可靠判断
- 决策关口仍然需要人类承担最终责任
- 如果方法契约设计得不好，工具也可能变成另一种形式化负担

## 核心特点

- `方法优先于闲聊`：输出遵循稳定的分析结构
- `允许推断，但必须标注`：系统会区分事实、推断和缺失证据
- `人工决策很贵`：只在真正影响推进的节点让人决策
- `从一开始就保留升级口`：第一版可以是单一入口能力，后续可以升级成复合智能体系统

## 输出形态

默认输出形态不是长报告，而是“轻量结构化审查卡”。

这样设计有两个原因：

- 更适合在 IDE、命令行工具、AI 对话窗口中快速阅读
- 既保留方法约束，又不会因为过度正式而增加使用门槛

一份典型输出通常包含：

- 基础信息
- 当前判断
- 关键判断
- 需要确认
- 建议先做
- 建议补充

## 用户入口

从产品形态上看，这个项目更适合作为一个统一入口的 `agent` 被使用，而不是要求最终用户直接记住一组 Python 命令。

当前仓库保留 CLI，主要用于：

- 方法内核验证
- 本地调试
- 回归测试
- 示例演示

长期会并行支持：

- CLI / IDE agent
- skill / AI 工具入口
- 网页 / 云端入口
- 混合模式

这些入口应共用同一套方法内核、状态机和规则层，而不是维护多套独立逻辑。部署形态的详细说明见 [docs/deployment-modes.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/deployment-modes.md)。

如果你关心网页 demo 第一版到底负责什么、不负责什么，可以继续看：

- [docs/web-demo-boundaries.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/web-demo-boundaries.md)

如果你现在只想知道“我到底该从哪里开始”，建议直接看：

- [docs/getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)

当前仓库默认仍使用规则解释器来承接多轮回复，但已经补上了 LLM 适配骨架，后续可以按用户环境切换到“用户自带模型”或“托管模型”模式，而不需要重写状态机。

当前推荐优先使用 OpenAI-compatible 配置方式，也就是只需要：

- `base_url`
- `api_key`
- `model`

这样可以更自然地接入各种兼容 OpenAI 格式的模型服务。

如果模型服务暂时不可用，例如 `base_url` 不可达、超时、返回异常内容，当前实现会自动回退到本地规则链路继续完成这一轮分析，而不是直接把整轮会话打成失败。这个降级现在已经覆盖回复解释、前置收敛和文案增强三个入口。

## 适用场景

- 需求刚被提出，但问题定义仍然模糊
- 团队准备评审一个需求，想先挑战它是否值得做
- 方案还没开始，希望先补齐验证假设和成功标准
- 希望把“产品感觉”变成“有证据等级的方法判断”

## 用户会得到什么

针对一个输入需求，系统会尽量输出这些内容：

- 当前场景和产品基础信息是否足够支撑判断
- 问题定义是否混入了方案表达
- 当前可能涉及的关键角色
- 证据充分度和关键未知项
- 是否应优先尝试非产品解法
- 最小验证动作、成功指标和停止条件

## 一个最小例子

输入：

```text
前台希望增加一个预约前提醒弹窗，避免漏提醒患者。
```

系统不会直接顺着写方案，而会先给出类似这样的判断：

- 输入已经带出方案，建议先把问题本身收拢
- 需要补充现状流程、失败案例和角色关系
- 先补证据，再决定要不要进入方案讨论

完整结构化案例见 [examples/problem-definition-case.json](/Users/wannz/Documents/sourcetree/pm-method-agent/examples/problem-definition-case.json)。

## 开发验证

当前仓库已经提供了一个最小可运行的 Python 命令行工具，默认输出为审查卡。

环境要求：

- Python 3.9 及以上

### 推荐快速开始

如果你只是想先体验当前方法内核，最稳的方式仍然是直接源码运行。

如果你不想先记命令，推荐先看这一页：

- [docs/getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)

单轮直跑：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model tob \
  --primary-platform mobile-web \
  --target-user-role 前台 \
  --target-user-role 诊所管理者 \
  --product-domain 医疗服务平台 \
  "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

如果你只是想看单轮输出，这一条已经足够。

但如果你想体验更接近真实使用的方式，当前更推荐直接走统一入口 `agent`：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "前台最近老是漏提醒患者，我在想是不是要处理一下。"
```

再顺手补一句：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "这是一个 ToB 医疗服务平台，主要通过网页端使用，前台在操作，店长会看结果。"
```

如果你在接团队规则、仓库规则或目录规则，也可以先看一眼当前到底生效了哪些内容：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli rules \
  --base-dir . \
  --show-prompt
```

如果你想先看当前本地工具底座已经暴露了什么，也可以直接列工具：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli tool --list
```

如果你想看当前工作区的 runtime session、工作记忆、摘要记忆和压缩状态：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli runtime \
  --workspace-id demo
```

如果这一轮发生过模型降级，runtime event log 里也会留下 `llm-fallback` 记录，方便后面排查是回复解释、前置收敛还是文案增强没有走到模型增强路径。

看某一个工具的参数契约：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli tool \
  --describe local-text-file-read
```

通过统一入口读取一个本地文本文件：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli tool \
  --tool-name local-text-file-read \
  --payload-json '{"workspace_id":"demo","path":"README.md"}'
```

### 可选安装

如果你希望安装本地命令，可以尝试：

```bash
python3 -m pip install -e .
```

如果本机环境较老，`install -e .` 可能失败。这时直接继续使用源码直跑即可。

### 继续体验

如果你想体验多轮承接，当前更推荐直接走统一入口 `agent`：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "前台最近老是漏提醒患者，我在想是不是要处理一下。"
```

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "这是一个 ToB 医疗服务平台，主要通过网页端使用，前台在操作，店长会看结果。"
```

如果你希望启用兼容 OpenAI 格式的模型服务，可以配置：

```bash
export PMMA_LLM_ENABLED=1
export PMMA_LLM_BASE_URL=https://api.deepseek.com
export PMMA_LLM_API_KEY=your-api-key
export PMMA_LLM_MODEL=deepseek-chat
```

启动本地网页后，如果你只是想先看一眼整体体验，不想自己手工编几轮输入，现在也可以直接点网页里的 `装载示例`。这一组示例会优先尝试由当前模型生成；如果模型暂时不可用，会自动回退到仓库内置样本。

更完整的入口、HTTP 示例和接入方式，建议直接看：

- [docs/getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)
- [docs/integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)
- [docs/README.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/README.md)
- [docs/http-service.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/http-service.md)
- [docs/deployment-modes.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/deployment-modes.md)
- [docs/agent-shell-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-shell-runtime.md)

## 体验建议

如果你想判断当前方法内核是否已经站得住，不建议只跑一个例子。

更合适的方式是直接按体验用例集逐条验证：

- [docs/evaluation-cases.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/evaluation-cases.md)：推荐体验顺序、覆盖场景与预期观察点
- [docs/manual-smoke.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/manual-smoke.md)：本地工具链、agent 多轮和真人风格用例的一键手动冒烟
- [docs/real-case-testing.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/real-case-testing.md)：如何拿真实问题试跑、记录反馈并判断体验是否站得住

如果你想判断“现在是不是已经适合公开发到 GitHub”，可以对照：

- [docs/release-readiness.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-readiness.md)：首次公开发布的最小标准与检查清单
- [docs/release-process.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-process.md)：首次公开前的提交、推送和版本建议

## 文档导航

- [docs/getting-started.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/getting-started.md)：第一次使用时该从哪里开始
- [docs/integration-examples.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/integration-examples.md)：不同外壳和脚本的最小接法
- [docs/README.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/README.md)：按主题整理过的完整文档索引
- [docs/implementation-roadmap.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/implementation-roadmap.md)：当前做到哪一步，以及后续计划
- [docs/release-readiness.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-readiness.md)：首次公开发布前的检查项

## 当前状态

当前仓库已经具备一套可运行的最小主线：

- 可运行的 CLI 与统一 agent 入口
- 可恢复的多轮案例与工作区状态
- OpenAI-compatible 的 LLM 适配骨架
- 可检查的规则层、prompt layering 和 runtime policy
- 受控的本地工具运行时、hook 和执行账本
- 开始区分本地工具和平台工具，并通过统一工具发现入口对外暴露
- 平台工具也开始进入统一 runtime，其中已包含第一个可写平台工具
- `local-command`、`local-directory-list`、`local-text-file-read`、`local-text-search`、`local-text-file-write` 五类最小工具

更细的实现进展和后续计划，建议看：

- [docs/implementation-roadmap.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/implementation-roadmap.md)
- [docs/advanced-agent-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/advanced-agent-runtime.md)

## 后续形态

这个项目的长期目标不是停留在 CLI，而是形成一个可同时支撑本地、网页和混合模式的受控 agent 内核。详细形态见 [docs/deployment-modes.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/deployment-modes.md)。

## License

当前仓库使用 [MIT License](/Users/wannz/Documents/sourcetree/pm-method-agent/LICENSE)。
