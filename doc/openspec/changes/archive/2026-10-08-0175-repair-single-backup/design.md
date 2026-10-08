# Design: repair-single-backup（修复备份「一次操作一份」）

> 规格：`doc/openspec/changes/2026-10-08-0175-repair-single-backup/specs/memory/spec.md`（MODIFIED）

## §1 决策

### D1 把 `_repair_session` 的**后半段**（备份 + 删除）提出循环 ⇒ 三段式

```
相 1  收集（每会话）   for sid in sessions:  材料 → 重抽 → 落新 → 收下该会话的 doomed
相 2  备份（**一次**）  doomed_all = ⋃ 各会话 doomed  →  一份 memory.repair.<一次时间戳>.jsonl
相 3  删除（**一次**）  for entry in doomed_all:  _delete_entry(entry)
```

`_repair_session` 相应改名 `_collect_session`，返回 `list[MemoryEntry]`（不再 `return None` 的早退分支散落
备份/删除逻辑）；`doomed` 判据（`_KEY_FACT_TAG in tags` + `session:<sid> in tags` + `id not in written`）
**逐字保留**，只是**求值时机**从「该会话落新之后」推迟到**全部会话落新之后**。

**为什么「收集完再算 doomed」不改变结果**：`written` 是**跨会话累积**的集合（`repair_stale_key_facts` 里
`written: set[str]` 单例、逐会话 update）；把 doomed 的求值推迟到全部落新之后，`written` 只会**更大**——
而 `written` 变大只会**缩小** doomed ⇒ 只会**更少删**、**不会**误删。相对现状（每会话算自己的 doomed），
差异仅在「会话 A 的落新 id 恰好等于会话 B 的旧 keyfact id」这一**跨会话同 slug** 情形 ⇒ 现状会删、
新形态**不删**。这是**正确的收紧**（那条 id 上此刻是 A 会话给出的新值，与 B 无涉）。

### D2 失败语义：**操作级全或无**（备份失败 ⇒ 一条都不删）

| 触发 | `0174`（现状） | `0175`（本 change） |
|---|---|---|
| 抽取器未注入 | 不删（**整次**） | 不变 |
| 某会话重抽抛错 | **该会话**不删，其余会话照删 | **不变**（抽取失败是**材料级**问题：该会话没有可用的新信息，不该因它阻断别的会话） |
| 备份写入失败 | **该会话**不删，其余照删 | **整次都不删**（`skipped["backup_failed"] = sorted(report.sessions)`） |

**为什么抽取失败仍保持会话级、而备份失败升为操作级**：两者性质不同 —— 抽取失败**只影响该会话**（它没落新、
故不该删它自己的旧条目），这是**局部**事实；而备份是**整次操作的回滚面**（一份文件里装着所有人的待删条目），
它落不成 ⇒ **整次操作不可回滚** ⇒ 谁的都别删。判据是「失败的作用域是否等于操作的作用域」，不是「统一从严」。

**已落的新条目在两种失败下都保留** —— 它们是正确的、脱敏后的新事实，且 `_write_key_fact` 走唯一写路径、
本就有 `EffectTracker` 可撤销 ⇒ 没有理由回滚。

### D3 备份文件名与格式**不变**（只把「次数」从 N 收敛为 1）

仍 `$CORE_STATE_DIR/memory.repair.<时间戳>.jsonl`、每行一条 `asdict(entry)` ⇒ 人工回滚口径（逐行解析回
`MemoryEntry`、`backend.put` 回去）**零改动**。`RepairReport.backup_path: str` **保持标量** —— 本 change 之后
它不再被覆盖（一份就是一份），字段无需改形（也就无需动 CLI 打印）。

`doomed` 并集为空 ⇒ **不落备份、不删除**（既有口径逐字保留：不产生空备份文件）。

## §2 落点

| 位置 | 变化 |
|---|---|
| `MemoryStore._repair_session` | → `_collect_session(session_id, extractor, report, written) -> list[MemoryEntry]`：重抽 + 落新 + **返回** doomed（备份/删除的代码**移出**） |
| `MemoryStore.repair_stale_key_facts` | 三段式：收集循环 ⇒ 并集 ⇒ **一次**备份（`except OSError` ⇒ `skipped["backup_failed"] = sorted(report.sessions)` + **返回**）⇒ 统一删除 |
| `RepairReport` / `_repair_backup_path` / `_delete_entry` / `_group_stale_by_session` | **零改动** |
| `src/core/entry.py` | **零改动**（报表字段与打印口径不变） |
| `src/core/memory/__init__.py` | **零改动** |

## §3 失败矩阵

| 场景 | 结果 |
|---|---|
| 单会话、有待删 | **一份**备份、该会话旧条目删净（与 `0174` 同） |
| **多会话**、各有待删 | **一份**备份（并集、一个时间戳）；`backup_path` 指向它；两会话各自删净 |
| **多会话**、备份写入失败 | **无任何删除**；`skipped["backup_failed"]` 列出**全部**会话；各会话已落的新条目保留 |
| 多会话、其一抽取失败 | 成功者照常（落新 + 参与并集备份 + 删除）；失败者不落库不删；`skipped["extract_failed"]` 记之 |
| 全部会话 `doomed` 为空 | 不落备份、不删除（仅有落新） |
| 无失效条目 | 零写入、零备份 ⇒ 幂等（不变） |
| `dry_run=True` | 只报告（不变） |

## §4 原则相容

- **P2 一切副作用可逆**：本 change **加强**之 —— 「一次性操作 ⇔ 一份回滚面」是一一对应的，`0174` 的 N 份备份
  里只有最后一份被报告提及，**回滚面信息不全**；收敛为一份后，报告路径即**完整**回滚面。
- **P3 进化局部化**：一个文件的一处方法重组；CLI / 规格面（除备份语义那句）/ 其余模块零改动。
- **P4 验证门 + 不可变世代**：规格先行（MODIFIED delta）→ 测试先行（多会话用例红）→ 四门禁 → 手工归档。
- **P5 记忆先行 / token 有界**：不新增任何界面；**减少**落盘文件数。
- **密钥红线**：备份内容仍是**已脱敏**的条目原文（承 `0174` D3）⇒ 不引入新明文面；本 change 不动脱敏判据。

## §5 测试计划（`tests/test_memory_keyfact_repair.py`，改 1 + 加 2）

| # | 用例 | 断言 |
|---|---|---|
| 1 | **新增** `test_two_sessions_share_one_backup` | 两个会话各有一条失效条目 + 各自材料 ⇒ 备份文件**恰好 1 个**；其行 id 集合 == 两会话待删 id 的**并集**；`report.backup_path` 指向该文件 |
| 2 | **新增** `test_backup_failure_blocks_every_session` | 同上两会话，`CORE_STATE_DIR` 指向**文件**（备份必失败）⇒ `report.deleted == []` **且** 两会话的旧条目**都在**；`skipped["backup_failed"]` 含**两会话**；新条目已落 |
| 3 | **改** 既有单会话备份用例 | 若其断言依赖「每会话一份」则收紧为「恰好一份」（需先核） |

**红态证据**：实现前跑新增用例 ⇒ ① 断言失败（备份文件数为 2 ≠ 1）；② 备份失败时**第一个**会话的条目已被删
（`report.deleted` 非空）⇒ 用例 2 失败。

## §6 局限（写进 ADR-0166 + `known-risk.md` §3）

① **备份失败即整次不删** ⇒ 一个坏目录（如磁盘满、权限错）会让**所有**会话都修不成 —— 以「不修」换「不错删」，
   方向恒为保守；
② **已产生的历史多份备份**（本次实跑的那两份）**不**被合并/清理（见 proposal §5）⇒ 库里**仍**存在多份旧备份，
   本 change 只保证**此后**每次操作恰好一份；
③ **跨会话同 slug 的收紧**（D1 末）⇒ `written` 跨会话累积会让 A 会话落的新 id 保护 B 会话的同名旧条目不被删；
   若两个会话对**同一实体**给出**不同**取值，后者（按会话顺序）覆盖前者 —— 同 slug 只有一条，**最后一个会话胜**，
   报告里两条 id 各自只出现一次（`written` 会含该 id、它不在 `deleted` 里）⇒ 用户从报告**看不出**发生了覆盖；
④ **不保证 `doomed` 并集的顺序** —— 备份行的顺序 = 会话遍历序 × 会话内 `_all_entries()` 序，**不**保证稳定
   （回滚按行不按序，故不影响正确性）；
⑤ 承 `0174` 的全部局限（重抽不确定 / 命名漂移 / 启发式脱敏等）—— 本 change 不触及。
