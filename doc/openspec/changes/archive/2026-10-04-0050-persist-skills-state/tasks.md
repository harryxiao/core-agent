# Tasks — persist-skills-state

## 1. 规格先行
- [x] 1.1 写 `specs/skills/spec.md` delta（1 ADDED 技能态持久化 + 1 MODIFIED 技能执行反馈）
- [x] 1.2 `openspec validate 0050-persist-skills-state` 全绿

## 2. 测试先行（先红）
- [x] 2.1 `tests/test_skills.py`：技能库重启恢复（含 version/status/instructions 全字段）
- [x] 2.2 反馈统计重启恢复（`(skill_id, version)` 计数）
- [x] 2.3 SOP 样本重启恢复（同组继续累积至阈值即提炼）
- [x] 2.4 灰度/A-B 状态重启恢复
- [x] 2.5 未注入路径纯内存（目录下无文件产出）
- [x] 2.6 损坏落盘降级为空态（不抛异常、可覆盖写入）

## 3. 实现
- [x] 3.1 新增 `src/core/skills/persist.py`（`read_state` / `write_state`，原子替换 + 损坏降级）
- [x] 3.2 `SkillLibrary(path=None)`：注册/卸载后落盘、启动恢复
- [x] 3.3 `SkillFeedback(path=None)`：写入后落盘、启动恢复（模块注释同步）
- [x] 3.4 `SopExtractor(path=None)`：样本累积/清组后落盘、启动恢复
- [x] 3.5 `VersionManager(path=None)`：灰度/A-B/稳定版本变更后落盘、启动恢复
- [x] 3.6 `build_runtime`：四个 `$CORE_STATE_DIR` 状态路径 + 显式构造 `VersionManager` 注入 `SkillIterator`

## 4. 文档同步
- [x] 4.1 `doc/03-interfaces/skills-interface.md`：四处路径参数 + 落盘形状
- [x] 4.2 `doc/01-architecture/adr.md`：ADR-0053（技能态持久化：逐类自持 + 两个纯函数）

## 5. 门禁与归档
- [x] 5.1 四门全绿：ruff check/format · pyright · pytest · openspec validate
- [x] 5.2 手动归档（合并 delta 进 `specs/skills/spec.md` → mv 到 `archive/2026-10-04-0050-persist-skills-state/`）
- [x] 5.3 `openspec validate --all` 全绿
- [x] 5.4 账本 `coding-plan/phase-19.md` A3 记「skills 半边已闭，evolution 半边随 A5」+ `README.md` 同步
- [x] 5.5 提交（显式路径，`feat(skills): 技能态持久化（技能库/反馈/SOP 样本/灰度状态落盘，change 0050）`）
