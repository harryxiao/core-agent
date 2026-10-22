# 设计：0301 记忆落盘跨进程合并与遗忘检索隔离

## 1. 约束与不变量

- `memory.jsonl` 仍是**单文件 JSONL**、每行一条完整条目（格式不变 ⇒ 旧文件可直接加载）。
- 既有原子性/逐行容错/字节往返不变（change `0206`）**逐字保留**。
- 「完好文件往返逐字节不变」：合并路径以**盘上顺序**为基线、同 id 覆盖不改变位置。
- 无新增配置键；两项修复**缺省生效**（缺陷修复，不给「关掉」的开关）。
- 记忆写入**不得**成为新的失败面：锁不可用 ⇒ 无锁写（fail-open），而非拒写。

## 2. D1 中性文件锁模块

**决定**：把 `exclusive_file_lock` / `try_exclusive_file_lock`（含平台实现 `_lock_fd` /
`_try_lock_fd` / `_unlock_fd` 与 `LockOutcome`）移入新模块 `src/core/filelock.py`；
`core/orchestration/state_files.py` 从该模块导入并 re-export（既有
`from core.orchestration.state_files import try_exclusive_file_lock` 的调用方与测试零改动）。

**理由**：`core.memory` 是 L2，`core.orchestration` 是 L3.5；从 memory 反向 import 编排层既
违反分层，也会触发 `core.orchestration.__init__` → `background` → `core.memory` 的循环导入。
复制一份锁实现则会出现两套平台分支（单点真源被破坏）。

**被拒方案**：
- 在 `_persist` 内做函数级 import（规避循环）——运行时安全，但依赖方向仍反了。
- 复制锁代码到 memory —— 两份 `flock`/`msvcrt` 分支，后续只改一处即漂移。

## 3. D2 变更集合并（不是快照覆盖）

**决定**：`FileBackend._persist(changed, deleted)` 在锁内：

```
base = 读盘（逐行容错，静默）
base[changed.id] = changed        # 覆盖不改变位置（dict 语义）
base.pop(deleted.id, None)
原子写 base
self._entries = base              # 采纳盘上最新集合
```

`put` / `put_many` / `delete` 只声明**本次变更**，不把整份内存快照当真相。

**代价**：每次落盘多一次全文件解析。写放大已是「全量重写」，解析与重写同阶；
`read()` 每轮一次强化落盘在真实体量（万条以内、单条数百字节）下为毫秒级。

**被拒方案**：
- **append-only journal**：更贴近 SDD §4.6，但需要改写加载、压实、删除与去重语义，
  超出 P0 修复面；留作后续形态。
- **按 mtime/size 跳过重读**：省一次解析，但存在「同纳秒同大小」的极小窗口导致覆盖；
  P0 优先正确性，不做。

**顺序语义**：同一 id 的并发写保持 **last-writer-wins**（后取锁者胜）；删除只删指定 id，
不会复活其他进程已删的条目（因为基线是盘上最新集合，而不是本进程启动时的快照）。

## 4. D3 锁语义：fail-open

**决定**：沿用 `exclusive_file_lock`（阻塞取锁；OSError 时无锁执行）。锁文件为
`memory.jsonl.lock`（`0600`，与状态文件同目录）。

**理由**：记忆写入发生在每轮收尾与每轮检索，**失败隔离**优先（SDD §5.1 要求 5：捕获失败只
告警、不得让节点失败）。fail-closed（如 `try_exclusive_file_lock`）会把锁争用升级为丢记忆，
不适合本路径。锁文件**不删除**（删除会让并发进程锁到不同 inode）。

**已知局限**：无锁降级期间仍有覆盖窗口（与修复前等价，但不再是常态路径）；Windows
`msvcrt.LK_LOCK` 等锁有 10s 上限，超时即降级。

## 5. D4 遗忘 = `forgotten` 标签 + 注入面排除

**决定**：

- `forget()` 对每个入选条目：先追加 `forgotten` 标签，再走既有 `migrate(L2 → L4, trace=
  forgetting.<id>)`（同一对象 ⇒ 标签随同一次落盘）；随后记一条同 trace 的效应，undo 时移除标签。
- `read()` 在**排名与预算之前**排除含 `forgotten` 标签的条目；新增仅关键字
  `include_forgotten: bool = False`（显式审计/回溯用）。
- `failure_lessons()` 同样排除含 `forgotten` 标签的条目（它是第二个注入面）。
- `audit()` / `session_chain()` / `memory list` 等**审计与诊断面**不过滤（墓碑语义：保留 id /
  时间 / 内容供追溯，只是不再召回）。

**为什么不把所有 L4 都排除**：L4 同时是压实、重要度闸门、L2 软上限的归档目标；若一律不可召回，
会静默改变三条既有行为与多个既有 Scenario（「冷数据按需加载」「失败条目已归档仍可读」等），
而 SDD 针对的是 **forget**。标签把「遗忘」与「归档」分开，改动面最小、语义最准。

**被拒方案**：
- 新 `MemoryEntry` 字段 `forgotten: bool` —— 落盘形状变化，牵动字节往返与旧行断言；
  标签是本仓既有的语义通道（`failure` / `steps` / `_PRESERVE_TAGS`）。
- 改 L4 全局语义 —— 见上。
- 删除 `failure` 标签来绕过教训读面 —— 混淆条目分类，且诊断面仍可见，语义更乱。

**可回滚性**：`forgetting.<id>` trace 回滚时，先移除 `forgotten` 标签、再由既有迁移 undo 迁回
L2 ⇒ 条目恢复可召回（与「遗忘可撤销」Scenario 一致）。

**旧数据**：历史 `forget()` 产生的 L4 条目没有标签 ⇒ 不具遗忘语义、仍可召回（无法追溯哪些是
遗忘产生的）；本限制登记于 known-risk。

## 6. 规格影响

- 「记忆后端落盘耐久」：新增跨进程合并段落 + 4 Scenario（跨实例合并 / 读取强化不覆盖 /
  删除不复活 / 锁不可用仍可写）。
- 「记忆遗忘（forgetting）」：归档改为「打 `forgotten` 标签 + 退出注入面 + 审计可见 +
  可回滚」，新增 3 Scenario（缺省不可召回 / 显式可见 / 非遗忘归档仍可召回）。
- 「情景链」：(h) 增加「含 `forgotten` 标签者缺省不返回」+ 1 Scenario。

## 7. 验证

- 新用例先红：跨实例合并 3 条、遗忘召回 4 条（`include_forgotten` 参数不存在 ⇒ TypeError）。
- 反证（`cp` + `md5sum`）：恢复旧 `_persist` ⇒ 合并用例红；去掉 `read()` 排除 ⇒ 遗忘用例红；
  去掉 `failure_lessons` 排除 ⇒ 教训读取用例红。
- 门禁：ruff / format / pyright / pytest 全量 + `openspec validate --all`。
