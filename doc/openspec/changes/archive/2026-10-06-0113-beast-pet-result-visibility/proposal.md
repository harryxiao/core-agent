# 提案 — 神兽/宠物任务结果可见性（change 0113 / phase-28 E46）

## 背景

`coding-plan/phase-28.md` §1.3 登记的 **E46「结果可见性」**（账本判优先级最高）。一手复核后，账本原写的
修法**两半都撞车**，本 change 按复核结论改形：

| 半 | 账本原写 | 一手事实 | 改判 |
|---|---|---|---|
| beast | 「`recall()` 前把 `last_result.reply` 经 `session.remember()` **落 L2**（`source=beast.<agent_id>`）」 | `runtime.py:564` 主 loop 装配 `exclude_source_prefixes=("beast.",)`，且 `beast-mode/spec.md:89` **明文要求**「记忆分区封存（`source=beast.*` **不再被主 loop read 命中**）」⇒ 落进去主 Agent **永远检索不到**，**自败** | 走**查询面**，不落 L2 |
| pet | 「由 `status` / `snapshot` **暴露最近任务结果正文**」 | `pet-mode/spec.md:249`/`:255` **明文**「`status` SHALL 返回结构化字段…**SHALL NOT 外泄主人偏好与任务正文**」⇒ 违**已有 Requirement**（非实现缺口） | 另设**独立查询面**，不碰 `status` |

**真缺口是同一形态**：结果对象**已经到手**，被**上层消费点丢弃**。

- **beast**：`beast/manager.py:71` `await self._router.handoff(...)` **已拿到** `LoopResult` → `:74` 存入
  `session.last_result` —— 该属性 repo-wide **零读者**（只有定义 + 这一处写）；`entry.py:1750-1751`
  `_summon` 只打印 `状态 {session.state.value}`。
- **pet**：`pet/core/session.py:153` `wake()` **已经** `return result`（`LoopResult`）——
  `driver.py:67` `session.wake()` **丢弃返回值**（`WakingSession` Protocol 注释还明写「驱动只取其副作用」）；
  会话只留了 `_last_trace_id`，正文无处可查。

## 变更目标

1. **接出已到手的结果，不新造数据流**：beast 补**只读查询面**（`BeastSession.result_summary()`）+ `summon` CLI
   呈现正文；pet 让 `wake()` 在会话内**自留一份** `last_result` + 控制面新增 `result` 查询。
2. **不落 L2、不改记忆语义**：beast 记忆命名空间与分区封存（`beast-mode/spec.md:54`/`:89`）**逐字不动**；
   不作「神兽产物回流主记忆」（那需单独裁决，本 change 不做）。
3. **不碰隐私条款**：`PetControl.status` 返回面**逐字不变**（仍不含偏好与任务正文）；新查询面**独立**，
   规格里显式钉住这条边界。
4. **单一门面**：pet 查询面进既有 `PetControl`（`pet-mode/spec.md:244-245` SHALL 单一门面），
   CLI `pet result` 与 `UIAPILayer.pet_command` **复用同一实现**。
5. **诚实**：无结果时报「无结果」，**SHALL NOT** 编造正文（与 phase-19「不谎报」同判据）。

## 非目标 / 已否决

- **不落 L2**：账本原修法自败（上表），已否决；「允许神兽产物回流主记忆」若要做须**单独**规格变更 + 裁决。
- **不动 `exclude_source_prefixes=("beast.",)`**：破 phase-26 刚闭的 E37/E38/E39 隔离语义，**不碰**。
- **不动 `status` / `snapshot` 的返回面**：`snapshot` 含 `preferences`/`tasks[].goal` 是**持久化面**（注册表落盘用）
  的有意设计，隐私过滤**故意**做在 `PetControl.status` 这层 —— 本 change 不改其任何一层。
- **不做跨进程**：结果**不落盘**、不进 `snapshot`/注册表；只作用**本进程**已注册会话（与 `status` 同界）。
- **不新造 `wake` 语义**：`PetControl.wake` 是「恢复让行」的**另一动词**，与 `PetSession.wake()`（执行一轮）不同，勿混。

## 风险

| 风险 | 缓解 |
|---|---|
| 结果正文经 CLI/API 外泄（beast 无隐私条款，pet 有） | pet 侧新面**只**给结果正文，**不含**偏好；并加守护测试钉住 `status` 字段集**逐字不变** |
| 新查询面被当成「第二真源」 | 只读**取用** `last_result`（会话持有的既有对象），不复制、不落库、不缓存 |
| `pet result` 与 `status` 语义混淆 | 规格**独立 Requirement** + docstring 写明与 `status` 的边界；CLI 帮助串补齐 verb |
