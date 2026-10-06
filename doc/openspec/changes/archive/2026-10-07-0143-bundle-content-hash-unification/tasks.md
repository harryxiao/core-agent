# Tasks · 0143 bundle 内容哈希双口径归一

## 1. 规格（先行）

- [x] 1.1 `composition/spec.md` **MODIFIED「bundle 分发格式」**：内容哈希口径入 SHALL
      （`plugin_id@generation` 规范形派生；同内容同哈希 / 异内容异哈希；SHALL NOT 以元信息充当内容哈希）
      + 发布入口 SHALL（读制品清单，缺失 / 非法 ⇒ `BUNDLE_INVALID` 且发布记录不变）
- [x] 1.2 三条既有 Scenario **逐字保留**；新增 Scenario「同内容同哈希、异内容异哈希」与
      「制品清单缺失不产假账」
- [x] 1.3 `openspec validate 0143-bundle-content-hash-unification` 通过

## 2. 测试（先行 · 红）

- [x] 2.1 `tests/test_composition.py`：`BundlePackager.load_manifest` 同内容异清单名 / 异 bundle 名 ⇒ 哈希相同
- [x] 2.2 改任一 `generation` ⇒ 哈希改变
- [x] 2.3 清单缺失 / 非法 JSON / `plugin_refs` 非法（非列表、缺字段）⇒ `CompositionError(BUNDLE_INVALID)`
- [x] 2.4 `tests/test_entry.py`：`release publish <清单>` ⇒ 退出码 0 + 「已发布版本 <name>」
- [x] 2.5 同内容两清单 ⇒ `releases.json` 两条记录哈希相同；异内容 ⇒ 不同
- [x] 2.6 清单缺失 ⇒ 退出码 1 + `发布失败` + `releases.json` **不变**（无假账）
- [x] 2.7 **验红**：实现前 13 条新用例失败（`load_manifest` 不存在 / publish 仍按名字哈希：`13 failed, 1 passed`）

## 3. 实现

- [x] 3.1 `src/core/composition/packager.py`：`BundlePackager.load_manifest(location)` —— 清单 → `PluginRef` →
      `pack()`（复用真口径）；异常归一为 `CompositionError(BUNDLE_INVALID)`
- [x] 3.2 `src/core/entry.py`：`_release` publish 分支改走 `load_manifest`（`ReleaseInfo.hash = bundle.hash`）；
      **删** `_content_hash` 与 `import hashlib`；`except` 补 `CompositionError`

## 4. 文档

- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0135 + `## 变更追踪` 行
- [x] 4.2 `doc/03-interfaces/composition-interface.md`：§4/§5 补内容哈希口径与发布入口（`load_manifest`）
- [x] 4.3 `doc/03-interfaces/deployment-interface.md`：§3 补 `release publish` 入参（制品清单）与哈希口径来源
- [x] 4.4 `coding-plan/cli-contract-baseline.md`：§2 动词表 `release publish <bundle>` ⇒ `<bundle-manifest>`
- [x] 4.5 `doc/04-testing/test-cases.md`：§59（TC-BUNDLE-01…05）

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— **1693 passed**（基线 1680 + 13）
- [x] 5.5 `openspec validate --all` —— 31 passed / 0 failed（归档后回落 30 / 0）

## 6. 收口

- [x] 6.1 手工归档至 `archive/2026-10-07-0143-bundle-content-hash-unification/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（§1 E84 行结论 + §9 表）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`fix(composition): bundle 内容哈希归一（change 0143）`）
