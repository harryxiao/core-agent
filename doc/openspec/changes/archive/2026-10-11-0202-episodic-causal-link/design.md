# Design 0202 — 情景链（时序相邻标注）

## 一句话

情景层补上**跨轮**结构：失败条目标注**同会话上一已记忆轮**（`after:<trace>`，**零记忆读**），
并提供按会话的**零效应只读链**。**因果不作推断** —— 只做确定性能做的。

## 为什么不做 LLM 因果推断（ADR-0192 的核心）

| 面 | LLM 因果推断 | 本 change 的确定性链 |
|---|---|---|
| 正确性 | **不可测**（只能测形状，无法验证「因为」是否成立） | 可验证（它就是一个 `trace_id`） |
| 可逆性 | 需**新增写路径**（P2 风险面） | 只加一个 tag ⇒ 与失败条目**同 trace** 可回滚 |
| 脱敏 | **新增面**：模型生成的失败归因散文是密钥易泄处（参 `diagnoser.py:_MAX_NOTE_CHARS` 的同型顾虑） | 零新散文 —— 只有 `trace_id` |
| 消费者增量 | `Diagnoser` 已按 `plugin_id` 归因 ⇒ 时序前驱**不增加信号** | 为只读面提供**跨轮**结构 |

⇒ 同 ADR-0041 的拒绝先例：**不可测正确性的新增模型调用，不因「蓝图要求」而做**。

## 语义与命名

标签 **`after:<trace_id>`** 的语义是**同会话内的时序相邻**，**不是因果**。
沿 ADR-0173「按机制本名命名」：机制是「上一已记忆轮的 trace」，不是「原因」——
写成 `after:` 则读作「因果」是**读者误读**；写成 `caused_by:` 则是**系统撒谎**。
**不自洽的因果声明比没有更坏。**

## 前序来源：进程内按会话表（**刻意零 I/O**）

```
DefaultLoop.__init__:  self._last_trace: dict[str, str] = {}
DefaultLoop.remember:  prev = self._last_trace.get(session_id)     # 标注用
                       ...（三条写入）...
                       self._last_trace[session_id] = trace_id     # 末尾更新
```

- `remember` **只有一个调用点**（`astream` 的本轮收尾）⇒ 一处维护，无并发争议。
- **不读记忆**：`MemoryStore.read` 会**强化 `reuse_count`**（`_reinforce` 是**落盘**写入，
  change `0187`）⇒ 为拿一个 `trace_id` 而检索 = 制造**新副作用**（违「只做确定性的」）。
  且 `MemoryBackend.search("")` 返回**写序**而非 `ts` 序 ⇒ 拿到的「上一条」未必真的是上一条。
- **更新不受开关门控**：写 `_last_trace` 是**零 I/O、零效应**的实例内登记，开着关着都不被读取 ⇒
  会话中途开开关也能立刻用上。**门控的只有标注的写入**。

## 存储决策：为什么是标签

| 方案 | 否决理由 |
|---|---|
| 新开 `loop.cause.<tid>` 条目 | 每次失败多一次写入换一个字符串；且是 `episodic` L2 ⇒ **进压实材料** |
| 给 `MemoryEntry` 加字段 | `MemoryEntry` 是跨后端**线上形状** ⇒ `FileBackend` 需迁移 |
| **标签** ✅ | 同 `id` 幂等；L2→L4 迁移原样存活；零 schema 变更；**消费面本就标签驱动** |

## 两处必须断言的交互（新标签不得遮蔽既有面）

1. `_PRESERVE_TAGS = frozenset({"failure"})` —— 失败条目 `tags` **仍含 `failure`** ⇒
   `_episodic_groups` 仍排除它 ⇒ **压实材料面未扰动**（这是 `0179` 的承重设计）。
2. `exclude_fact_tags = frozenset({"steps"})`（组合根生产值）—— 失败条目**无 `steps`** ⇒
   **仍进「相关事实」**。新标签 `after:…` 与 `steps` 无交集。

⇒ 两条都写成 Scenario 并落成断言：**新标签的加入不得改变该条目在两条通道上的去留**。

## 只读链：`session_chain`

```python
def session_chain(self, session_id: str = "") -> list[ChainNode]:
    nodes = [... for e in self._all_entries() if e.kind == "episodic" and e.layer == "L2"
             and (not session_id or e.session_id == session_id)]
    nodes.sort(key=lambda n: n.ts)   # list.sort 稳定 ⇒ 同 ts 保写入序
    return nodes
```

- 走 `_all_entries()`（冷区 + 热区），**不走 `read()`** ⇒ 零 `_reinforce`、零效应。
- `list.sort` 是**稳定**排序 ⇒ `ts` 相等（或 `0`）时保持 `_all_entries` 的**写入序** ⇒
  「`ts` 主序、写序次序」如实成立。
- 节点是 `frozen` dataclass（纯快照，不携带 store 语义）。
- **不**加入 `memory/protocol.py` 的 `MemoryStore` Protocol —— 与既有运维动词
  `repair_stale_key_facts`（change `0174`，同样只在具体类上）同处置；改 Protocol 会波及替身实现。

## 落点与开关

`loop/default.py`（`_last_trace` / `causal_links` / `remember`）· `loop/protocol.py`（无改动 ——
标签在 `tags` 里，不加字段）· `memory/store.py`（`ChainNode` / `session_chain`）·
`configuration/manager.py`（`loop.causal_links`，缺省 `False` + 独立访问器 + ConfigSpec 行 +
`_loop_errors` 校验）· `runtime.py`（注入四只 loop）。

## 已知局限（登记）

1. **进程内前序表** ⇒ 跨进程重启**链路断**；三路 loop 实例（main / sub / beast）各自一份 ⇒
   彼此之间**不连链**（各自会话独立，实践中影响有限，但如实登记）。
2. **只连失败轮** —— 成功轮不写 `after:`（成功轮本就没有失败条目）。故链是
   「失败轮的相邻关系」，不是「每一轮的相邻关系」。
3. **`Diagnoser(predecessor_lookup=…)` 未接线** —— 需对 `evolution/spec.md` 做约 36 行逐字
   MODIFIED（本批最高风险规格编辑）⇒ **登记为遗留**，不静默膨胀本 change。
4. **`session_chain` 无规格外消费者** —— 今日只有本 change 的测试与未来的运维/诊断视图可用它；
   本 change **不**新增 CLI / TUI 面（那是另一个 change）。
