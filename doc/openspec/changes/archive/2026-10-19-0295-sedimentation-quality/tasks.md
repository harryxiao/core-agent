# Tasks — 0295 沉淀质量重构

## 1. 规格与测试先行

- [x] 1.1 写 spec delta：notes（MODIFIED 循环纪律 + ADDED 候选区/回收目录）、skills（MODIFIED SOP 提炼 + ADDED 状态运维）、configuration（ADDED 沉淀配置项）
- [x] 1.2 `tests/test_notes_sediment.py`：预滤、JSON 解析/拒绝、support 去重、上限、不可见、晋升来源守护、auto-promote、prune/manifest/恢复、损坏容错
- [x] 1.3 `tests/test_skill_draft_quality.py`：准入闸、重复轨迹、draft 不路由、activate 生效、active 不覆盖、deprecated 粘性、拒绝文本门、CLI list/deprecate
- [x] 1.4 确认新增用例先红

## 2. notes 实现

- [x] 2.1 `src/core/notes/sediment.py`：`Candidate` / `CandidateStore`（RLock、0600、原子、128 上限、损坏容忍）
- [x] 2.2 `Sedimenter`：预滤、脱敏有界 prompt、严格 JSON、upsert/support、promote/reject/auto-promote
- [x] 2.3 `src/core/notes/prune.py` + `NoteStore.raw/remove`；`store.has_write_effect` 公开化
- [x] 2.4 `src/core/notes/__init__.py` 导出

## 3. skills 实现

- [x] 3.1 `SopExtractor` RLock + 准入闸（空 steps / 短任务 / 工具动作 / 重复轨迹）
- [x] 3.2 结构化 Markdown prompt + 拒绝文本门
- [x] 3.3 发布 `draft`；active/gray 跳过、deprecated 粘性、draft 覆盖
- [x] 3.4 `skill list [--status]` / `skill deprecate` CLI

## 4. loop / runtime / CLI / 配置

- [x] 4.1 `TurnObserver` 4 参 + `_notify_turn` 传 `ctx.reply`；更新 3 参调用点
- [x] 4.2 runtime 构造 `Sedimenter`，`_loop_hooks` 改走候选；删除 `note_store.observe_turn` 接线
- [x] 4.3 notes CLI：`candidates` / `candidate-show` / `candidate-promote` / `candidate-reject` / `prune`
- [x] 4.4 ConfigSpec + 访问器 + `_key_to_patch` 允许 `notes.`

## 5. 测试更新与门禁

- [x] 5.1 更新 `test_notes_loop.py` / `test_skills.py` / `test_skill_extraction_quality.py` / `test_procedural_e2e.py` / `test_phase13.py` / `test_skill_retirement.py`
- [x] 5.2 更新 `test_loop*.py` 3 参观察者为 4 参；补 runtime 接线回归守卫
- [x] 5.3 `ruff check` / `ruff format --check` / `pyright` / `pytest -q`
- [x] 5.4 反证 3/3（cp 到 /tmp + md5 复原）：效果预滤、durable 判定、SOP active
- [x] 5.5 `openspec validate --all`

## 6. 文档与迁移

- [x] 6.1 ADR-0285 / known-risk E231 / test-cases §208 / 四份接口文档
- [ ] 6.2 迁移（agent 空闲时）：`notes prune` 34 篇、`sop-samples.json` 入回收目录、3 条 SOP deprecate
- [x] 6.3 归档 / 提交（含 0294）；6.2 迁移待 core-agent 进程重启后执行
