# 任务：feature-flag-gating（E10）

## 1. 规格先行

- [x] 1.1 `configuration` spec「功能开关（feature flag）」MODIFIED（装配语义 + 缺省开 + 单一真源名单）
      + 四个新场景 → `specs/configuration/spec.md`
- [x] 1.2 用户裁决落地：白名单内可选模块**缺省开**，仅显式 `false` 关闭

## 2. 测试先行（红 → 绿）

- [x] 2.1 `tests/test_feature_gating.py`：**缺省装配**（无 features 段 ⇒ pet/beast/evolution 三面非空）
- [x] 2.2 显式 `true` 等价缺省（`features: {pet: true}` ⇒ 非空）
- [x] 2.3 `pet: false` ⇒ `pet_manager is None` 且**不读** `pets.json`（写入损坏 JSON，装配仍成功）
- [x] 2.4 `beast: false` ⇒ `beast_manager is None` 且 20 神通**未注册**（域内路由返回空）
- [x] 2.5 `evolution: false` ⇒ `runtime.evolution is None` 且 `loop._cold_path is None`
- [x] 2.6 三模块全关 ⇒ 核心面（loop/memory/tools/skill_router）照常非空
- [x] 2.7 `ConfigManager.is_disabled` 口径：未声明 False / `true` False / `false` True；`is_enabled` 语义不变
- [x] 2.8 CLI 六入口（`pet list` / `summon` / `recall` / `evolve run|pending|confirm|reject`）
      关闭时 stderr 说明 + 退出 0
- [x] 2.9 确认红（`is_disabled` 不存在 / 字段不可空 → 失败），实现后转绿

## 3. 实现

- [x] 3.1 `configuration/manager.py`：`is_disabled(module)`（`features.get(module) is False`）
- [x] 3.2 `runtime.py`：`GATABLE_MODULES` + 三处装配裁剪 + 五字段可空 + docstring 订正
- [x] 3.3 `runtime.py`：`cold_path` 随 evolution 关闭置 `None`
- [x] 3.4 `entry.py`：六入口拒绝（stderr + 退出 0）

## 4. 文档

- [x] 4.1 `doc/03-interfaces/configuration-interface.md`：两谓词口径并列
- [x] 4.2 `doc/02-modules/configuration.md` §5/§6：门控行
- [x] 4.3 `doc/02-modules/runtime.md`：装配裁剪表（名单 + 副作用 + 关闭后果）
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0065 + 映射表行
- [x] 4.5 `doc/04-testing/test-cases.md`：新用例号（TC-CONF-*）
- [x] 4.6 `coding-plan/phase-0.md:32` 验收框：口径订正为「白名单内缺省开」+ 勾选

## 5. 门与归档

- [x] 5.1 四门：ruff check / ruff format --check / pyright / pytest
- [x] 5.2 `openspec validate 0067-feature-flag-gating` → 手动归档 → `openspec validate --all`
- [x] 5.3 账本 `coding-plan/phase-19.md`：§1 表 E10 行、§3 E10 段、§0 计数、§9 第 9 步；
      `coding-plan/README.md` 若列版本行则同步（另记新报 E20/E21 与 D6）
- [x] 5.4 记忆与提交
