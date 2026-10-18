# Tasks 0273 — 里程碑报告锚定

## 1. 装配器

- [x] 1.1 `src/core/notes/milestone.py`：`close_milestone(...)`（固定节次序 / 来源合并 / 幂等 /
      来源守护 / 空内容守卫 / 脱敏 / 3000 字符头部保留截断）
- [x] 1.2 `src/core/notes/__init__.py` 导出 `close_milestone` 与常量

## 2. CLI

- [x] 2.1 `notes milestone` 子命令（`<name>` / `--session` / `--as` / `--title` / `--priority` /
      可重复 `--conclusion` / `--decision` / `--constraint`）
- [x] 2.2 `_notes_milestone` 处理器 + `_session_key_facts`；成功回执、失败非零退出；
      `_NOTES_USAGE` 同步

## 3. 测试与门禁

- [x] 3.1 `tests/test_notes_milestone.py`：结构 / 幂等 / 摘要与 keyfact 装配 / 空内容 /
      空 slug / 来源守护与 `--as` / 脱敏与有界 / 优先级次序
- [x] 3.2 `tests/test_entry.py`：CLI 成功落盘 + show 读回 / 空内容非零 / usage 列出 milestone
- [x] 3.3 反证：摘来源守护 / 摘脱敏 / 摘截断 / 忽略优先级 / 空内容不返回 None ⇒ 对应用例红；
      复原 `md5sum` 同
- [x] 3.4 四门禁 + `openspec validate --all`；archive + ADR-0263 + 台账 E209 + 测试节 §185
      + 模块/接口文档 + 单次提交
