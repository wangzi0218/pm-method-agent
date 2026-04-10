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

从产品形态上看，这个项目应当优先作为一个统一入口的 `agent` 被使用，而不是要求最终用户直接运行 Python 命令。

当前仓库保留命令行工具，主要用于：

- 方法内核验证
- 本地调试
- 回归测试
- 示例演示

未来面向用户的交付形态会并行支持：

- 命令行工具
- 主代理 / AI 工具入口
- 可选网页入口

这些入口应共用同一套方法内核，而不是维护多套独立逻辑。当前已经开始补本地 HTTP 服务层，作为 CLI、skill、agent 和未来 MCP/网页入口之间的统一底座。

当前仓库默认仍使用规则解释器来承接多轮回复，但已经补上了 LLM 适配骨架，后续可以按用户环境切换到“用户自带模型”或“托管模型”模式，而不需要重写状态机。

当前推荐优先使用 OpenAI-compatible 配置方式，也就是只需要：

- `base_url`
- `api_key`
- `model`

这样可以更自然地接入各种兼容 OpenAI 格式的模型服务。

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

在一些较老的 Python / pip 环境里，`install -e .` 仍可能失败。遇到这种情况，直接继续使用源码直跑即可，不影响体验当前版本。

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

通过统一入口模拟 agent / skill 交互：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
 "前台最近老是漏提醒患者，我在想是不是要处理一下。"
```

继续补一句：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "这是一个 ToB 移动端产品，前台使用，管理者负责结果。"
```

查看当前工作区：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli workspace demo
```

切换到指定案例：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli workspace demo \
  --switch-case-id case-xxxxxx
```

启动本地 HTTP 服务：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli serve --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

读取工作区最近案例：

```bash
curl http://127.0.0.1:8000/workspaces/demo/cases
```

切换当前工作区的活跃案例：

```bash
curl -X POST http://127.0.0.1:8000/workspaces/demo/active-case \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "case-xxxxxx"
  }'
```

创建案例：

```bash
curl -X POST http://127.0.0.1:8000/cases \
  -H "Content-Type: application/json" \
  -d '{
    "input": "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。",
    "context_profile": {
      "business_model": "tob",
      "primary_platform": "mobile-web",
      "target_user_roles": ["前台", "诊所管理者"]
    }
  }'
```

创建项目背景：

```bash
curl -X POST http://127.0.0.1:8000/project-profiles \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "医疗服务平台",
    "context_profile": {
      "business_model": "tob",
      "primary_platform": "mobile-web"
    },
    "stable_constraints": ["上线周期紧"]
  }'
```

通过统一 agent 入口发送消息：

```bash
curl -X POST http://127.0.0.1:8000/agent/messages \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "demo",
    "message": "前台最近老是漏提醒患者，我在想是不是要处理一下。"
  }'
```

这组命令当前仍是验证版，但已经代表了后续网页和 agent 入口会共用的底层会话模型。

如果你希望让“回复解释”这一步优先使用兼容 OpenAI 格式的模型服务，可以先配置：

```bash
export PMMA_LLM_ENABLED=1
export PMMA_LLM_BASE_URL=https://api.deepseek.com
export PMMA_LLM_API_KEY=your-api-key
export PMMA_LLM_MODEL=deepseek-chat
```

配置后，再继续执行 `reply`，系统会优先使用 LLM 解释器；如果配置不完整，则会自动回退到规则解释器。

当前多轮承接已经支持：

- 根据卡片类型恢复到正确阶段，而不是总从头重跑
- 记录关口选择，并影响后续状态推进
- 对“暂缓”“先试非产品路径”“继续产品化”做不同分支处理
- 在需要时保持关口阻塞，而不是误判为已完成
- 通过工作区记住当前活跃 case 和项目背景
- 查看最近案例，并在案例之间切换
- 通过 HTTP service 直接驱动统一 agent 入口
- 在有模型配置时，用 LLM 增强回复解释、前置收敛和卡片文案
- 为统一入口补上了最小 `runtime session`，记录 `query_id`、`turn_count`、`resume_from` 和终止语义
- 为每轮 agent 交互补上了最小事件日志，后续可以继续扩展到执行账本和 sub-agent 生命周期
- 为统一入口补上了最小 `execution ledger`，记录关键执行单元的 `requested / completed / failed` 状态，并在下一轮开始时自动收口未闭环项
- 已在 runtime 层显式区分 `completed / blocked / deferred / failed / interrupted / cancelled / continued` 等终止语义

## 体验建议

如果你想判断当前方法内核是否已经站得住，不建议只跑一个例子。

更合适的方式是直接按体验用例集逐条验证：

- [docs/evaluation-cases.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/evaluation-cases.md)：推荐体验顺序、覆盖场景与预期观察点
- [docs/real-case-testing.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/real-case-testing.md)：如何拿真实问题试跑、记录反馈并判断体验是否站得住

如果你想判断“现在是不是已经适合公开发到 GitHub”，可以对照：

- [docs/release-readiness.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-readiness.md)：首次公开发布的最小标准与检查清单
- [docs/release-process.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/release-process.md)：首次公开前的提交、推送和版本建议

## 文档导航

- [docs/architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/architecture.md)：系统架构、升级口和交付适配层
- [docs/agent-architecture.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-architecture.md)：主代理、专项代理和内部协作方式
- [docs/agent-interaction.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-interaction.md)：主代理状态机、追问规则和阶段推进逻辑
- [docs/agent-shell-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/agent-shell-runtime.md)：最小 agent 外壳、工作区状态和统一入口运行时
- [docs/advanced-agent-runtime.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/advanced-agent-runtime.md)：更完整的 agent runtime 设计，包括 query loop、终止语义、prompt 治理和 sub-agent 编排
- [docs/brainstorm-integration.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/brainstorm-integration.md)：如何把 brainstorm 作为前置思考层融合进主代理，而不退化成普通聊天
- [docs/context-profile.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/context-profile.md)：场景和产品基础信息的定义方式
- [docs/contracts.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/contracts.md)：案例状态、结论项、决策关口和证据分级契约
- [docs/evaluation-cases.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/evaluation-cases.md)：典型体验用例与验证方式
- [docs/real-case-testing.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/real-case-testing.md)：真实问题试跑方法、记录模板与体验判断标准
- [docs/output-style.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/output-style.md)：默认输出风格与审查卡结构
- [docs/implementation-roadmap.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/implementation-roadmap.md)：里程碑、实现阶段和后续发展计划
- [docs/http-service.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/http-service.md)：本地 HTTP 服务层、接口定义和与 MCP 的关系
- [docs/interaction-memory-design.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/interaction-memory-design.md)：用户触发、持续互动、记忆层与主动建议设计
- [docs/llm-adapter.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/llm-adapter.md)：LLM 适配层、解释器注入点和未来接入方式
- [docs/prompt-layering.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/prompt-layering.md)：Prompt 分层、优先级和项目级追加规则的最小实现
- [docs/rule-layering.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/rule-layering.md)：规则分层、规则来源、目录作用域和规则加载器的设计
- [docs/runtime-policy.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/runtime-policy.md)：规则从“被看见”到“被执行”的最小硬约束层
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
- 一层可扩展的 LLM 适配骨架与回复解释器接口
- 一层最小可运行的本地 HTTP 服务
- 一份面向长期协作的交互层与记忆层设计
- 一层最小可运行的 agent 外壳与工作区状态
- 一套基于工作区的案例查看与切换能力
- 一层基于 OpenAI-compatible 配置的 LLM 增强理解与文案能力
- 一层最小可运行的高级 runtime 骨架，包括 `runtime session`、终止语义和事件日志
- 一层最小可运行的执行账本骨架，用来追踪关键执行步骤并为后续工具闭环打底
- 一层最小可运行的 prompt composer，用来统一组织身份描述、行为规则、工具约束、输出纪律和项目级追加规则
- 一层最小可运行的规则加载器，用来吸收用户本地、仓库级、目录级和结构化策略规则
- 一层最小可运行的 runtime policy，用来把部分规则变成真正的运行时硬约束，并开始覆盖内部动作级执行关口

## 后续形态

这个项目的长期目标，不是只做一个 CLI 工具。

更合理的演进方式是：

- 当前阶段：CLI 用于验证方法内核
- 下一阶段：继续完善交互层、记忆层和 skill / agent 接入
- 后续阶段：优先提供 skill / agent 入口，再按需要补网页和托管服务能力

如果未来提供网页或 AI 原生入口，底层都会复用这层服务接口来承接会话状态、阶段推进和结果读取。

## License

当前仓库使用 [MIT License](/Users/wannz/Documents/sourcetree/pm-method-agent/LICENSE)。
