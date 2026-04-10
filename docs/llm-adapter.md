# LLM 适配层设计

## 目标

`PM Method Agent` 的长期形态一定会接入 LLM，但不应把方法核心直接绑死在某一个模型或某一个供应商上。

如果要进一步看“哪些能力该留在本地层，哪些能力该交给 LLM”，可继续参考：

- [docs/llm-boundary-scenarios.md](/Users/wannz/Documents/sourcetree/pm-method-agent/docs/llm-boundary-scenarios.md)

这一层的目标不是“让模型接管所有逻辑”，而是把模型调用放进稳定边界里，让项目同时支持：

- 默认无模型运行
- 用户自带模型配置
- 网页或服务端托管模型

## 当前实现边界

当前仓库已经补上了最小适配骨架：

- `src/pm_method_agent/llm_adapter.py`
- `src/pm_method_agent/reply_interpreter.py`
- `src/pm_method_agent/pre_framing.py`
- `src/pm_method_agent/case_copywriter.py`

当前已落地的能力包括：

- `LLMAdapter` 协议
- 统一的 `LLMRequest` / `LLMResponse` 数据结构
- `OpenAICompatibleAdapter`
- `OpenAICompatibleConfig`
- `HeuristicReplyInterpreter`
- `LLMReplyInterpreter`
- `HybridReplyInterpreter`
- `LLMPreFramingGenerator`
- `LLMCaseCopywriter`
- `reply_to_case(..., reply_interpreter=...)` 注入点
- 基于环境变量的默认解释器切换

这意味着：

- 默认情况下，系统仍可完全不依赖 LLM 运行
- 一旦接入真实模型，就可以先替换“用户回复解释”这类局部能力
- 不需要重写 `session_service` 或状态机

## 为什么先接“回复解释器”，而不是整套分析器

如果一开始就让 LLM 直接负责全部分析，会有两个问题：

- 方法边界容易被模型行为带偏
- 回归测试会更难稳定

当前更合适的顺序是：

1. 让状态机、关口和输出契约先稳定。
2. 让 LLM 先承担高弹性、强语义的局部任务。
3. 再逐步扩大 LLM 参与范围。

因此第一批适合 LLM 化的环节是：

- 用户回复的结构化解释
- 关口选择的语义识别
- 场景信息抽取
- pre-framing 的候选方向生成
- 更自然的协作文案

当前已经实际接入的就是这三类：

- `reply interpreter`：混合模式，LLM 增强 + 规则兜底
- `pre-framing generator`：LLM 只增强候选方向，不碰主线状态
- `case copywriter`：LLM 只润色文案槽位，不碰结构和关口

而这些环节之外，当前仍建议优先保持规则化：

- 阶段推进
- 决策关口触发
- 输出卡片结构
- 证据等级的显式呈现

## 当前推荐分层

### 方法核心

负责：

- `CaseState`
- 分析模块
- 决策关口
- 状态机
- 输出渲染

### 会话服务层

负责：

- case 创建和回复承接
- 状态恢复
- 历史记录
- 解释器注入

### LLM 适配层

负责：

- 统一模型请求结构
- 屏蔽不同供应商 SDK 差异
- 提供稳定的解释器输入输出

### 交付入口层

负责：

- CLI
- agent
- 网页
- API

## 适配接口

### `LLMAdapter`

最小要求只有一个动作：

- `generate(request) -> LLMResponse`

这允许后续挂接：

- OpenAI
- Anthropic
- 国内模型网关
- 团队内部代理服务

### `ReplyInterpreter`

这是目前 LLM 最先接入的业务接口。

它的职责是把一段自然语言回复解释成结构化结果，至少包括：

- `context_updates`
- `categories`
- `inferred_gate_choice`
- `parser_name`

当前已经有两种实现：

- `HeuristicReplyInterpreter`
- `LLMReplyInterpreter`

默认情况下，如果环境变量中存在完整的 OpenAI-compatible 配置，系统会自动使用 `LLMReplyInterpreter`；否则回退到 `HeuristicReplyInterpreter`。

## OpenAI-compatible 配置

当前推荐直接使用这组环境变量：

- `PMMA_LLM_ENABLED=1`
- `PMMA_LLM_BASE_URL`
- `PMMA_LLM_API_KEY`
- `PMMA_LLM_MODEL`

可选项：

- `PMMA_LLM_PROVIDER`
- `PMMA_LLM_API_PATH`
- `PMMA_LLM_TIMEOUT`
- `PMMA_LLM_EXTRA_HEADERS_JSON`

如果你想在本地安全地配置，而不把密钥带进仓库，建议：

1. 复制一份 [.env.example](/Users/wannz/Documents/sourcetree/pm-method-agent/.env.example)
2. 本地保存为 `.env.local`
3. 再把真实 key 只写进 `.env.local`

当前 CLI、agent 和 HTTP service 启动时都会优先读取当前目录下的 `.env` / `.env.local`。

仓库默认已经忽略：

- `.env`
- `.env.local`
- `.env.*.local`

例如使用兼容 OpenAI 格式的服务时，可以像这样：

```bash
export PMMA_LLM_ENABLED=1
export PMMA_LLM_BASE_URL=https://api.deepseek.com
export PMMA_LLM_API_KEY=your-api-key
export PMMA_LLM_MODEL=deepseek-chat
```

或使用本地 `.env.local`：

```bash
cp .env.example .env.local
```

配置后，`reply` 会自动尝试使用 LLM 来解释用户回复。

## 三种使用方式

### 1. 默认本地模式

特点：

- 不依赖外部模型
- 直接用规则解释器
- 适合开发、测试、离线验证

### 2. 用户自带模型模式

特点：

- 用户在 IDE、AI 工具或本地环境里配置模型
- 项目只负责方法编排和状态机
- 更适合早期 agent 集成

### 3. 托管模型模式

特点：

- 网页或服务端统一调用模型
- 用户不需要自己配置 key
- 更适合面向更广泛用户

## 当前限制

当前仓库还没有直接提供某个供应商的生产级适配器。

这是刻意保留的边界，因为现阶段更重要的是：

- 先把统一协议定稳
- 先把状态机接点打通
- 先保证无模型模式也能工作

## 下一步建议

后续可以按这个顺序继续：

1. 补更细的失败处理和超时提示。
2. 把更多高弹性语义环节逐步切到 LLM。
3. 在 CLI 和网页里补显式的模型状态展示。
4. 为 LLM 输出补充更严格的契约校验和回退机制。
