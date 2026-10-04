# persist-skills-state — 技能态持久化（A3 之 skills 半）

## Why

Phase 19 账本 A3 记：技能/进化链路的运行态**全部活在进程里**，进程一退全丢。技能半边具体是四处：

- `SkillLibrary` 注册表（SOP 提炼入库的技能随进程消失，生产每次启动技能库恒为空）；
- `SkillFeedback` 统计（`src/core/skills/feedback.py` 模块注释自陈「仅进程内统计（不落盘、不写记忆）」）；
- `SopExtractor` 样本累积（`_samples` 组内计数，跨进程清零 → 阈值永远攒不满）；
- `VersionManager` 灰度 / A/B 状态（重启后 `_gray` / `_stable` / `_ab` 归零，灰度与定夺结果蒸发）。

后果：Phase 18 的「经验 → 技能」结晶链路在生产**每进程从零开始**——SOP 要连攒 3 条同组成功轨迹才提炼一次，
技能库与反馈统计又随进程重启清零，结晶实际上不会跨会话累积。这是账本点名的横切根因
「运行时零件『进程内、无状态、无驱动』」在 skills 侧的实例（与 A5 的观察窗口同族）。

## What Changes

- 新增 skills spec Requirement **「技能态持久化（skill state persistence）」**：四类状态可落盘 JSON 并在启动恢复；
  未注入路径时纯内存（零行为变化）；落盘缺失或损坏降级为空态。
- MODIFIED **「技能执行反馈」**：删「仅进程内累积」的绝对口径，改为「缺省进程内；注入路径时落盘并恢复」。
- 实现：新增 `src/core/skills/persist.py`（两个纯函数 `read_state` / `write_state`，标准库 JSON + 原子替换 + 损坏降级），
  四处组件各加可选 `path` 参数（缺省 `None` = 纯内存，向后兼容）；`build_runtime` 注入 `$CORE_STATE_DIR` 下的四个状态文件。
- 决策记 ADR-0053（逐类自持落盘 + 复用既有 `_persist` 惯例，不引第三方依赖、不新建存储服务）。

## Non-Goals

- **不做** evolution 侧持久化（观察窗口 / 候选队列）：那是 A3 的进化半边，随 A5（采样来源）一并做。
- **不做** 跨进程并发写入的锁/合并（CLI 与 serve 同时写同一文件）；沿用既有 `_persist` 惯例的整文件覆盖语义。
- **不改** 路由 / 版本选择 / 迭代判定语义——持久化只跨进程保态。
- **不引** 新依赖（红线：核心零第三方运行时依赖）。

## Impact

- `src/core/skills/{persist,library,feedback,sop,version}.py`、`src/core/runtime.py`
- `doc/openspec/specs/skills/spec.md`（1 ADDED + 1 MODIFIED Requirement）
- `doc/03-interfaces/skills-interface.md`、`doc/01-architecture/adr.md`（ADR-0053）
- 账本 `coding-plan/phase-19.md`（A3 部分销账）
