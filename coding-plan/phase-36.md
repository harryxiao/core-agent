# Phase 36：长任务硬化（批次 `0190`~`0195`，6 change）

> **状态**：✅ **全闭**（2026-10-11；6 条 change `0190`~`0195` 逐条独立收口：各自 change 目录 /
> ADR / 规格 delta（或规格中性）/ 四门禁 / 手工归档 / 单次提交）。
> **来源**：2026-10-11 用户问「记忆模块支持长任务运行吗（需要经历会话压缩、持续轮次的）」⇒
> 主代理据台账 + 两份 `file:line` 探索报告如实回答「**能跑，但续跑靠人、有几处会丢**」。
> 用户先裁决**先修台账失真**（六条 §3 局限改注，commit `3ff6f26`，Plan Task 1），再立本批次。
> **为什么是一批而非一条**：一条 change 跨 `orchestration` / `runtime` / `entry` / `loop` /
> `context` / `memory` **六个子包**，违反 **P3**（进化局部化与可归因）与「一 change 一提交」红线
> ⇒ 沿 **Phase 34 / 35 先例**：**一个批次、多条 change**，每条仍各自 change / ADR / delta /
> 四门禁 / 单提交。
>
> **红线（全批次）**：主方向封存 `exclude_source_prefixes=("beast.","pet")`（`runtime.py`
> **逐字不动**，phase-26）；密钥只引用不读取、**绝不**进日志/记忆（留痕只报 id / session 键，
> **绝不回显正文**）；零三方依赖；`config*.yaml` / `.claude/settings*.json` / `uv.lock` 等**不提交**。

---

## §0 用户裁决的两个设计岔口（AskUserQuestion，2026-10-11）

| # | 岔口 | 裁决 |
|---|---|---|
| 1 | 崩溃恢复的**续跑语义** | **启动扫描 + 呈现，续跑仍显式**（**不自动重执行** —— 守 **P2**：副作用不自动重放）⇒ change `0191` |
| 2 | 批次范围 | **6 条全做**（`0190`~`0195`） |

---

## §1 批次总览（执行顺序 = 编号顺序）

| # | change（归档目录） | capability | 一句话 | ADR | 台账 | 测试基线 |
|---|---|---|---|---|---|---|
| 1 | `0190-checkpoint-session-attribution` | `orchestration`＋`cli-ops` | `CheckpointFn` 加 session 形参（去 `"default"` 硬编码）＋ CLI `task` fresh 铸会话 / resume 用 checkpoint 会话 | ADR-0180 | E127 | 2208 → 2214（+6） |
| 2 | `0191-recovery-surfacing` | `durability`＋`cli-ops` | `Runtime.recover()` 启动接线：serve/task 启动扫描+呈现未完成任务（**不自动重执行**）＋坏任务降级不炸全扫 ＋「最新检查点」对齐 ts 序 | ADR-0181 | E128 | 2214 → 2219（+5） |
| 3 | `0192-compact-session-scope` | `loop`＋`context`＋`memory` | 轮内压实 `memory.compact()` **会话化**（与 `_maintain` 同口径）＋ `persist` trace 会话键化 ＋「多轮历史」docstring 诚实化 | ADR-0182 | E129 | 2219 → 2223（+4） |
| 4 | `0193-summary-tail-preservation` | `memory` | 滚动摘要 >2000 字**首尾保留**（修头截断销毁尾部；提升触发语义逐字不动）＋ 价值闸跳过补留痕 | ADR-0183 | E130 | 2223 → 2227（+4） |
| 5 | `0194-summary-injection-decoupling` | `loop` | `_load_summaries` 与 `history_turns>0` **解耦**（摘要通道独立于原文回放开关；缺省逐字不变） | ADR-0184 | E131 | 2227 → 2229（净 +2） |
| 6 | `0195-longtask-e2e-gates` | （架构测试，**规格中性**） | 长任务端到端门禁：压实→下一轮 prompt、越界尾部→摘要器 prompt、解耦回归（`skip_specs`，**零 `src/` 改动**） | ADR-0185 | E132 | 2229 → 2232（+3） |

**批次合计**：测试基线 **2208 → 2232**（**+24**）；`openspec validate --all` **31 passed / 0 failed**；
四门禁（`ruff check` / `ruff format --check` / `pyright` **0-0-0** / `pytest -q`）**逐条全绿**。

---

## §2 账目（E127~E132，逐条根因 → 修法）

| 台账 | 根因（一句话） | 修法（一句话） | 归档 |
|---|---|---|---|
| **E127** | 长任务断点链路上**三重会话身份不调和**：`CheckpointFn` 回调签名无 session ⇒ 检查点硬编码 `"default"`；CLI `task` 完全无会话身份 ⇒ 子任务轨迹/记忆/转录零归因 | `CheckpointFn`/`DoneFn` 增第 4 参 `session_id`（调用点在作用域内已有）＋ `runtime` 写实参原值（空串照传＝诚实「无会话」）＋ CLI `task` fresh 铸真会话 / resume 读 checkpoint 会话＋旧 `"default"` 兼容视作无会话 | `0190` / ADR-0180 |
| **E128** | **崩溃恢复能力齐备却无人触发**：`recover()` 零生产调用方；`_recover_incomplete` 对「快照全坏任务」整体 `raise` ⇒ 一坏任务中断整轮扫描；两种「最新检查点」定义并存（文件序 vs ts 序） | 启动扫描 + 呈现（**只报 task id、绝不自动重执行**，守 P2）＋ `try/except DurabilityError` 降级跳过（只报 task id）＋ `--resume` 统一 ts 序 | `0191` / ADR-0181 |
| **E129** | 同一条循环里**两套压实口径**：轮内 `_compact` 裸调 ＝ **全会话聚合**（顺手提炼他会话条目），`_maintain` 却会话化；`persist` trace 是**常量**非会话键；docstring 称「多轮历史」而实输入 `ctx.messages`（**仅本轮**） | 轮内改 `compact(session_id=ctx.session_id)`（空串实现逐字不动、全量语义保留给显式调用）＋ trace 改 `f"compaction.{key}"`（与 store 口径一致、零消费面被打破）＋ docstring / 契约注诚实化 | `0192` / ADR-0182 |
| **E130** | 滚动摘要越界即**无声销毁尾部**（最新结论所在）：`build_prompt` 纯头截断；价值门控跳过会话**零留痕**；且**越界同时是提升触发器** ⇒ 修法必须保触发语义 | `_elide_summary` **首尾保留**（头 ＋「⋯（中略 N 字）」＋ 尾 800，三段**恰为上界**）；触发判据**仍读全体长度**（逐字不动）；价值闸补 `warnings.warn` **只报会话键** | `0193` / ADR-0183 |
| **E131** | **关原文回放即连坐关掉记忆注入**：`_load_summaries` 门控含 `history_turns <= 0` ⇒ 长任务「只要摘要不要原文」的省 token 配置把摘要通道**整条关掉**且无留痕；注释自称「与 `_load_history` 完全同形」是**假** | 门控删 `history_turns <= 0` 一项（只留本职判据）；缺省 `>0` ⇒ 恒假 ⇒ **逐字不变**；错锚测试拆组订正 | `0194` / ADR-0184 |
| **E132** | 长任务链路「**产出 → 注入**」**两端分离无锚**：压实用例只断言记忆态、注入用例手播摘要 ⇒ 「压实产物真的进了下一轮 prompt」无断言；越界与解耦亦只测到对象层 | 新增 `tests/test_longtask_e2e.py` 三条端到端锚（真 loop ＋ 真 memory ＋ 桩 provider）＋ **防过空断言** ＋ **反证**（逐条临时回退确认转红）；**零 `src/` 改动** | `0195` / ADR-0185 |

---

## §3 逐条收口（协议一致性）

每条**必走**：spec-first（或**规格中性**判定）→ ADR → 先红测试 → 实现 → 四门禁 → 手工归档
→ 台账 ＋ 记忆 → **单次提交**。**规格 delta** 落点：`0190`→`orchestration`＋`cli-ops`；
`0191`→`durability`＋`cli-ops`；`0192`→`loop`＋`context`＋`memory`；`0193`→`memory`；`0194`→`loop`；
`0195` **规格中性**（`.openspec.yaml` `skip_specs: true`，沿 `0156` / `0189` 先例 ⇒ 无 delta）。

**归档方式**：`openspec archive` 在 symlink+WSL 下**必败** ⇒ 恒为**手工**（delta 合 canonical 时断言
**0 canonical 行丢失 / 0 Scenario 标题丢失**，再 `shutil.move` 进 `doc/openspec/changes/archive/`）。

**能力面 canonical 变化**（`doc/openspec/specs/`）：`orchestration`（检查点会话归因）＋ `cli-ops`
（task 会话 ＋ 入口启动呈现 ＋ `--resume` ts 序）；`durability`（recover 纯扫描语义 / 降级跳过 /
句柄标识任务）；`loop`（轮内压实按会话收窄 ＋ **摘要注入与历史回放解耦**）；`context`（压实产物
trace 携带会话键）；`memory`（循环内压实一律会话化 ＋ 摘要越界**首尾保留** ＋ 价值门控留痕）。
逐条 Scenario 计数见各自 change 的 delta 与 `doc/04-testing/test-cases.md` §103~§108。

**本批次的方法论教训（值得记）**：`0195` 初版把「越界首尾保留」的锚点误放在**循环注入的
system prompt**，实测**失败** —— `_elide_summary` 约束的是**摘要器 prompt**（压实**输入**），
注入面是**逐字**的。⇒ **若不做 e2e，此误解不会被发现**；端到端锚的价值正在于此。

---

## §4 遗留与显式不做

- **不在本批次范围**（用户已明示或本批次刻意划出）：
  - **自动续跑**（replay 重执行）—— 用户裁决①：**显式续跑**；副作用自动重放需审批面配合，另批。
  - **`ContextCompactor` 输入面扩多轮 / provenance 活化** —— 多轮历史已由三层滑窗（`0178`）＋
    记忆压实承载；扩面是 token 成本与去重新决策（`0192` 只**诚实化注记**，显式不做）。
  - **mid 提升通道** —— mid 有界瞬态；canonical 逃逸由长期摘要提升（`0153`）承载（`0193` 显式不做）。
  - **每会话节拍刷新**（ADR-0169⑦）—— 单活跃长任务场景已被当前节拍服务；多会话公平性维持
    「可接受」登记，另议。
  - **事实面预算 2048 / `pending` 通道**（gap ⑥ 残余）—— 装配预算内部，非长任务主轴。
  - **`scheduler.suspend/resume` 接线** —— 纯状态机转接、无持久化语义；接它需先定义续跑编排视图。
  - **checkpoint `trace_ids` 的新消费面** —— 仍只有 time-travel（进程内）；跨进程撤销是 ADR-0136
    既有局限。
- **本批次新增的已知局限**：逐条登记在 `coding-plan/known-risk.md` **§3**（按 ADR 归类：
  ADR-0180~0185）—— 例如 `0190` 旧 checkpoint `"default"` 不迁移、`0191` 呈现为「提示」非「托管」、
  `0192` provenance 仍为死面、`0193` 中略区仍不可逆丢失、`0194` 摘要读取仍要求转录已注入、
  `0195` 不覆盖 CLI resume 且桩 provider 不模拟推理。
- **§1 其余开账**：**E27**（IM 网关未接线）/ **E55** / **C7**（TTS）/ **E91** / **E100**（余运维动词）/
  **E101**（hooks 实现）—— **未闭**，仍登记于 `coding-plan/known-risk.md` §1。

---

## §5 关联

- 前置：`coding-plan/phase-35.md`（记忆面彻底完善，9 change `0181`~`0189`）·
  `coding-plan/known-risk.md`（§1 账目 E127~E132 已闭、§3 已知局限）；Plan Task 1 的台账失真改注
  见 commit `3ff6f26`（六条 §3 局限改注）。
- 逐条细节：`doc/openspec/changes/archive/2026-10-11-0190-*` … `…-0195-longtask-e2e-gates/`
  （各有 `proposal.md` / `tasks.md` / `design.md`，`0190`~`0194` 另有 `specs/`；`0195` 另有
  `.openspec.yaml`）；用例与红态证据：`doc/04-testing/test-cases.md` §103~§108。
- 测试锚点：`tests/test_entry.py` / `test_durability*.py` / `test_scheduler*.py` / `test_loop.py` /
  `test_context_compaction.py` / `test_memory.py` / `test_memory_summary_promotion.py` /
  `test_history_replay.py` / `test_longtask_e2e.py`。
