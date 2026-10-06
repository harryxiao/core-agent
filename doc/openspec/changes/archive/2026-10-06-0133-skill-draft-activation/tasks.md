# 任务：技能 draft → active 显式启用路径（change 0133 / E72）

## 1. 规格先行

- [x] `specs/skills/spec.md` delta：ADDED「技能启用（draft → active）」+ 6 Scenario
- [x] `specs/skillhub/spec.md` delta：MODIFIED「签名校验与可信下载」（接上启用路径）
- [x] `openspec validate --all` 通过（31/0 → 归档后 30/0）

## 2. ADR

- [x] ADR-0126 + `## 变更追踪` 行

## 3. 测试先行（红）

- [x] `test_skills.py`：draft 不路由 / activate 后可路由 / 幂等 / 未知 id KeyError / 效应可回滚
- [x] `test_skillhub_cli.py`：`skill activate` 跨进程可见 + 未注册技能退出码非零

## 4. 实现

- [x] `skills/library.py::activate`（幂等 + 落盘 + 可选效应登记）
- [x] `entry.py`：`skill activate` 子命令 + `_skill_activate`
- [x] 路由放行集**不变**（`router.py` 不改）

## 5. 门禁

- [x] `.venv/bin/ruff check src tests` / `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` = 0/0/0
- [x] `.venv/bin/pytest -q`（1622 → 1629）

## 6. 文档与归档

- [x] `doc/03-interfaces/skills-interface.md` §2 + `doc/02-modules/skills.md` + `test-cases.md`
- [x] 手工归档 `archive/2026-10-06-0133-skill-draft-activation/`
- [x] `coding-plan/phase-34.md` §1 E72 + §9 行；`coding-plan/README.md` 索引
- [x] 记忆文件更新
- [x] 单次提交 `feat(skills): 技能 draft → active 显式启用路径（change 0133）`
