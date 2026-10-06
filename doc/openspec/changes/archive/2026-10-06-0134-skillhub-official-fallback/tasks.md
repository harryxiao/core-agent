# 任务：skillhub 源不健康以官方源结果回退（change 0134 / E80）

## 1. 规格先行

- [x] `specs/skillhub/spec.md` delta：MODIFIED「多源路由与健康回退」+ 3 Scenario
- [x] `openspec validate --all` 通过（31/0 → 归档后 30/0）

## 2. ADR

- [x] ADR-0127 + `## 变更追踪` 行

## 3. 测试先行（红）

- [x] `test_skillhub.py`：非官方源不健康 ⇒ `list`/`route` 回退官方源结果 + 该源被标记不健康
- [x] `test_skillhub.py`：回退目标亦不健康 ⇒ `SOURCE_UNHEALTHY`
- [x] `test_skillhub.py`：官方源自身不健康 ⇒ `SOURCE_UNHEALTHY`（无回退目标）
- [x] `test_skillhub.py`：client `search(source=S)` 回退官方源命中

## 4. 实现

- [x] `index.py::_ensure_healthy` 返回可用源名（标记不健康 + 回退官方源）
- [x] `index.py::list` / `route` 用可用源取结果

## 5. 门禁

- [x] `.venv/bin/ruff check src tests` / `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` = 0/0/0
- [x] `.venv/bin/pytest -q`（1629 → 1632）

## 6. 文档与归档

- [x] `doc/03-interfaces/skillhub-interface.md` §3 + `doc/04-testing/test-cases.md`
- [x] 手工归档 `archive/2026-10-06-0134-skillhub-official-fallback/`
- [x] `coding-plan/phase-34.md` §2 E80 + §9 行；`coding-plan/README.md` 索引
- [x] 记忆文件更新
- [x] 单次提交 `fix(skillhub): 源不健康以官方源结果回退（change 0134）`
