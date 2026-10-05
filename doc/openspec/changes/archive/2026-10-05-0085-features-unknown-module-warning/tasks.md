# tasks — 0085 `features` 段未知模块名告警

## 1. 规格先行
- [x] 1.1 `specs/configuration/spec.md` delta：MODIFIED「配置校验与生效」+ 两新场景
- [x] 1.2 `openspec validate 0085-features-unknown-module-warning` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_configuration.py`：注入已知集合 → `features.peet` 告警且不阻断（`result.ok is True`）
- [x] 2.2 `tests/test_configuration.py`：注入已知集合 → `features.pet` **不**告警
- [x] 2.3 `tests/test_configuration.py`：**未**注入 → `features.peet` 不告警（向后兼容）
- [x] 2.4 `tests/test_configuration.py`：作用域限 `features` —— `llm.typo_key` 不触发 feature 告警
- [x] 2.5 `tests/test_entry.py`：`config validate` 对 `features.peet: false` 发出告警且返回 0（证明入口注入已接线）
- [x] 2.6 红：`git stash push -u -- src/` 后新增用例失败（缺注入面）→ `git stash pop`

## 3. 实现（绿）
- [x] 3.1 `manager.py`：`__init__` 增 `known_modules: Iterable[str] | None = None`（`# noqa: PLR0913` 6→7）；`self._known_modules`
- [x] 3.2 `manager.py`：新 `_unknown_feature_warnings(config)`；`validate_schema` 的 `warnings` 并入
- [x] 3.3 `entry.py`：import `GATABLE_MODULES`；新 `_config_manager(args, *, yaml_path=None)`；替换 10 处构造点

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/configuration-interface.md`：§2 构造签名 + §2.3 features 例外
- [x] 5.2 `doc/01-architecture/adr.md`：ADR-0080 + 映射表行
- [x] 5.3 `doc/04-testing/test-cases.md`：TC-CONF-0x

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/configuration/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0085-…`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-19.md` §0/§1/§3/§9 关 E20①；`coding-plan/README.md`
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(configuration): features 段未知模块名告警（change 0085）`
