# Tasks 0282 — auto-approve 命令模式级允许面

> 验证目标：`auto_approve_commands` 三面齐备、非法条目阻断启动且不回显；auto-approve 下
> `tools.code_run` 仅放行「词元边界前缀匹配且无 shell 元字符」的命令；其余档位 / 工具 /
> 空配置行为逐字不变。

## 1. 规格与测试先行

- [x] 1.1 spec delta：`configuration` ADDED；`permission` ADDED。
- [x] 1.2 新 `tests/test_command_allowlist.py`（配置 / 匹配 / 元字符 / fail-closed / 档位隔离）。

## 2. 配置层

- [x] 2.1 `permission.auto_approve_commands` ConfigSpec + 默认常量（三面）。
- [x] 2.2 校验：条目形态、工具 id 白名单、非空前缀、前缀无元字符；错误不回显取值。
- [x] 2.3 访问器 `permission_auto_approve_commands() -> dict[str, tuple[str, ...]]`。

## 3. 判定与接线

- [x] 3.1 `PermissionGuard(allowed_commands=...)` + `confirm` 内命令面判定（仅 auto-approve）。
- [x] 3.2 元字符整类拒绝 + 词元边界前缀匹配；拒绝信息不回显命令。
- [x] 3.3 `build_runtime` 接线（缺省空 ⇒ 逐字不变）。

## 4. 验证

- [x] 4.1 四门禁（ruff check / ruff format --check / pyright / pytest）。
- [x] 4.2 反证 3/3（摘元字符判定 / 裸前缀 / 摘命令面分支 ⇒ 各红；复原 `md5sum` 同）。
- [x] 4.3 `openspec validate --all` 全绿后归档。

## 5. 文档与登记

- [x] 5.1 ADR-0272；台账 E218；`doc/04-testing/test-cases.md` §194。
- [x] 5.2 `doc/02-modules/permission.md`、`doc/03-interfaces/{permission,configuration}-interface.md`。
- [x] 5.3 单次提交 `feat(permission): ...` + Co-Authored-By。
