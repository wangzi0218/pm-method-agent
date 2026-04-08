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
- 初步判断
- 关键判断
- 需要确认
- 先做这几步
- 待补信息

## 用户入口

从产品形态上看，这个项目应当优先作为一个统一入口的 `agent` 被使用，而不是要求最终用户直接运行 Python 命令。

当前仓库保留命令行工具，主要用于：

- 方法内核验证
- 本地调试
- 回归测试
- 示例演示

未来面向用户的交付形态会并行支持：

- 命令行工具
- 交互网页
- 主代理 / AI 工具入口

这三种入口应共用同一套方法内核，而不是维护三套独立逻辑。

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

当前阶段最稳的运行方式，不是先安装命令，而是直接源码运行：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model tob \
  --primary-platform mobile-web \
  --target-user-role 前台 \
  --target-user-role 诊所管理者 \
  --product-domain 医疗服务平台 \
  "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

如果只是想快速体验，这一条已经足够。

### 可选安装

如果你希望把它安装成本地命令，再执行：

```bash
python3 -m pip install -e .
```

安装成功后，可以直接使用：

```bash
pm-method-agent "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

如果本机 `pip` 版本较旧，建议先升级，再安装：

```bash
python3 -m pip install --upgrade pip
```

如果你暂时不想动本机环境，就继续使用源码直跑方式：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

带场景信息运行：

```bash
pm-method-agent \
  --business-model tob \
  --primary-platform pc \
  --target-user-role 前台 \
  --target-user-role 诊所管理者 \
  --product-domain 医疗SaaS \
  "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

只运行单一模式：

```bash
pm-method-agent --mode problem-framing "诊所希望做一个新的数据看板"
```

输出 JSON：

```bash
pm-method-agent --format json "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

### 当前阶段的入口说明

当前仓库中的 CLI 主要用于：

- 方法内核验证
- 回归测试
- 示例演示

它已经适合公开体验，但还不是最终面向用户的完整 agent 入口。

### 多轮会话试用

当前仓库已经提供了一个最小可运行的会话模式，用来提前验证未来 agent / 网页都会依赖的状态承接能力。

开始一个新会话：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli start \
  "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

补充回答并继续：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli reply case-xxxxxx \
  "这是一个 ToB 移动端产品，前台使用，管理者负责结果。"
```

查看当前会话：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli show case-xxxxxx
```

查看会话历史：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli history case-xxxxxx
```

这组命令当前仍是验证版，但已经代表了后续网页和 agent 入口会共用的底层会话模型。

## 体验建议

如果你想判断当前方法内核是否已经站得住，不建议只跑一个例子。

更合适的方式是直接按体验用例集逐条验证：

- [docs/evaluation-cases.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/evaluation-cases.md)：推荐体验顺序、覆盖场景与预期观察点

如果你想判断“现在是不是已经适合公开发到 GitHub”，可以对照：

- [docs/release-readiness.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-readiness.md)：首次公开发布的最小标准与检查清单
- [docs/release-process.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-process.md)：首次公开前的提交、推送和版本建议

## 文档导航

- [docs/architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/architecture.md)：系统架构、升级口和交付适配层
- [docs/agent-architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-architecture.md)：主代理、专项代理和内部协作方式
- [docs/agent-interaction.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-interaction.md)：主代理状态机、追问规则和阶段推进逻辑
- [docs/context-profile.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/context-profile.md)：场景和产品基础信息的定义方式
- [docs/contracts.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/contracts.md)：案例状态、结论项、决策关口和证据分级契约
- [docs/evaluation-cases.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/evaluation-cases.md)：典型体验用例与验证方式
- [docs/output-style.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/output-style.md)：默认输出风格与审查卡结构
- [docs/implementation-roadmap.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/implementation-roadmap.md)：里程碑、实现阶段和后续发展计划
- [docs/release-process.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-process.md)：首次公开前的提交流程与版本建议
- [docs/release-readiness.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-readiness.md)：GitHub 首次公开发布的标准
- [docs/session-service-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/session-service-design.md)：多轮会话与服务层设计
- [docs/releases/v0.1.0.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/releases/v0.1.0.md)：首个公开版本说明

## 当前状态

当前仓库已经包含：

- 一版项目说明和方法设计草案
- 一版最小可运行的命令行工具
- 一份 agent-first 的运行设计
- 一份主代理交互设计
- 一套可复用的数据结构定义、审查卡风格约束与示例案例
- 一组最基础的 smoke tests
- 一套可直接复制执行的体验用例

## 后续形态

这个项目的长期目标，不是只做一个 CLI 工具。

更合理的演进方式是：

- 当前阶段：CLI 用于验证方法内核
- 下一阶段：增加多轮会话能力与服务层
- 后续阶段：同时提供网页入口和 agent 入口

如果未来提供网页形态，底层会补一层服务接口或 API，用来承接会话状态、阶段推进和结果读取。

## License

当前仓库使用 [MIT License](/Users/wannz/Documents/sourcetree/pm-method-agent/LICENSE)。
