# Self-Improvement 理念对比：Self-Harness / ModularRSI ↔ CORE-Harness

> 本文对比两篇论文的 "self-improvement" 核心理念，与 CORE-Harness（core-agent）架构的自我迭代理念是否一致。
> 结论先行：**一致，且是"移植级"的一致**——CORE-Harness 的进化引擎直接以 ModularRSI 为蓝本落地；
> Self-Harness 的「固定模型只改 harness」虽是同源理念，但未被架构文档显式采纳（0 处引用），二者呼应属理念层殊途同归。
> 在此之上，CORE-Harness 叠加 GA 的分层记忆，独创「结晶经济」闭环，构成相对两篇论文的单点超越。

---

## 0. 对照对象

| 编号 | 名称 | 定位 |
|---|---|---|
| 2606.09498 | Self-Harness（上海 AI Lab） | 固定模型与评估器，只让 harness 自我改进 |
| 2609.14857 | ModularRSI | 把递归自我改进（RSI）泛化到 harness，强调可泛化 |
| — | CORE-Harness（`core_harness_architecture.md`） | 无特权核心的插件化智能体运行时，融合三源 |

---

## 1. 两篇论文的 self-improvement 核心理念

### 1.1 Self-Harness（2606.09498）

**一句话：性能 = 基础模型 + harness；固定模型与评估器，只让 harness 自我改进。**

- **对象**：改进的是**非参数脚手架（harness）**，模型权重与评估器完全冻结。
- **机制**：三段式循环
  1. **Weakness Mining**：从失败轨迹提炼 `verifier-grounded failure signature φ(r)=(c,q,m)` 并聚类；
  2. **Harness Proposal**：用**同一个模型**生成 K 个多样化但**最小化编辑**（每编辑只改一个"可编辑表面"）；
  3. **Proposal Validation**：回归测试，接受规则 `Δin≥0 ∧ Δho≥0 ∧ max>0`（不得牺牲任何维度）。
- **核心信条**：evaluator / optimizer 分离；只动 harness、不碰权重 → 安全、可解释、可归因。

### 1.2 ModularRSI（2609.14857）

**一句话：把 RSI 泛化到 harness，强调"可泛化的自进化"。**

- **机制**：三阶段
  1. **Contrastive Trajectory Sampling**：同一任务 rollout，对比成功/失败轨迹；
  2. **Module-wise Harness Evolution**：把 harness 拆成 **5 个功能模块**独立并行进化，修改范围受限；
  3. **Validation Gates**：程序检查 + 泛化 diff review + 执行验证。
- **补强**：Cross-Module Integration + Function Library Management（merge 去重 + task-aware composition）；**benchmark-disjoint 进化协议**（2000 实例，留出集与进化数据不相交）防死记；跨模型迁移。

---

## 2. CORE-Harness 的自我迭代理念（读原文核实）

顶层 `core_harness_architecture.md` 开宗明义「融合三源」：

> dsh 的「一切皆插件+可逆组合」作**基底**，ModularRSI 的「对比诊断+验证门+不可变世代」作**进化引擎**，GA 的「分层记忆+技能结晶+最小种子」作**记忆与效率策略**。

进化引擎 = `doc/02-modules/evolution.md` + `specs/evolution/spec.md`，核心是**四阶段闭环 + 结晶经济**：

- **四阶段**：观测 → **诊断**（Diagnoser 归因到单个插件）→ **提案**（Proposer 生成世代化候选）→ **验证**（Validator 过验证门）→ **评测**（Evaluator 留出集防退化）；
- **结晶经济（Crystallization Economy）**：`经验(L4) → 技能/SOP(L3) → 插件(L0/L1)` 向上**结晶**，失败沿反方向**可逆溶解**；「记忆与代码是同一光谱的两端」。

---

## 3. 一致性判断

### 3.1 ✅ 逐条对齐（ModularRSI → CORE-Harness 的 L4 进化引擎）

| ModularRSI（2609.14857） | CORE-Harness 进化引擎 |
|---|---|
| Contrastive Trajectory Sampling（同任务成败对比） | 对比诊断「对比同任务成败轨迹，跨任务聚合证据」 |
| Module-wise Evolution（拆 5 模块、限修改范围） | 模块级提案「归因到**单个插件**、修改范围受限」 |
| Validation Gates（程序检查+review+执行验证） | 验证门「review + 运行时测试，不过门不发布」 |
| benchmark-disjoint（留出集不相交） | 留出评测「留出集与进化数据不相交，防过拟合」 |
| immutable generation（不可变世代） | 世代化产物「不可变、带 delta、可回滚」 |

这不是"理念相似"，而是 CORE-Harness 架构文档**明确标注来源为 ModularRSI（arXiv 2609.14857，25 处引用）**，四阶段闭环 + 验证门 + 不可变世代全部是其落地实现。

### 3.2 ⚠️ 与 Self-Harness 的关系：理念同源，未被显式采纳

- Self-Harness 的「**固定模型只改 harness、evaluator/optimizer 分离**」，在 CORE-Harness 中体现为「**无特权核心 + 进化只碰单个插件、永不碰 L0 基底**」——精神完全一致；
- 但架构文档 **0 处引用 Self-Harness（2606.09498）**，只引用了 dsh/Cordis（2608.25512）、ModularRSI（2609.14857）、GA（2604.17091）。

### 3.3 🌟 CORE-Harness 的独特增量（超越两篇论文）

1. **结晶经济是融合点，非任何单篇所有**（架构 §8 明示"本架构新增"）：把 ModularRSI 的「代码进化」和 GA 的「记忆沉淀」统一成**同一光谱两端**——ModularRSI 改代码但缺记忆沉淀，GA 沉淀记忆但不改代码，CORE-Harness 用「结晶/溶解」打通两者。
2. **可逆溶解**：借 dsh 的可逆 effect，失败的进化不是单纯回滚，而是**降级回记忆并保留"为什么失败"**，永不丢历史。
3. **受控递归**：进化引擎自身也是插件 → 可进化自己，但受 L0 宪章 + 验证门约束。

---

## 4. 结论

**一致，而且比"一致"更彻底**——CORE-Harness 的自我迭代理念**直接以 ModularRSI 为蓝本落地**（四阶段闭环 + 验证门 + 不可变世代 + 留出评测逐条对应）；Self-Harness 的"固定模型只改 harness"虽是同源理念但未被显式引用，其与 CORE-Harness 的呼应属**理念层的殊途同归**。在此基础上，CORE-Harness 额外叠加 GA 的分层记忆，独创「结晶经济」闭环，把"会记"与"会进化"统一起来，这是它相对两篇论文的单点超越。

---

## 5. 证据索引

- 架构融合三源：`core_harness_architecture.md` §0/§8/§9
- ModularRSI 引用（25 处）：`core_harness_architecture.md` §L4 层、§148
- 进化引擎四阶段：`doc/02-modules/evolution.md` §1
- 四阶段补全 change：`doc/openspec/changes/0008-evolution-four-stages/proposal.md`
- 进化规格 7 条 Requirement：`doc/openspec/specs/evolution/spec.md`
- Self-Harness 引用计数：0 处（rg 全工程核验）
