# Change: 会话标识透传至记忆沉淀（session-scoped memory）

## Why

`coding-plan/phase-19.md` 账本 A2 / E2（同一根因）：**会话维度在生产路径上从未生效**。

- **写入侧恒空串**：`LoopPlugin` 三入口（`run`/`arun`/`astream`）只收 `user_input`，会话标识
  **不进循环**（`src/core/loop/protocol.py:18-24`）；`DefaultLoop.remember` 因此构造
  `MemoryEntry` 时不带 `session_id`，落为 dataclass 缺省 `""`（`memory/protocol.py:32`）。
  生产上所有会话的 L2 沉淀挤进同一个空串分组。
- **后果**：`CORE-MEM` 的「压实按会话聚合」「固化按会话门控」「遗忘按会话衰减」三项口径
  （`memory/spec.md:68-71`、`:108-111`）在真实数据上退化为**单分组**——即规格写了会话，
  运行时只有一个"会话"。
- **读侧错位**：`UIAPILayer.get_memory(session_id)` 把会话 ID 当**检索 query** 用
  （`src/core/ui/api.py:113-117`），而非按会话归属过滤；`compact(session_id)` 为占位
  no-op（`:119-121`），而 `MemoryStore.compact` 的真实压实早已实现
  （`memory/store.py:166-190`，接口文档 `memory-interface.md:107`）。

## What Changes

- **loop 接受会话标识**（loop，MODIFIED「执行循环」，`CORE-LOOP-R1`）：三入口（`run`/`arun`/
  `astream`）接受可选 `session_id`（缺省空串 = 未归属），「记忆」步把该标识写入本轮沉淀
  L2 条目的 `session_id`。**标识随调用传递、不驻留循环实例**（单实例可并发服务多会话）。
- **L2 写入落会话归属**（memory，MODIFIED「分层记忆模型」，`CORE-MEM-R1`）：L2 写入 SHALL
  记录条目的会话归属（缺省空串表示未归属会话）；压实/固化/遗忘沿用既有「按 `session_id`
  归组」口径 —— 本变更补齐**写入侧**，不改归组算法。
- **UI 会话维度接真**（ui，MODIFIED「三模统一内核启动」，`CORE-UI-R1`）：API 层
  `create_session` 生成的标识无改写透传至循环与记忆写入；`compact(session_id)` 触发该会话
  的真实压实；`get_memory(session_id)` 只返回该会话归属的条目（UI 层按 `entry.session_id`
  过滤，不改 `MemoryStore.read` 表征）。
- **`MemoryStore` 契约补齐**：Protocol 补声明 `compact`（接口文档 `memory-interface.md:107`
  早已定义此方法，Protocol 遗漏）。

## Non-goals

- **不做每会话独立 loop / memory 实例**（另案）：本变更只做「标识透传 + 单店按会话归组」，
  组合根与生命周期不动。
- 不做运行时段进程内状态持久化（`SkillLibrary`/观察窗口/灰度态等，账本 A3）；不做遗忘调度器
  （A1）。
- 不改 `MemoryStore.read(query, budget)` 表征，不改压实/固化的归组算法与阈值。
- 不处理编排（`run_task` → `TaskScheduler`）子任务的会话归属；不给 CLI 入口引入会话生命周期。

## Impact

- **Affected specs**：`loop/spec.md`（MODIFIED「执行循环」+ 新场景）、`memory/spec.md`
  （MODIFIED「分层记忆模型」+ 新场景）、`ui/spec.md`（MODIFIED「三模统一内核启动」+ 新场景）
- **Affected code**：`src/core/loop/protocol.py`（三入口签名）、`src/core/loop/default.py`
  （`remember` 携带标识）、`src/core/memory/protocol.py`（补 `compact`）、`src/core/ui/api.py`
  （透传 / `compact` 接真 / `get_memory` 按会话过滤）
- **Affected docs**：`03-interfaces/loop-interface.md`、`03-interfaces/memory-interface.md`、
  `03-interfaces/ui-interface.md`
- **Affected tests**：`tests/test_loop.py`（标识随沉淀落账 + 缺省兼容）、`tests/test_ui.py`
  （透传 / 压实 / 按会话读）
- **Dependencies**：无新依赖
- **风险**：`get_memory` 读取范围收窄为本会话（空串「未归属」条目不再出现在会话视图）——
  这是本次要修的语义，但会改变既有 UI 断言；低（`create_session` 后的写入本就应归属该会话）。
