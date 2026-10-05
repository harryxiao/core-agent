# tasks — 0092 skillhub 接入 CLI

## 1. 规格先行
- [x] 1.1 `specs/skillhub/spec.md` delta：MODIFIED「技能市场与技能发现」+「签名校验与可信下载」（CLI 触达点 + 技能库同源 + 3 场景）
- [x] 1.2 `openspec validate 0092-skillhub-cli-wiring` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_skillhub_cli.py`（新）：`skill search` 见市场元数据（注入内存 index）
- [x] 2.2 `skill install` 落 draft 且**跨进程可见**（重开 `SkillLibrary(path=…)` 能查到）
- [x] 2.3 签名失败 → 退出码 1 + 不落盘；市场未接（缺省 fetcher）→ 退出码 1 如实报错
- [x] 2.4 `skill remove` 作用于**持久库**（先落盘再删，第二次报未注册）

## 3. 实现（绿）
- [x] 3.1 `entry.py`：`_build_skill_library()` / `_build_skillhub_client()` + `_skill_search` / `_skill_install` 改走客户端
- [x] 3.2 `entry.py`：`skill search` 增 `--source`；`skill install` help 订正

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/skillhub-interface.md`：§2 CLI 触达点 + 技能库同源
- [x] 5.2 `doc/02-modules/skillhub.md`：生产触达点
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0087 + 映射表行

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/skillhub/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0092-…`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-20.md` §1/§4.4 C5 收口（C 类四项全闭）+ `phase-19.md` §1/§5 + `coding-plan/README.md`
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(skillhub): 接入 CLI skill search/install（change 0092）`
