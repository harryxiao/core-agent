# tasks — env 前缀口径订正（change 0080 / 账本 E24）

## 1. 规格（真 delta，**非** `skip_specs`）
- [x] 1.1 `specs/configuration/spec.md`：MODIFIED「功能开关（feature flag）」—— env 面改**复数** + 补齐 `0072` 丢失的正文段 + 新增场景「env 面以复数前缀生效」
- [x] 1.2 `openspec validate 0080-configuration-env-prefix-alignment` 通过

## 2. 文档订正
- [x] 2.1 `doc/03-interfaces/configuration-interface.md` §2.2（三通道行 + ⚠️ 注记转 ✅）
- [x] 2.2 `doc/02-modules/configuration.md` §3.3（`CORE_FEATURE_*` → `CORE_FEATURES_*`）
- [x] 2.3 `doc/01-architecture/adr.md` ADR-0069（正文叙述 +「登记后续」E24 项）
- [x] 2.4 `tests/test_feature_flag_faces.py` docstring 引用的通道清单（无代码变更）

## 3. 账本 / README
- [x] 3.1 `coding-plan/phase-19.md`：§1 表 E24 行 → ✅ 已关闭（change `0080`）；§0 相关句标注；§9 第 9 项追加
- [x] 3.2 `coding-plan/README.md` 状态行同步（E24 入已闭列表 + 依赖列尾 + 下一步清单）

## 4. 收口
- [x] 4.1 四门全绿（无代码变更，期望与基线逐位一致：ruff check / ruff format --check / pyright / pytest）
- [x] 4.2 手动归档（合并 delta 进 spec + `shutil.move`）+ `openspec validate --all` 全绿
- [x] 4.3 记忆更新 + 提交
