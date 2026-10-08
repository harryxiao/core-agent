# Design: memory-material-and-ref（记忆材料与引用语义）

> 规格 delta：`specs/memory/spec.md`（MODIFIED「结构化实体抽取（关键事实）」）、
> `specs/loop/spec.md`（MODIFIED「执行循环」）。取证与范围见 `proposal.md`。

---

## 1. 决策

| # | 决策 | 理由 |
|---|---|---|
| **D1** | 行动序列**另立**一条 L2 条目（**不**挤进既有轨迹条目） | 抽取器每条约 **400 字符窗**（`extract.py:29` `_MAX_ENTRY_CHARS`，**逐条**截断后才拼进 prompt）；24/24 条 keyfact 的实体都产自轨迹条目的**散文** ⇒ 插到开头会顶掉散文。另立 ⇒ **两条各占一窗**，既有散文抽取零风险 |
| **D2** | 密钥判据**提为公开**（`looks_like_secret` + 新增 `redact_secrets`） | loop 直接调 `extract._looks_secret` 会**跨模块私有边界**；`core/memory/__init__.py` 已有 `REDACTED` 等公开导出先例 ⇒ 上提后 loop 走 `from core.memory import …`，**依赖方向不变**、私有面不破 |
| **D3** | `ref` 形态判据 = **前缀 `coeffect:` + 名称非空** | 规格只承诺「形如 `coeffect:<名称>`」；不解析名称内部结构（解析无收益、徒增失败面）。**非该形态 ⇒ 视为无引用**（弃用 `ref`、不落 `ref:` 标签、取值回裸值判据） |
| **D4** | 脱敏粒度 = **子串替换**（非整行抹除） | 行动序列一行含「工具名（参数摘要）→ 结果节选」；整行抹除会连**工具名**一起丢（那正是「做了什么」的信息）。`redact_secrets` 逐 pattern 命中即换 `<redacted>`，保留结构 |
| **D5** | 行动序列条目 `id = f"loop.steps.{trace_id}"`、`tags=["loop","steps"]`、`source` / `trace_id` / `session_id` 与轨迹条目**同值** | 同 trace ⇒ 按 trace 回滚**一并**可逆（P2）；同 `session_id` ⇒ 会话隔离与压实归组口径一致；`kind` 取缺省 `episodic` ⇒ **自然成为压实材料**（本 change 的目的） |

## 2. 实现落点

### 2.1 `src/core/memory/extract.py`

- `_looks_secret` → **`looks_like_secret`**（公开），模块内调用点同步；**行为逐字不变**。
- 新增 **`redact_secrets(text: str) -> str`**：逐 `_SECRET_PATTERNS` 以 `REDACTED` 替换命中子串。
- 新增私有 **`_is_coeffect_ref(ref: str) -> bool`**：`ref.startswith("coeffect:") and bool(ref[9:].strip())`。
- `_PROMPT_HEAD` 收紧：明示「`ref` **只允许** `coeffect:<名称>`；给不出就**留空**，SHALL NOT 用出处说明充数」。
- `scrub_key_fact` 第 2 步：`if ref and _looks_secret(ref):` → **`if not _is_coeffect_ref(ref):`**
  （**一条判据覆盖两义**：密钥形态的 `ref` 必然不满足 `coeffect:` 形态 ⇒ 旧的「像密钥的 ref 弃用」
  被**包含**而非丢失）。其余步骤（含 `_truncate_value` 首尾保留、先脱敏后截断）**逐字不动**。

### 2.2 `src/core/memory/__init__.py`

导入与 `__all__` 增加 `looks_like_secret`、`redact_secrets`（沿用现有导出风格）。

### 2.3 `src/core/loop/default.py`

- 新增常量 `_MAX_MEMORY_ENTRY = 2048`（既有轨迹条目的 `[:2048]` 字面量同时改用 ⇒ **单一真源**；
  行为不变）。
- `remember(self, trace_id, trajectory, *, session_id="", steps: Sequence[str] = ()) -> None`：
  - 既有轨迹条目（`loop.<trace_id>`）的写入路径与内容 **逐字不变**；
  - `steps` 非空时，**另**写一条 L2 条目：`content = "\n".join(redact_secrets(s) for s in steps)[:_MAX_MEMORY_ENTRY]`，
    `id=f"loop.steps.{trace_id}"`、`tags=["loop","steps"]`、其余字段同轨迹条目；
  - `steps` 缺省 `()` ⇒ **行为与变更前逐字一致**（既有调用点与 `tests/test_memory_namespace.py` 不受影响）。
- 调用点（`default.py:437`）：`self.remember(trace_id, [...], session_id=session_id, steps=_action_steps(ctx))`

### 2.4 `src/core/loop/protocol.py`

`Loop.remember` 声明同步新增 `steps` 形参（仅关键字、有缺省）。

## 3. 失败矩阵与降级

| 情形 | 行为 |
|---|---|
| `steps` 为空（纯文字回复轮） | **不**写第二条（无行动不记忆）；轨迹条目照常 |
| `self._memory is None` / `trajectory` 为空 | 既有早退**逐字不变**（两条都不写） |
| 行动序列超长 | 逐行 ≤`_MAX_STEP_LINE`(300)（既有）+ 条目 ≤`_MAX_MEMORY_ENTRY`(2048) |
| 行内命中密钥形态 | 该**子串**换 `<redacted>`；行的其余部分（工具名 / 路径）保留 |
| `redact_secrets` | 纯函数（正则替换），**不抛**；无副作用 |

## 4. 与既有原则的相容性

- **P2 可逆**：第二条条目经同一 `MemoryStore.write()`（既有唯一写路径）记录可撤销效应，
  且与轨迹条目**同 `trace_id`** ⇒ 按 trace 回滚一并逆转。
- **P5 token 有界**：条目有界（2048），且入 prompt 时再经 400 字符节选。
- **密钥红线**：写入 L2 **前**脱敏（L2 会被检索进 prompt 且 `memory.jsonl` 落盘 ⇒ 必须在写入侧拦），
  判据与关键事实抽取**同源**（单一实现）、方向 over-redact。
- **P1/P3**：零新增插件、零新增分层跨越；不引入第三方依赖。

## 5. 测试（红 → 绿，先写测试）

- `tests/test_memory_ref_shape.py`（memory 侧）
  1. 非 `coeffect:` 形态 `ref` + 正常取值 ⇒ **取值保留**（不抹）、不落 `ref:` 标签、条目照常落库；
  2. 非 `coeffect:` 形态 `ref` + 密钥形态取值 ⇒ **整条丢弃** + `warnings.warn`（含实体名、不含取值）；
  3. `coeffect:<名称>` 形态 `ref` ⇒ 取值<redacted>、落 `ref:` 标签（**既有行为回归**）；
  4. `looks_like_secret` / `redact_secrets` 公开判据：命中子串被替换、非命中文本逐字不变；
  5. `redact_secrets` 多个 pattern 同现 ⇒ 各自替换。
- `tests/test_loop_memory_sequence.py`（loop 侧）
  6. 有工具调用的一轮 ⇒ 除轨迹条目外**另**一条 L2 条目，内容含 `工具名（…）→ …`，轨迹条目内容**逐字不变**；
  7. 纯文字回复轮 ⇒ **不**另立条目；
  8. 行动序列含密钥形态串 ⇒ 该子串为 `<redacted>`（整条不含明文）；
  9. `steps` 缺省（旧调用形态）⇒ 只写轨迹条目（**向后兼容**回归）；
  10. 超长行动序列 ⇒ 条目长度 ≤ `_MAX_MEMORY_ENTRY`。
- **红态证据**：实现前先跑 ⇒ 新增用例全红（记入 `04-testing`）。

## 6. 局限（写进 ADR + known-risk §3）

① **脱敏判据是启发式**：不符合任何 `_SECRET_PATTERNS` 的内联凭据（如自定义口令）仍会入 L2 并落盘；
与既有 `code_run` 目标同行暴露口径一致（0169 局限②），**根治需在工具侧打标**，另立。
② **`ref` 形态只认前缀**：`coeffect:` 之外的**真实**引用源（如 `env:`）当前一律视为无引用 ⇒
若未来要支持，需独立 change 定义其解析与脱敏语义。
③ **每轮多一条 L2 条目** ⇒ 压实材料条数与 token 成本上升（有界；无「合并同类轮」策略）。
④ **400 字符窗未改**：本 change 靠「另立条目」绕开窗口竞争，**不**放宽 `_MAX_ENTRY_CHARS`；
若某轮行动序列超 400 字符，抽取器仍只看前 400（但比「完全没有」是净增）。
⑤ **`round N 执行结果` 类实体名不再产生**（材料变了），但**既有 16 条错误条目不会被本 change 清理**
（同实体重抽会幂等覆盖刷新；不主动迁移，见 proposal §4）。
