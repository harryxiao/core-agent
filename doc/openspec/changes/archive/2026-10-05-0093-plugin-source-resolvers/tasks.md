# tasks — 0093 插件四源解析器（Phase 20 C6）

## 1. 规格先行
- [x] 1.1 `specs/plugin-registry/spec.md` delta：MODIFIED「插件来源与安装」（四源发现契约 + 3 场景）
- [x] 1.2 `openspec validate 0093-plugin-source-resolvers` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_plugins_sources.py`（新）：`resolve_git_repo` 真实临时仓库往返 / 缺 manifest / 克隆失败归一
- [x] 2.2 `resolve_market_registry`：注入 fetcher 取回 / DomainError 透传 / 失败脱敏（URL 凭据不回显）
- [x] 2.3 `resolve_mcp_endpoint`：合成 manifest、零网络
- [x] 2.4 `InstallDispatcher.resolve` 四源分派 + `LOCAL_PATH` 既有行为不变
- [x] 2.5 CLI：`plugin install --source git-repo` 端到端（真实临时仓库，技能**跨进程落盘**）
- [x] 2.6 红：以上用例在实现前失败

## 3. 实现（绿）
- [x] 3.1 `src/core/plugins/sources.py`（新）：`MANIFEST_FILENAME` / `Cloner` / `Fetcher` / `_clone_with_git` / `_http_json` / `_parse_manifest` / `_safe` / 三解析器
- [x] 3.2 `src/core/plugins/install.py`：`InstallDispatcher.resolve` 四源分派 + `cloner`/`fetcher` 注入缝 + `_resolve_local`
- [x] 3.3 `src/core/plugins/__init__.py`：导出
- [x] 3.4 `src/core/entry.py`：`plugin install --source`；`_build_installer` 技能库同源
- [x] 3.5 绿：全部用例通过

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/plugin-registry-interface.md` §8：四源解析契约 + `core-plugin.json` + CLI `--source`
- [x] 5.2 `doc/01-architecture/adr.md`：ADR-0088 + 映射表行
- [x] 5.3 `doc/04-testing/test-cases.md`：TC-PLUGIN-01/02/03

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/plugin-registry/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0093-plugin-source-resolvers`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-20.md` §1/§4.5 C6 收口 + `phase-19.md` §1/§5 + `coding-plan/README.md`；新增后续行（`install_tool` 未接线）
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(plugins): 插件四源解析器（change 0093）`
