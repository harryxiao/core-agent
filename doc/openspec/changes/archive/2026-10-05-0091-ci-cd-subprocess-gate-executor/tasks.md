# tasks — 0091 ci_cd 门禁执行器（stdlib subprocess）

## 1. 规格先行
- [x] 1.1 `specs/ci-cd/spec.md` delta：MODIFIED「交付流水线」（生产缺省执行器 + 2 场景）
- [x] 1.2 `openspec validate 0091-ci-cd-subprocess-gate-executor` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_ci_cd_subprocess.py`（新）：真实 subprocess 通过 / 非零退出（reason 含输出尾部）
- [x] 2.2 工具缺失 → `passed=False` 不抛；超时 → `passed=False`（注入小 timeout）
- [x] 2.3 未知门禁类型 → 抛 `GATE_FAILED`；缺省工厂表 == `GATE_COMMANDS`
- [x] 2.4 `CICDPipeline()` 缺省执行器为 `SubprocessGateExecutor`

## 3. 实现（绿）
- [x] 3.1 `src/core/ci_cd/pipeline.py`：`SubprocessGateExecutor` + `build_gate_executor` 工厂
- [x] 3.2 `src/core/ci_cd/__init__.py`：导出 `SubprocessGateExecutor`
- [x] 3.3 `CICDPipeline.__init__` 缺省改为 `build_gate_executor()`

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/ci-cd-interface.md`：§2 生产执行器 + §4 注
- [x] 5.2 `doc/02-modules/ci-cd.md`：§3.1 门禁实现落实现
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0086 + 映射表行

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/ci-cd/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0091-…`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-20.md` §1/§4.2 C3 收口（含「装配/CLI 待消费者 + 命令基准 PATH 待决策」偏离说明）+ `phase-19.md` §1/§5 + `coding-plan/README.md`
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(ci-cd): 门禁执行器 stdlib subprocess（change 0091）`
