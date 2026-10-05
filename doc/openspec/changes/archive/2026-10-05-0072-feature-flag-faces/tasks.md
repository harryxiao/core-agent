# tasks — 功能开关三面接线与取值统一（change 0072）

## 1. 测试先行（红）
- [x] 1.1 `tests/test_feature_flag_faces.py` 新建：CLI 面接线（裸名 / 显式取值 / 优先级 / 语法拒绝 / 组合根端到端）
- [x] 1.2 取值归一：假值写法（`off`/`no`/`0`/加引号）归一为关；真值写法；原生布尔回归；env 面归一
- [x] 1.3 非法取值阻断：yaml / yaml 空值 / env / CLI 四面参数化；`apply_change` 同口径
- [x] 1.4 红证：先跑（实现前）应失败，记录失败面

## 2. 实现（绿）
- [x] 2.1 `manager.py`：`_FEATURE_TRUE` / `_FEATURE_FALSE` 取值集合
- [x] 2.2 `manager.py`：`_normalize_features()` 单一归一/校验点（构建前，`ConfigurationError` 阻断）
- [x] 2.3 `manager.py`：`_apply_env` 写入原文；`_build_config` / `_merge_patch` 改用统一归一
- [x] 2.4 `entry.py`：`_cli_overrides` 收集 `--feature NAME[=BOOL]` → `features.<模块>` 覆盖键
- [x] 2.5 `entry.py`：`_parse_feature_flag()` 语法校验（缺名 / 缺值当场拒绝）
- [x] 2.6 绿证：全量 pytest 通过，既有 `test_feature_gating.py` / `test_configuration.py` 无回归

## 3. 规格
- [x] 3.1 `configuration` spec delta：MODIFIED「功能开关（feature flag）」（三面全生效 / 同口径取值 / 校验期拒绝 / CLI 参与优先级链）
- [x] 3.2 新增场景：CLI 面覆盖 yaml 与环境 / 常见假值写法归一为关闭 / 非法取值校验期拒绝
- [x] 3.3 `openspec validate 0072-feature-flag-faces` 通过

## 4. 文档同步
- [x] 4.1 `doc/03-interfaces/configuration-interface.md` §2.2：三面与取值口径
- [x] 4.2 `doc/02-modules/configuration.md` §3.3：取值归一与校验期拒绝
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0069 + 映射表行
- [x] 4.4 `doc/04-testing/test-cases.md`：TC-CONF-06/07/08
- [x] 4.5 `doc/00-product/user-guide.md`：feature flag 口径订正（「缺省关闭」→ **缺省装配**，change `0067` 订正规格时漏改本行）+ 补三面取值口径

## 5. 归档与账本
- [x] 5.1 手动归档：合并 delta 进 `doc/openspec/specs/configuration/spec.md`，变更目录移入 `archive/2026-10-05-0072-feature-flag-faces/`
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 `coding-plan/phase-19.md`：关闭 E20②、登记并关闭 E23（`--feature` 零消费）、登记 E24（env 名前缀与规格不符）；E20① 保持开放并注明与规格告警口径冲突
- [x] 5.4 `coding-plan/README.md` 计数与单元格更新
- [x] 5.5 四门复跑 + 记忆更新 + 提交
