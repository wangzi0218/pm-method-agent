# 体验用例集

## 目标

这份文档用于验证当前 CLI 运行时是否已经具备稳定、可复用的“方法内核”体验。

每条用例都尽量满足三件事：

- 可以直接复制执行
- 覆盖不同产品语境
- 能验证明确的输出特征

## 使用方式

进入仓库根目录后，优先使用源码直跑方式：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli "你的需求描述"
```

如果本机安装入口已经可用，也可以改成：

```bash
pm-method-agent "你的需求描述"
```

## 用例 1：信息不足时先补场景

目的：

- 验证系统不会直接进入分析
- 验证是否优先追问最小必要信息

运行：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

预期观察点：

- 输出应为“场景补充卡”
- 不应直接进入完整审查卡
- 追问应集中在产品类型、主要平台、关键角色

## 用例 2：ToB 移动端方案导向需求

目的：

- 验证问题定义是否能识别“方案先行”
- 验证移动端和企业产品语境是否被纳入判断

运行：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model tob \
  --primary-platform mobile-web \
  --target-user-role 前台 \
  --target-user-role 诊所管理者 \
  --product-domain 医疗服务平台 \
  "前台希望增加一个预约前提醒弹窗，避免漏提醒患者。"
```

预期观察点：

- 初步判断应指出“输入已经带出方案”
- 关键判断中应出现角色关系、时机说明、非产品路径
- 应出现移动端限制相关提醒

## 用例 3：ToB 流程/权限类问题

目的：

- 验证是否会在决策挑战阶段停下
- 验证是否优先提示非产品路径

运行：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model tob \
  --primary-platform pc \
  --target-user-role 审批专员 \
  --target-user-role 部门负责人 \
  --product-domain 企业协同办公 \
  "希望新增跨部门审批抄送能力，减少流程遗漏。"
```

预期观察点：

- 输出应为“决策关口卡”或在决策关口中明显阻塞
- 建议应偏向先比较流程、培训、管理等非产品路径
- 不应直接把“做功能”当成默认正确答案

## 用例 4：ToC 增长型移动端需求

目的：

- 验证 ToC 语境下的表达是否自然
- 验证增长目标类需求是否仍然会被要求补基线和验证方式

运行：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model toc \
  --primary-platform native-app \
  --target-user-role 新用户 \
  --target-user-role 运营 \
  --product-domain 内容社区 \
  "想增加一个新手引导浮层，提升新用户发帖率。"
```

预期观察点：

- 仍应先拆分问题与方案
- 不应出现明显偏 ToB 的组织侧表达
- 应追问当前基线、行为阻塞和验证周期

## 用例 5：相对清晰的问题描述

目的：

- 验证当输入更接近问题本身时，文案不会机械套用“方案先行”

运行：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model toc \
  --primary-platform native-app \
  --target-user-role 新用户 \
  --target-user-role 内容运营 \
  --product-domain 内容社区 \
  "新用户注册后 3 天内发帖率偏低，运营怀疑他们没有理解首帖该发什么。"
```

预期观察点：

- 初步判断不应再强调“输入已经带出方案”
- 关键判断仍应补角色、现状流程和验证动作
- 审查卡应更像问题定义审查，而不是方案否定

## 用例 6：短输入线索

目的：

- 验证输入过短时不会做出过度推断

运行：

```bash
PYTHONPATH=src python3 -m pm_method_agent.cli \
  --business-model internal \
  --primary-platform pc \
  --target-user-role 运营 \
  "要做一个数据看板。"
```

预期观察点：

- 应明显提示“当前更像待展开的问题线索”
- 不应生成过于具体的验证结论
- 应把补充现状和目标作为首要动作

## 建议记录方式

每次跑完一条用例，建议至少记录这四项：

- 哪一句读起来别扭
- 哪个判断明显不准
- 哪一块信息过多
- 哪个本应出现的判断没有出现

## 当前阶段的通过标准

当前 CLI 阶段不要求“完全正确”，但至少要满足：

- 不同用例下的输出结构稳定
- 阻塞与放行时机大体合理
- 文案读感接近协作卡片，而不是报告或闲聊
- ToB / ToC / PC / 移动端语境有基本差异
