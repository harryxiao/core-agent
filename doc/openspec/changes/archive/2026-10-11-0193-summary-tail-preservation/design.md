# Design 0193 — 滚动摘要首尾保留（尾部不销毁）+ 价值闸留痕

## 1. 问题定位（P3）

| 面 | 事实 | 缺口 |
|---|---|---|
| `summarize.py:48` | `prior.content[:MAX_SUMMARY_CHARS]` | **纯头截断** ⇒ 越界后尾部（最新结论）永不再进 LLM |
| `store.py:700-703` | 越界即**提升触发**（`_deliver_promotion`） | 修法须**保触发语义**（判据读全体长度） |
| `store.py:118-125` / `:579-580` | 价值闸跳过 = `continue` | 静默跳过，运维无留痕 |

## 2. 设计决策

### 2.1 首尾保留（`_elide_summary`）

```python
_SUMMARY_TAIL_CHARS = 800   # 尾部保留预算

def _elide_summary(content: str) -> str:
    if len(content) <= MAX_SUMMARY_CHARS:      # 未越界 ⇒ 逐字全文（兼容性红线）
        return content
    omitted = len(content) - MAX_SUMMARY_CHARS  # 上界之外的字数
    marker = f"\n⋯（中略 {omitted} 字）\n"
    head = content[: MAX_SUMMARY_CHARS - _SUMMARY_TAIL_CHARS - len(marker)]
    tail = content[-_SUMMARY_TAIL_CHARS:]
    return f"{head}{marker}{tail}"
```

- **总长恒 = `MAX_SUMMARY_CHARS`**（`head + marker + tail` 三段相加恰为上界）⇒ 上界（token 有界）
  **不破**，`MAX_SUMMARY_CHARS` 语义（「投喂摘要器时的节选上限」）**保真**。
- **头 ~1200 / 尾 800**：`head = 2000 - 800 - len(marker)` ≈ 1186（marker ≈ 14 字）—— 头略少于
  1200、尾恰 800，**头大尾小**符合「既有结论在前半段、最新结论在尾部」的摘要形态。
- **尾部逐字保真**：`content[-800:]` 与原文末段逐字一致 ⇒ 最新结论不再被无声销毁。
- **单趟无循环**：`marker` 长度由 `omitted`（= `len - 2000`，与 head 选择无关）决定 ⇒ 无循环
  收敛问题，实现确定性。

### 2.2 触发语义逐字不动

`_deliver_promotion`（`store.py:700-703`）的越界判据读 `len(prior.content)`（条目**全体长度**）
与 `len(summary)`，**不读本节选** ⇒ 首尾保留**不触碰**该判据。`_commit_summary` 落库**仍不截断**
（canonical 存全文、投喂有界 —— 两条边界正交，本 change 只动「投喂」那条）。

### 2.3 价值闸留痕

`_summarize_sessions` 的 `if _below_gate(entries, scores): continue` 前补：

```python
warnings.warn(f"memory compaction skipped low-value session {sid!r}", RuntimeWarning, stacklevel=2)
```

- **只报会话键**（`sid!r`），**绝不**回显摘要 / 事件正文（承密钥红线）。
- `sid` 可为空串（缺省分组）⇒ 照报 `''`（仍是键，非正文）。
- 不改变门控**判据**与**结果**（仅补留痕，跳过行为逐字不变）。

### 2.4 mid 提升通道显式不做

mid 层（`compaction.mid.<key>`）由 `summarize_slice(session_id, entries, max_chars=…)` 预截断
（`store.py:477` `[:max_chars]`），是**有界瞬态层**；canonical 逃逸由**长期摘要提升**（change 0153）
承载。本条保长期摘要「越界不销毁尾部」后，该提升路径即在正确前提上成立 ⇒ **mid 无需另一条提升通道**。

## 3. 规格落点

`memory`「记忆压实」：节选**首尾保留**条款（含越界判据读全体长度）+ **价值门控留痕**条款
+ 2 Scenario。

## 4. 验证

- 红测试：>2000 prior 含尾段 + 中略标记 + 总长 ≤ 上界；≤2000 逐字；触发仍准点；留痕只报会话键。
- 四门禁（直连二进制）；`openspec validate` → 手工归档（0 行丢失 / 0 Scenario 标题丢失）。
