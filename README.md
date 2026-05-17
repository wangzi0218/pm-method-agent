# PM Method Agent

一个帮产品经理把需求想清楚的 agent 内核。

你可以把一句还没想透的草稿丢给它，例如：

```text
前台最近老是漏提醒患者，我在想是不是要处理一下。
```

它不会马上顺着你写方案，而是先帮你判断：

- 这到底是不是一个已经成立的问题
- 现在证据够不够
- 角色和责任关系有没有说清
- 是不是值得现在投入产品能力
- 下一步应该补信息、先验证，还是暂缓

## 当前状态

`PM Method Agent` 已发布到 `v0.2.0`。

这个版本已经适合被当作：

- 本地可运行的产品判断 agent 预览版
- 多轮协作、阶段关口和记忆闭环的参考实现
- 后续新产品的架构和方法样板

它还不是完整平台，也不建议继续在这个仓库里追“完全体”。

如果你想基于这些探索做一个更简洁、面向产品经理个人或团队提效的新产品，建议先看：

- [项目收尾说明](docs/project-closeout.md)
- [新产品启动 Brief](docs/new-product-brief.md)

## 为什么需要它

很多需求不是坏在设计阶段，而是坏在更早的判断阶段。

常见情况是：

- 只听到了一个抱怨，还没看清真实场景
- 用户说了一个方案，但真实问题还没定义清楚
- 看起来很急，但没有影响范围和机会成本
- 明明可以先靠流程、运营或培训解决，却直接进入产品开发
- AI 给了很多建议，但没有帮你做出更可靠的判断

`PM Method Agent` 想解决的不是“帮你写更多文档”，而是让需求进入方案设计前，多经过一层务实的问题定义审查。

## 它已经能做什么

`v0.2.0` 已经具备这些能力：

- 从一句模糊草稿开始分析
- 多轮补充背景、证据和决策倾向
- 同一工作区内承接当前案例
- 在方案先行时提醒你先确认真实问题
- 对项目背景和长期偏好给出记忆建议
- 用户确认后再写入长期记忆
- 本地命令行、本地网页演示和本地 HTTP 服务共用同一套内核

它默认输出的是一张轻量审查卡，而不是长报告。

你会看到类似这些内容：

- 当前判断：这条需求现在处在哪个阶段
- 关键问题：哪些地方证据弱、风险高
- 需要确认：现在是否能继续往方案走
- 接下来先做：下一步最值得补什么
- 记忆引用：这轮是否沿用了项目背景或个人偏好

如果你继续补充信息，它会承接上一轮，而不是要求你把完整背景重新说一遍。

## 它不是什么

这个项目目前不是：

- 完整云端产品
- 团队协作后台
- 正式 MCP 外壳
- 正式 IDE 插件或 skill 包
- 多代理编排系统
- PRD 自动生成器

这些方向已经在文档中做过设计讨论，但不建议继续全部塞进当前仓库。

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

这类草稿已经在讲方案了，系统会先提醒你确认真实问题是什么。

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

完整回归：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

网页验收：

```bash
bash scripts/web_demo_acceptance.sh
```

如果本机 pip 较旧导致可编辑安装失败，继续使用 `PYTHONPATH=src python3 -m pm_method_agent.cli ...` 即可。

## 如果你想继续这个方向

当前仓库已经适合作为参考实现收尾。

后续有两条路：

### 1. 继续研究 agent 入口

可以参考这些文档：

- [v0.3 方向设计](docs/v0-3-direction.md)
- [IDE / skill 最小契约](docs/ide-skill-minimal-contract.md)
- [本地 Skill 草稿](docs/local-skill-draft.md)
- [MCP 候选工具清单](docs/mcp-tool-candidates.md)

### 2. 开一个更简洁的新产品

如果目标是做面向产品经理个人或团队提效的产品，建议另开新项目，并参考：

- [项目收尾说明](docs/project-closeout.md)
- [新产品启动 Brief](docs/new-product-brief.md)

新项目可以借鉴这里的 harness 思路：底层保留 workspace、case、memory、event、loop，体验层再做得更自然、更轻。

## 继续了解

如果你只是想试用：

- [快速开始](docs/getting-started.md)
- [真实问题试跑](docs/real-case-testing.md)
- [典型体验用例](docs/evaluation-cases.md)

如果你想了解当前版本边界：

- [v0.2.0 发布说明](docs/releases/v0.2.0.md)
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
