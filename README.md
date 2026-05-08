# PM Method Agent

一个帮产品经理把需求想清楚的 agent。

你可以把一句还没想透的草稿丢给它，例如：

```text
前台最近老是漏提醒患者，我在想是不是要处理一下。
```

它不会马上顺着你写方案，而是先帮你判断：

- 这到底是一个什么问题
- 现在证据够不够
- 角色和责任关系有没有说清
- 是不是值得现在投入产品能力
- 下一步应该补信息、先验证，还是暂缓

## 为什么需要它

很多需求不是坏在设计阶段，而是坏在更早的判断阶段。

常见情况是：

- 只听到了一个抱怨，还没看清真实场景
- 用户说了一个方案，但问题本身还没定义清楚
- 看起来很急，但没有影响范围和机会成本
- 明明可以先靠流程、运营或培训解决，却直接进入产品开发
- AI 给了很多建议，但没有帮你做出更可靠的判断

`PM Method Agent` 想解决的不是“帮你写更多文档”，而是让需求进入方案设计前，多经过一层务实的问题定义审查。

## 它会怎么帮你

它默认输出的是一张轻量审查卡，而不是长报告。

你会看到类似这些内容：

- 当前判断：这条需求现在处在哪个阶段
- 关键问题：哪些地方证据弱、风险高
- 需要确认：现在是否能继续往方案走
- 建议先做：下一步最值得补什么
- 记忆引用：这轮是否沿用了项目背景或个人偏好

如果你继续补充信息，它会承接上一轮，而不是要求你把完整背景重新说一遍。

## 适合谁

更适合：

- 需要判断“这个需求到底值不值得做”的产品经理
- 想在方案设计前先收紧问题定义的设计师、产品负责人或业务负责人
- 希望把个人经验沉淀成团队方法的人
- 已经使用 AI，但不想每次都自己组织复杂提示词的人

不太适合：

- 只想快速生成完整 PRD
- 已经明确要做，只缺排期和拆任务
- 希望系统替你做最终业务决策
- 没有任何真实场景、证据或用户线索，却希望得到确定结论

## 现在能体验什么

当前处于 `v0.2` 预览版准备状态。

已经可以体验：

- 从一句模糊草稿开始分析
- 多轮补充背景、证据和决策倾向
- 同一工作区内承接当前案例
- 对项目背景和长期偏好给出记忆建议
- 用户确认后再写入长期记忆
- 本地命令行、本地网页演示和本地 HTTP 服务

暂时还不是：

- 完整云端产品
- 正式 MCP 外壳
- 正式 IDE 插件或 skill 包
- 多代理编排系统
- PRD 自动生成器

## 最快体验方式

当前还是开源预览版，需要在本地跑起来。

环境要求：Python 3.9 及以上。

### 方式一：直接对话

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "前台最近老是漏提醒患者，我在想是不是要处理一下。"
```

然后继续补一句背景：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli agent \
  --workspace-id demo \
  "这是一个 ToB 医疗服务平台，主要通过网页端使用，前台在操作，店长会看结果。"
```

### 方式二：打开本地网页演示

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli serve --port 8011
```

然后打开：

```text
http://127.0.0.1:8011
```

如果你不想自己编输入，可以点页面里的 `装载示例`。

## 一个更完整的例子

如果你希望先把场景信息一次性给全，可以这样跑：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model tob \
  --primary-platform mobile-web \
  --target-user-role 前台 \
  --target-user-role 诊所管理者 \
  --product-domain 医疗服务平台 \
  "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

这类输入里已经带出方案，系统会优先提醒你先把问题本身拆出来。

## 如果你想接入模型

默认不强依赖模型服务。需要模型增强时，可以接入兼容 OpenAI 接口格式的服务：

```bash
export PMMA_LLM_ENABLED=1
export PMMA_LLM_BASE_URL=https://api.deepseek.com
export PMMA_LLM_API_KEY=your-api-key
export PMMA_LLM_MODEL=deepseek-chat
```

模型主要负责语义理解和表达增强。阶段推进、决策关口、记忆写入确认这些控制逻辑仍由本地方法内核负责。

## 如果你是开发者

本地安装：

```bash
python3 -m pip install -e .
```

基础回归：

```bash
PYTHONPATH=src python3 -m unittest tests.test_smoke tests.test_human_like_flows
```

网页验收：

```bash
bash scripts/web_demo_acceptance.sh
```

如果本机 pip 较旧导致可编辑安装失败，继续使用 `PYTHONPATH=src python3 -m pm_method_agent.cli ...` 即可。

## 继续了解

如果你只是想试用：

- [快速开始](docs/getting-started.md)
- [真实问题试跑](docs/real-case-testing.md)
- [典型体验用例](docs/evaluation-cases.md)

如果你想了解当前版本边界：

- [v0.2 发布准备清单](docs/v0-2-readiness.md)
- [v0.2 产品定义](docs/product-v0-2.md)
- [网页演示边界](docs/web-demo-boundaries.md)

如果你想了解架构和路线：

- [文档索引](docs/README.md)
- [文档地图](docs/documentation-map.md)
- [实现路线图](docs/implementation-roadmap.md)
- [整体架构](docs/architecture.md)

## License

[MIT](LICENSE)
