# Proposal: memory-material-and-ref（记忆材料与引用语义）

> 本 change 由**实跑落库取证**驱动，不是设计推演。取证先推翻了我上一轮的主次判断
> （我原以为「L2 缺行动序列」是主因，证据显示它只影响**抽取器能看见什么**，而把 24 条关键事实
> 里的 **16 条**抹成 `<redacted>` 的是**另一条**路径 —— 见 §1），故本稿按**证据**重排。

---

## 1. Why —— 核实过的现状

**取证源**：`${CORE_STATE_DIR:-~/.core/state}/memory.jsonl`（183,654 bytes，真实会话落库，非构造样本）。

**代码定位**：

- 写材料（D-A）：`src/core/loop/default.py:674` `remember()` —— 本轮 L2 条目内容 =
  `"\n".join(_trajectory_line(item) …)[:2048]`，而 `_trajectory_line`（`loop/default.py:88`）对终止项返回
  `str(data["reply"])`、对其它项返回 `"round N ok"` / `"round N failed <err>"`。
  ⇒ **本轮 L2 条目字面上就是 `round 1 ok\n<最终回复散文>`**。
- 读材料（消费端）：`MemoryStore.compact()` → `_summarize_sessions()` → `_extract_key_facts(sid, entries)`，
  材料 = **该会话聚合的 L2 episodic 条目**；每条内容再经 `extract.py:29` `_MAX_ENTRY_CHARS = 400`
  节选后**才**入 prompt ⇒ 抽取器实际只看得到**每条 L2 条目的前 400 字符**。
  注：`memory/spec.md:359` 的「（即「行动与结果」产生的事件）」是在**解释 episodic 条目是什么**
  （承「无行动不记忆」），**不是**「L2 内容须含工具调用序列」的规范句 —— 故本 change 的 D-A 是
  **新增行为**，非「兑现既有承诺」（本稿初版此处措辞**过度声称**，已更正）。
- 脱敏判据（D-B）：`src/core/memory/extract.py` `scrub_key_fact()` —— 「给出 `ref` ⇒ `value` 一律
  `<redacted>`」，而 **`ref` 的形态未被校验**。

**实测（24 条 `L2|semantic|extraction`）**：

| 观测 | 条数 | 含义 |
|---|---|---|
| `value` 可用、无 `ref` | **8** | 正常抽取（`项目名称` / `源码目录` / `质量门禁` …） |
| `value = "<redacted>"` **且带自造 `ref`** | **16** | **被 D-B 抹掉** |

被抹掉的 16 条，其 `ref` 全是**模型自造的出处说明**，不是 `coeffect:<名称>`：

```
榴莲:            <redacted>   ref:round1:热带水果有哪些
泰国:            <redacted>   ref:round1:东南亚国家
问题现象:        <redacted>   ref:路由未命中事件描述
处理要求:        <redacted>   ref:路由未命中事件描述
Textual 依赖版本: <redacted>   ref:证据链第1条
round 5 执行结果: <redacted>   ref:会话事件
round 6 执行结果: <redacted>   ref:会话事件
```

**实体名的来源（按会话回看材料，决定了 D-A 该取什么形态）**：

| 会话 | 实体 | 该会话 L2 条目的实况 |
|---|---|---|
| `babd4a1a`（**8 条正常的**） | 项目名称 / 当前角色 / 规格文档目录 / 源码目录 / 开发流程 / 质量门禁 / 插件管理操作 / 会话退出方式 | 全部来自**助手自我介绍散文**：`round 1 ok\nHi! 👋 I'm the planning core for **CORE-Harness** — …` |
| `b19cd0e6` | 榴莲 / 山竹 / 泰国 / 越南… | 来自**闲聊散文**（水果 / 国家清单） |
| `8e01a4b9`（5 轮工具） | 问题现象 / 渲染组件 / Textual 依赖版本 / 控件是否支持表格 / round 5 执行结果 | 来自**分析散文** + 条目自身的 `round N ok` 前缀 |

⇒ **24/24 条 keyfact 的实体都源自「回复散文」，无一条源自工具调用或结果。**

三条独立结论：

1. **D-B 是主因**：`_PROMPT_HEAD` **从未**禁止非 `coeffect:` 的 `ref`，模型便顺手把「取自哪一句」
   当引用回填；`scrub_key_fact` 见 `ref` 非空即抹故 **16/24（67%）** 的取值被销毁。这是**纯自伤**：
   这些取值**不是**密钥，本可原样保留。
2. **D-A 是新增行为，且形态被证据约束**：材料确实只有 `round N ok` + 散文（实体名出现
   `round 5 执行结果` 即证），补行动序列有价值；**但**抽取器每条约 **400 字符窗**，
   若把行动序列**插到既有条目开头**，会把**产出全部 24 条的那段散文顶出窗口** ⇒
   很可能把仅有的好结果一起弄坏。故 D-A **必须另立条目**（见 §2）。
3. **D-C 随 D-A 必连**：行动序列含有界结果节选（`_output_excerpt = str(value)[:400]` 原文），
   落入 L2 即**新开一条外泄面**（L2 会被检索进 prompt、且 `memory.jsonl` 落盘）。

### 三个缺陷

| # | 缺陷 | 定位 | 后果 |
|---|---|---|---|
| **D-A** | **L2 材料无行动序列**（新增行为，非「兑现承诺」） | `loop/default.py:674` `remember()` | 材料 = `round N ok` + 回复散文 ⇒ 抽取器只能从散文抠实体（甚至把 `round N 执行结果` 当实体名）；「做了什么、得到什么」**从未**进记忆 |
| **D-B** | **`ref` 形态未校验** | `extract.py` `scrub_key_fact` + `_PROMPT_HEAD` | 模型自造出处说明 ⇒ 取值被判「引用式」**一律**抹成 `<redacted>`；实测 **16/24** |
| **D-C** | **行动序列的结果节选是原文** | `loop/default.py:207` `_output_excerpt` = `str(value)[:400]` | 见 §2 说明：**不是**被单独修的项，而是 D-A 的**必连项** |

**D-C 为什么不能切出去**：D-A 若把行动序列（含工具结果原文）写进 L2，就**新开一条外泄面** ——
工具结果可能是文件内容、命令输出、响应体，其中可含明文密钥。因此 D-A 的落地**必须同时**规定
写入前脱敏；这**不是**第三个独立任务，而是 D-A 的**安全前提**。

## 2. What Changes

1. **行动序列沉淀为「另立一条」L2 条目（D-A′ + D-C，一起落地）** —— `loop` 侧在既有轨迹条目
   （`loop.<trace_id>`，内容 **逐字不变**）之外，**另**写一条 L2 条目承载本轮行动序列，
   复用既有 `_action_steps` 渲染（`loop/default.py:110`，change 0171 引入，已供 notes 写回与
   SOP 提炼；工具名 + **有界参数摘要** + **有界结果节选**，整行 ≤300）。
   - **另立条目的理由（证据）**：抽取器每条约 **400 字符窗**，而**全部** 24 条 keyfact 的实体
     都产自轨迹条目的**散文**；把序列插到既有条目开头会**顶掉散文**。另立 ⇒ 两条各占一窗，
     既有散文抽取**零风险**。
   - **单一实现**：不写第二份渲染；notes 与 L2 用**同一函数**（「行动序列」只有一处定义）。
   - **有界**：承 `_action_steps` 既有上界（逐行 ≤300）+ 条目整体上界（`[:2048]`）⇒ 不随轮次增长。
   - **脱敏（D-C）**：写入前对渲染行跑**密钥形态判据**并替换命中子串为 `<redacted>`；判据与
     `extract.py` 的 `_looks_secret` **同源**（**提为公开**后复用，见 §3 待裁 3 ——
     loop → memory 是既有合法依赖方向，**不新增**分层跨越）。
   - **无工具调用 ⇒ 不写该条目**（`_action_steps` 对纯文字回复轮返回空 ⇒ 无行动不记忆）。
   - **落库仍走既有唯一写路径** `MemoryStore.write()`（记可撤销效应）—— 与既往逐字一致。
2. **收紧 `ref` 语义（D-B）** ——
   - **prompt 侧**：`build_extract_prompt` 明示「`ref` **只允许** `coeffect:<名称>` 形态；给不出这样的
     引用就**留空**，SHALL NOT 用出处说明充数」。
   - **store 侧（真正的信任边界）**：`scrub_key_fact` **新增 `ref` 形态判据** ——
     **非 `coeffect:<名称>` 形态的 `ref` 视为「无引用」**：弃用该 `ref`、不落 `ref:` 标签，取值
     随即按**裸值**判据处理（正常文本**原样保留**；密钥形态则走既有 fail-closed 整条丢弃 + warn）。
   - `docs`：`memory/spec.md`「结构化实体抽取（关键事实）」**MODIFIED**（措辞层面放宽，
     方向不变：over-redact 仍然成立 —— 只是「哪些算引用」被定义清楚）。

> **不放宽密钥红线**：本 change 使**更少**的东西被抹（正常取值回到明文），但**不**使任何**密钥形态**
> 的东西逃逸 —— 密钥形态的取值无论有无引用都仍旧脱敏或丢弃。方向仍是 over-redact。

## 3. 待裁（已定 —— 用户 2026-10-08 裁决）

- **待裁 1 —— 范围取哪几项？** ⇒ **D-A + D-B**（推荐案）。
  D-B 单独做即投入产出比最高（救回 16/24）；D-A 是「材料名实相符」这件规格承诺；D-C 随 D-A。
- **待裁 2 —— store 侧遇「非 `coeffect:` 形态的 `ref`」怎么办？** ⇒ **视为无引用**（推荐案）。
  与「靠 prompt 让模型别乱写引用」相比，**判据必须在 store**（注入的抽取器**不构成信任边界**，
  这是 0155 的既定原则）；与「整条丢弃」相比，「视为无引用」既不销毁正常取值、又保留 fail-closed
  对**密钥形态**取值的兜底 —— 两个方向都不放松。
- **待裁 3 —— D-A 按什么形态落地？判据怎么复用？** ⇒ **另立一条 L2 条目**；
  判据**提为公开**（`looks_like_secret` + `redact_secrets`，`core.memory` 导出）。
  形态理由见 §1 结论 2（400 字符窗证据）。复用理由：loop 直接调 `extract._looks_secret`
  会**跨模块私有边界**；上提为公开（`core/memory/__init__.py` 已有 `REDACTED` 等公开导出的先例）
  后 loop 走 `from core.memory import …`，依赖方向不变、私有面不破。
  `scrub_key_fact` 改用改名的公开判据 ⇒ **行为逐字不变**（纯重命名 + 新增 `redact_secrets`）。

## 4. 逐项对照（本 change **不**做的）

| 事项 | 为何不做 |
|---|---|
| 顺带放宽 `MAX_KEY_FACTS_PER_COMPACT`(8) / `_MAX_FACT_CHARS`(200) | 与本次缺陷无关；上界三处文档化，动它需独立取证 |
| 改 `_summarize_sessions` 的**门控**（`_below_gate`） | D-A 已经把材料修好；门控是否过紧**无**本次证据支持 |
| 把工具结果**全文**写入 L2 | 违 P5（token 有界）；`_action_steps` 的**有界节选**正是为此 |
| 改 `notes` 侧写回 | 0171 已收口；本 change 只**复用**其渲染函数，零行为变更 |
| 迁移/清理**既有** 16 条错误 `<redacted>` 条目 | 属数据修复，非契约；可用同实体重抽**幂等覆盖**自然刷新（`id` 不变） |

## 5. 切出（另立清单，本 change 不含）

- **D-B 的 prompt 侧**只是**辅助**（模型仍可能乱写）；**信任边界在 store** —— 若未来要让
  `ref` 支持 `coeffect:` 之外的真实引用源（如 `env:`），需独立 change 并在规格里定义其解析。
- **L2 条目的材料**还可再优选（如按相关性挑选而非全量），但**无**证据表明当前形态有损 ⇒ 不做。

## 6. Impact

- **delta**：`doc/openspec/specs/memory/spec.md`「结构化实体抽取（关键事实）」**MODIFIED**
  （+2 Scenario）；`doc/openspec/specs/loop/spec.md`「执行循环」**MODIFIED**（+3 Scenario）。
  二者均为**既有 capability** ⇒ 归档后 `openspec validate --all` 仍 **31/0**（capability 数不变）。
- **代码**：`src/core/memory/extract.py`（`_looks_secret` → 公开 `looks_like_secret` + 新增
  `redact_secrets`；`_PROMPT_HEAD` 收紧；`scrub_key_fact` 新增 `ref` 形态判据）、
  `src/core/memory/__init__.py`（导出两个公开判据）、
  `src/core/loop/default.py`（`remember()` 增**仅关键字**形参 `steps`，缺省 `()` ⇒ 既有调用
  **逐字不变**；有则另立条目并逐行脱敏）、`src/core/loop/protocol.py`（`Loop.remember` 声明同步）。
  **其余接口零变更**：`MemoryStore` / `KeyFactExtractor` / `TurnObserver` / `MemoryEntry`
  签名与调用点逐字不动；L2 轨迹条目 `id`/`tags`/`content` 逐字不变。
- **ADR-0164**（本文档集）；**台账 E110**；`doc/02-modules/memory.md` §3.4、
  `doc/03-interfaces/memory-interface.md` §3、`doc/04-testing/test-cases.md` §86（TC-MEM-REF）。
- **门禁基线**：`pytest` **1979 passed**（本 change 记增量）；四门禁直连二进制、禁 `uv run`。
- **风险**：**中低**。触碰 loop 写入内容与 memory 脱敏判据，**含密钥面** ⇒ 测试先行（红→绿）；
  可逆性由既有 `EffectTracker` 与同 trace 回滚保证，无新增不可逆副作用。
