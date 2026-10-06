# 提案 — 落地只认门禁全过的制品（fail-closed 收口）（change 0127 / phase-34 E69）

## 背景

`coding-plan/phase-34.md`（全系统架构走查缺陷账本）登记的 **E69**（低危、**fail-open 潜伏**）：
`EvolutionExecutor.commit` **从不读 `record.gated`** ⇒ 未过门的制品也可能被放行落地。

| # | 一手事实（2026-10-06 复核，行号已核实） | 后果 |
|---|---|---|
| 1 | `evolution/models.py:79-80` 明写「`gated` 标记『门禁全过、可复核』，`committed` 标记『已复核落地』—— **`commit` 只认前者为真者**」 | 契约**写在模型 docstring 里**，实现未兑现 |
| 2 | `evolution/executor.py:183` 走 `self.staged(...)`；`:215-218` 该访问器**仅滤 `committed`** | 未过门（`gated=False`）的残留制品被当成「待复核」 |
| 3 | `evolution/executor.py:178-211`（`commit` 全程）**从不读 `gated`**；全仓 `gated` **只有写**（`:171` 筹备产物 / `:205` 落地产物）**无读** | 同一 |
| 4 | `evolution/pending.py:233-239` `staged()` docstring 写「**待复核**制品（**门禁已过**、尚未落地）」，过滤条件却**只有 `not committed`** | 呈现面（`evolve pending`，`entry.py:1149`）同样会把未过门制品列为待复核 |
| 5 | `evolution/executor.py:152` `attach_implementation(record)`（此时 `gated=False`）**早于** `:158 _run_gates`，且 `:219-221` 随即 `flush()` | 筹备一旦中断，台账里**已经**有一条 `gated=False` 的持久制品 |

**窗口（可达）**：门禁执行**抛异常**（或进程在门禁跑动中被杀）⇒ `_run_gates` 的 `finally` 已回退
工作树，但 `clear_implementation`（只在 `:159-160` 的「门禁返回失败」分支调用）**不跑** ⇒ 台账留下
一条 `gated=False` 的制品；此时工作树与 `record.before` **一致**（已回退）⇒ 重启后 `commit` 的
**漂移校验通过**、**复核单可正常签发**，于是**从未跑过门禁的补丁被永久应用**。

**契约面现状**：`evolution/spec.md`「架构级候选的原生实施（可选）」Requirement 的「复核（review）」
「落地（commit）」两条只规定审批单与漂移，**未**规定「只有门禁全过的制品才可复核 / 落地」⇒ 按本仓
SDD 惯例 **规格先行**（非 `skip_specs`）。

## 变更目标

**`evolution/spec.md`「架构级候选的原生实施（可选）」Requirement MODIFIED**（两条口径 + 1 个 Scenario）：

1. **待复核定义收窄** —— **待复核**仅指**门禁全过**（`gated=True`）的制品；未过门的制品 SHALL NOT
   被列为待复核项（呈现面与落地面同一判据）。
2. **落地 fail-closed** —— 落地 SHALL 只认门禁全过的制品；无制品**或**制品未过门（含筹备异常 /
   进程中断留下的 `gated=False` 残留）⇒ SHALL 结构化拒绝（`IMPLEMENT_REJECTED`）并提示重新筹备，
   SHALL NOT fail-open。

## Non-goals

- **不改两阶段结构**：筹备（补丁 → 守卫 → 应用 → 跑冻结门 → 回退）与落地（复核关 → 漂移校验 →
  应用制品 → 记可逆效应 → `implemented`）**逐字不变**。
- **不改门禁口径**：门禁命令仍取**单一真源** `GATE_COMMANDS`、仍经独立执行面（子进程）运行；
  本 change 只加「**读**」`gated` 这一判据。
- **不改守卫**：范围守卫（`_scope_violation`）与路径 / 归因一致校验不动。
- **不补「门禁中断即自动清账」**：`_run_gates` 异常路径**不新建** `clear_implementation` 调用 ——
  残留制品由本 change 的**读取面判据**挡住（另见「已知局限」）。
- **不动 `committed` 语义与已落地制品的可见性**。

## 判据与取舍

**判据只加在读取面（两个「待复核」访问器），不在 `commit` 里另立分支。** 理由：
`gated` 的语义已由模型 docstring 与 `pending.staged()` docstring 定义为「待复核」的**构成要件**
（缺它就不是待复核），把判据收在两个访问器即**单点**生效 —— `commit` 与 `evolve pending` 同时
正确，且不产生「同一制品在 A 面可复核、B 面不可复核」的双口径。

**拒绝理由沿用既有 `IMPLEMENT_REJECTED`（不新增错误码）**：失败因由是「没有可复核的制品」——
与「未筹备直接落地」是**同一件事**（`staged` 为 `None`），操作面提示（先 `--dry-run` 筹备）也
正是本窗口的正解；新增码只会让同一处置路径分叉出两个名字。

**不静默丢弃残留制品**：`gated=False` 的记录**仍留在台账**（`implementation_of` 可见），本 change
只让它**不可复核 / 不可落地**——留痕优于抹掉（抹掉会让「筹备中断过」这一事实消失）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 正常路径（筹备成功 ⇒ `gated=True`）被误伤 | `prepare` 的产物**恒** `gated=True`（`:171`）；既有 4 条筹备 / 落地用例即回归守门 |
| 呈现面过滤导致「台账有、列表无」的困惑 | 这正是**规格要求**（未过门 = 非待复核）；`implementation_of` 仍可查得，且落地报错提示重新筹备 |
| 改动热路径 | `commit` / `staged` 均**只由操作面显式驱动**（`core-agent evolve implement`），不在 loop 节拍上 |

## 兼容性

- `EvolutionOutcome` / 候选状态词表**零变更**。
- 落地的既有判据顺序（复核关 → 漂移校验）**逐字不变**，本 change 只是让「制品不存在」的判据覆盖面
  从「未筹备」扩展到「未筹备 **或** 未过门」。
- `evolve pending` 的**输出形状不变**，仅在**异常残留**这一此前错误的输入上不再列出该制品
  （**这正是本 change 的目的**）；正常流程输出逐字不变。
