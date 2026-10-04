# Tasks — evolution-cold-path

## 1. 规格先行
- [x] 1.1 evolution delta（ADDED 冷路径驱动 + ADDED 窗口持久化 + MODIFIED auto-dissolve[采样来源]）
- [x] 1.2 loop delta（MODIFIED 执行循环：维护节拍含冷路径 + 2 个新场景）
- [x] 1.3 cli-ops delta（MODIFIED 运维命令集：`evolve run` + 场景）
- [x] 1.4 `openspec validate 0051-evolution-cold-path` 全绿

## 2. 测试先行（先红）
- [x] 2.1 `ObservationRegistry` 落盘/恢复（基线+样本+冻结截止）+ 纯内存 + 损坏降级
- [x] 2.2 worker 采样：已开窗目标按 plugin_id 归因的成功率上报；无归因不采样
- [x] 2.3 worker 采样端到端：批次成功率低于基线 → 达下限 → 自动溶解（教训留痕）
- [x] 2.4 loop 冷路径节拍：达间隔调用一次 / 未达间隔不调用 / 回调抛错降级不中断
- [x] 2.5 CLI `evolve run`：强制跑一轮并打印结局；装配失败退出码 1

## 3. 实现
- [x] 3.1 `src/core/persistence.py`（helper 迁入）+ 四个 skills 模块改 import + 删 `skills/persist.py`
- [x] 3.2 `ObservationRegistry(path=None)`：`_load`/`_persist`/`targets()`
- [x] 3.3 `EvolutionWorker._sample_observations`（cycle 后按 plugin_id 归因采样）
- [x] 3.4 loop：ctor 增冷路径回调 + 维护节拍内调用（失败降级）
- [x] 3.5 `entry.py`：`evolve run` 子命令 + handler
- [x] 3.6 `runtime.py`：窗口落盘路径 + 冷路径回调注入 loop

## 4. 文档同步
- [x] 4.1 `doc/03-interfaces/evolution-interface.md`（采样来源 + 窗口持久化 + worker 驱动）
- [x] 4.2 `doc/03-interfaces/loop-interface.md`（冷路径回调）
- [x] 4.3 `doc/03-interfaces/skills-interface.md` §7（helper 迁至 `core/persistence.py`）
- [x] 4.4 `coding-plan/cli-contract-baseline.md`（`evolve run` 行）
- [x] 4.5 `doc/01-architecture/adr.md` ADR-0054（+ ADR-0053 指注）

## 5. 门禁与归档
- [x] 5.1 四门全绿：ruff check/format · pyright · pytest · openspec validate
- [x] 5.2 手动归档（合 3 份 delta → mv 到 `archive/2026-10-04-0051-evolution-cold-path/`）
- [x] 5.3 `openspec validate --all` 全绿
- [x] 5.4 账本：A10 新增并关闭、A5 关闭、A3 全闭、§9 顺序更新 + README 同步
- [x] 5.5 提交（`feat(evolution): 冷路径驱动面 + 观察期采样与持久化（change 0051）`）
