# 任务：tool-validation-single-source（E14）

## 1. 规格（先行）
- [x] 1.1 `specs/constraints/spec.md` MODIFIED「输入输出校验」（口径单一真源 bullet + 新场景）
- [x] 1.2 归档时合并进 `doc/openspec/specs/constraints/spec.md`

## 2. 测试先行（`tests/test_tool_use.py` 校验节）
- [x] 2.1 结构守护（**红**）：`core.tools.provider` 不再定义 `_matches_type`；唯一实现在 `validator.py`
- [x] 2.2 行为等价：缺参 → 工具层 `ainvoke` 与 `Validator.validate_input` 拒绝口径一致
- [x] 2.3 行为等价：错型 → 同上
- [x] 2.4 回归：既有 `test_invoke_missing_arg` / constraints `validate_input` 用例不变绿

## 3. 实现
- [x] 3.1 `src/core/tools/provider.py`：删 `_matches_type` 副本；`_validate_args` 委托 `Validator().validate_input`

## 4. 文档
- [x] 4.1 `doc/03-interfaces/constraints-interface.md`：`Validator` 标注单一真源
- [x] 4.2 `doc/03-interfaces/tool-use-interface.md`：`ToolProvider` 调用前校验委托
- [x] 4.3 `doc/02-modules/constraints.md` / `tool-use.md`：口径单一真源
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0062 + 映射表行

## 5. 验证与收尾
- [x] 5.1 四门全绿（ruff / format / pyright / pytest）
- [x] 5.2 `openspec validate 0059-...` → 手动归档 → `openspec validate --all`
- [x] 5.3 账本 E14 关闭 + §9 步骤 9 更新 + README 同步
- [x] 5.4 提交 `refactor(tools): 校验口径单一真源（工具层委托 constraints Validator，change 0059）`
