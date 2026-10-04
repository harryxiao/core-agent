# 模块设计：持久性与恢复（Durability & Recovery）

> 对应规格：`doc/openspec/specs/durability/spec.md` ｜ 接口：`doc/03-interfaces/durability-interface.md`
> 定位：**横切层**，让智能体的执行态可保存、可恢复、可回滚，解决"进程崩溃即前功尽弃"的脆弱性问题。

---

## 1. 模块定位

CORE 的智能体执行是长时程、多步骤的：orchestration 负责任务级编排与断点续跑，loop 负责多轮推理-行动闭环。本模块统一提供 **checkpoint（检查点快照）、crash recovery（崩溃恢复）、time-travel（时间旅行）、retention policy（保留策略）** 四类能力，覆盖执行态级（执行上下文、任务状态、中间结果、记忆、会话状态）的持久化与恢复。

它是两个既有原语的**上层挂载能力**（不新建撤销机制，仅复用）：
- orchestration「断点续跑」——任务级挂起/恢复/取消，挂载检查点与崩溃恢复；
- tool-use「时间旅行回滚」——写类工具副作用级 EffectId undo 栈，挂载执行态级时间旅行。

---

## 2. 内部组成

```
Durability（横切层）
├── CheckpointManager   检查点管理：创建 / 列表 / 寻址
│   ├── Checkpoint      检查点 = 快照 + 元数据（唯一标识、时间戳、任务/会话归属、父检查点、pinned 标记）
│   └── Snapshot        执行态快照（执行上下文 / 任务状态 / 中间结果 / 记忆 / 会话状态）
├── CrashRecovery       崩溃恢复：检测中断 → 定位最近有效检查点 → 幂等恢复
├── TimeTravel          时间旅行：沿快照差异逆序撤销，复用 EffectId undo 栈
└── RetentionPolicy     保留策略：数量上限 / 时间窗口 / 存储配额，pinned 豁免
        └── 存储后端：MemoryBackend（L2 存储后端抽象，复用不新建）
```

---

## 3. 关键设计

### 3.1 检查点与快照

- 显式创建：上层在任意时刻调用创建检查点，当前执行态被持久化为快照，返回唯一标识，任务继续执行不被阻塞。
- 元数据与寻址：检查点携带时间戳、任务/会话归属、父检查点，支持按标识或元数据查询。

### 3.2 崩溃恢复

- 恢复流程：检测中断 → 定位最近有效检查点 → 恢复执行态 → 未完成步骤幂等续跑。
- 恢复幂等性：崩溃发生在步骤中途时，从检查点恢复后重放该步骤，不重复产生副作用。
- 检查点损坏降级：最近检查点损坏则回退更早有效检查点并告警，不因单点损坏阻塞恢复。

### 3.3 时间旅行

- 执行态级回滚：回滚到任意历史检查点，沿快照差异逆序撤销副作用。
- 与副作用级协同：回滚区间内的写类工具副作用，沿历史逆序调用各写类工具的撤销函数（复用 tool-use EffectId 可逆效应），状态与副作用一致回滚。不新建撤销机制。

### 3.4 生命周期与保留策略

- 保留策略自动清理：按数量上限 / 时间窗口 / 存储配额清理过期检查点（时间窗口或 LRU），释放存储。
- 关键检查点保护：pinned 检查点不受自动清理影响，直到显式取消标记。

---

## 4. 与 loop / orchestration 的挂接

```
loop（L3）四阶段：
  Act       ──► EffectTracker 记录 undo 栈（副作用级，供 tool-use 时间旅行回滚）
                 └── CheckpointManager 在轮次边界 / 长任务里程碑创建检查点
  Remember  ──► 每轮写 L2 记忆（无行动不记忆）
orchestration（任务级）：
  断点续跑   ──► 挂起时经 CheckpointManager 持久化执行上下文与中间结果
                 └── 恢复时 CrashRecovery 从断点幂等续跑
```

---

## 5. 错误处理与可靠性

- 持久化本身故障（磁盘满 / 后端不可用）不得阻塞主循环：降级为内存环形缓冲，异步重试落盘。
- **写入原子提交**：检查点落盘经「写同目录临时文件 + `os.replace`」提交，进程在写入中途崩溃不会出现半写/空文件 —— 既有检查点集合不受影响（change `0062`）。
- 检查点损坏：恢复时回退更早有效检查点并告警，不因单点损坏阻塞恢复。
- 存储配额触发：按保留策略自动清理，pinned 检查点豁免。

---

## 6. 关联

- 接口契约：`doc/03-interfaces/durability-interface.md`
- 规格：`doc/openspec/specs/durability/spec.md`
- 挂载：`doc/openspec/specs/orchestration/spec.md`（断点续跑）、`doc/openspec/specs/tool-use/spec.md`（时间旅行回滚）
- 测试：`doc/04-testing/test-cases.md`（DUR 系列）
