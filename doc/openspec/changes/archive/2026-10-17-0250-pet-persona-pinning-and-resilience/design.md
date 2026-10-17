# Design 0250 — 宠物人格固定与故障韧性

## 决策

### D1 人格随快照固定（persona pinning）

- `snapshot()` 增 `"persona": dict | None`，字段 `name / species / persona_text / traits / preferences`
  —— 与 `PersonaLayer` 协议字段**同构**，但不含可调用面（`render_prompt` 由重建的 `Persona` 提供）。
- 新增 `persona_from_record(data) -> Persona`（`pet/library/persona.py`），与 `Persona` dataclass
  字段一一对应；缺失键取 dataclass 缺省值（`""` / `{}`）。**不**做版本号与迁移：字段面是人格
  描述，未知键忽略、缺键取缺省，非法类型（非 dict）由调用方守卫（`persona_factory` 只在 dict 时调用）。
- `restore(record, *, ..., persona=None, persona_factory=None)` 解析序：
  1. 显式 `persona` 非空 → 用它（既有调用方语义**不变**）；
  2. 否则 `record["persona"]` 是 dict 且 `persona_factory` 非空 → 重建；
  3. 否则 `None`（无人格的裸任务行为，逐字不变）。
- 组合根恢复工厂 `lambda record: PetSession.restore(record, ..., persona_factory=persona_from_record)`。
  激活路径（`entry.py`）仍显式注入人格，因此**首次进程**与**恢复进程**走同一人格。

### D2 落盘边界：变更后持久化

- `PetManager.persist()`：有路径则 `_persist()`，无路径无操作（纯内存部署零行为变化）。幂等
  （整表覆盖写，复用既有 `_persist` 的 `write_text` 口径）。
- `PetControl.sleep / wake / assign` 在变更成功后调用 `self._manager.persist()`；`stop` 已由
  `manager.stop()` 落盘（不重复）。
- `entry._pet_run` 的 `on_tick` 在每次驱动 tick 后调用 `manager.persist()` —— 覆盖「驱动唤醒消费
  任务 / 唤醒计数递增」这类**由驱动而非控制面**产生的变更。注意先 `persist()` 再上报 tick（上报
  失败不得吞掉落盘）。
- 该边界是**保守的**：多余一次落盘（无变化）无害，漏落盘就是丢进度；故不追踪脏位。

### D3 唤醒异常 → BACKOFF + 上抛；控制面 recover

- `wake()`：
  ```python
  try:
      result = asyncio.run(run_handoff(...))
  except Exception as exc:
      self.backoff(exc)
      raise
  ```
  `except Exception` **不**覆盖 `asyncio.CancelledError`（BaseException）与 `KeyboardInterrupt`
  —— 取消/中断不是会话故障，不得置 BACKOFF。
- `backoff(exc)` 既有实现：`state = BACKOFF`、`_fault = str(exc)`、`_yielding = False`。保持不动。
- 新增 `PetSession.recover()`：`BACKOFF → ACTIVE`、`_fault = None`；其余态抛
  `PetError(OrchestrationErrorCode.PET_NOT_ACTIVE, ...)`（与 `resume` 同码，调用方口径一致）。
- `PetControl.wake`：
  ```python
  if pet.state is PetSessionState.BACKOFF:
      pet.recover()
  else:
      pet.resume()
  ```
  先睡后醒、退避后叫醒都走同一动词，宿主无需感知内部态。
- 任务**不回队**：出队在执行前（一次性语义），失败原因随 `_fault` 与驱动 `FAILED` 观测面可见；
  自动重放会绕开「主人派发」这一明确意愿，且无退避上限。

## 反证设计（每个机制单独摘除应使对应测试变红）

| 探针 | 摘除 | 预期红测试 |
|---|---|---|
| P1 | `snapshot` 的 `persona` 字段 | 人格快照往返 |
| P2 | `restore` 的 `persona_factory` 分支 | 运行时工厂重建后带人格 |
| P3 | `wake` 的 try/except → `backoff` | 唤醒失败置 BACKOFF 且上抛 |
| P4 | `PetSession.recover()` / 控制面 BACKOFF 分支 | 控制面唤醒恢复 BACKOFF |
| P5 | `PetControl` 的三个 `persist()` 调用 | assign 后新进程可见 |
| P6 | `_pet_run` on_tick 的 `persist()` | 唤醒进度跨进程可见 |

## 局限

1. 落盘是「整表快照」，多进程**同时**写同一注册表存在最后写者胜出的竞争（既有架构，登记）。
2. `recover()` 只清故障、不重置 `wake_count`（计数是累计事实，不是故障状态）。
3. 失败任务不回队（D3 决策），需要主人重新 `assign`。
4. `persona_from_record` 不校验人格内容语义（与 `parse_persona` 同口径：文本直通）。
5. 控制面仍只作用本进程 live 会话（规格明文，未改）。
