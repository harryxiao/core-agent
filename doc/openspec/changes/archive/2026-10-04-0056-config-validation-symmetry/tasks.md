# Tasks — config-validation-symmetry

## 1. 规格先行
- [x] 1.1 configuration delta（MODIFIED「密钥分级与安全」+「配置校验与生效」，共 2 新场景）
- [x] 1.2 `openspec validate 0056-config-validation-symmetry` 全绿

## 2. 测试先行（先红）
- [x] 2.1 IM 段 secret 为空 → 校验失败（缺失）
- [x] 2.2 IM 段 secret 引用不可解析 → 校验失败（不可解析）
- [x] 2.3 IM 段缺失时不校验 secret（既有「IM 可选不配置」不回归）
- [x] 2.4 judgment 段 provider 非空但 api_key 为空 → 校验失败
- [x] 2.5 judgment 段 provider 为空（惰性段）→ 不校验 api_key
- [x] 2.6 `permission.mode` 非法取值 → 校验失败且列出四档；四档取值各自通过
- [x] 2.7 回归：既有 6 项密钥/权限模式用例全绿（明文拒绝、read-only、缺省 interactive）

## 3. 实现
- [x] 3.1 `manager.py`：`_PERMISSION_MODES` 常量（口径注明 permission 规格）
- [x] 3.2 `manager.py` `validate_schema`：三处密钥引用 `elif` 链 + permission.mode 枚举校验

## 4. 文档订正（E7）
- [x] 4.1 `coding-plan/cli-contract-baseline.md` §10 工具清单改实测集合 + 头部标注「设计态快照」
- [x] 4.2 同文件 §11 逐条标注结论（1/2/6/7；3 指向本变更；5 转出后续行）
- [x] 4.3 `doc/03-interfaces/configuration-interface.md`（校验口径）
- [x] 4.4 `doc/01-architecture/adr.md` ADR-0059 + 文末映射表行

## 5. 门禁与归档
- [x] 5.1 四门全绿：ruff check/format · pyright · pytest · openspec validate --all
- [x] 5.2 手动归档（合 delta → mv 到 `archive/<date>-0056-config-validation-symmetry/`）
- [x] 5.3 账本 E7 关闭 / E8 关闭 + 转出 `extra` 后续行 + `coding-plan/README.md` 同步
- [x] 5.4 提交（`feat(configuration): 密钥引用校验对称化 + permission.mode 枚举校验（change 0056）`）
