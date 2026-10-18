# Proposal 0264 — 工具面打磨（P2：检查点告警 / 去重规范化 / 输出首尾保留）

## Why

对比审查（2026-10-18）列出三处低风险但长期损耗的打磨项：

1. **检查点损坏静默**：`CheckpointStore._load` 对坏 JSON 行 `continue`，不告警；结构不符的
   行（`record["checkpoint"]` 缺失 / 字段类型错）还会直接抛异常中断加载。用户不知道恢复面
   丢了数据。
2. **去重仅精确匹配**：批内 / 紧邻重复只对「参数逐字相同」生效；同一路径的不同写法
   （`~` / 相对 / 绝对 / `..`）、CRLF 与 LF、省略 `mode` 与显式 `"w"` 都会被当成不同动作，
   重复写盘。
3. **输出截断只留头部**：`code_run` 的 `stdout` / `stderr` 按 `_MAX_OUTPUT_CHARS` **纯头截断**，
   而测试 / 编译错误的结论通常在**尾部** —— 长输出下最有用的信息先被丢掉。

## What Changes

- **检查点损坏行告警且不阻断**：`_load` 捕获 `(ValueError, TypeError, KeyError)`（覆盖坏 JSON 与
  结构不符行），累计计数后 `warnings.warn` **一次**（只报条数 + 文件名，不回显行内容）；合法行
  照常加载。
- **去重参数规范化**（仅 `file_write` / `file_patch`）：`path` 做
  `expanduser → abspath → normpath → normcase`（Windows 大小写）；`content` / `old_content` /
  `new_content` 做 CRLF→LF；`file_write` 省略 `mode` 与显式 `"w"` 等价（`a`/`append` 归一为
  `"a"`，仍与覆盖写不同）。`code_run` / `web_fetch` 保持精确匹配（避免 shell / URL 语义风险）。
- **输出首尾保留**：新增 `_truncate_output(text, limit)`，总量上限不变（`_MAX_OUTPUT_CHARS`
  = 8192）：头部 1/3 + `\n…[truncated N chars]…\n` + 尾部其余；
  `stdout_truncated` / `stderr_truncated` 语义不变。仅作用于 `code_run` 前景结果；后台日志文件
  不截断，`tools.process output` 仍只读尾部（≤64K）。

## Impact

- `src/core/durability/store.py`、`src/core/loop/default.py`、`src/core/tools/builtin.py`。
- 规格：`durability` **ADDED** 1 req（损坏行告警、不阻断）；`loop` **MODIFIED**「单次推理多工具
  动作」（规范化口径）；`tool-use` **MODIFIED**「内置原子工具」（首尾保留）。
- 文档：`doc/02-modules/{durability,loop,tool-use}.md`、`doc/03-interfaces/{durability,tool-use}-interface.md`、
  `doc/04-testing/test-cases.md` §176、ADR-0254 / 台账 E200。
- 测试：`tests/test_durability.py`、`tests/test_parallel_tool_calls.py`、`tests/test_tool_use.py`。

## 不做（明确边界）

- 不对 `code_run` / `web_fetch` 做参数归一（shell 字符串与 URL 的等价性不可靠，误合并风险高）。
- 不引入三方依赖；不改 `_MAX_OUTPUT_CHARS` 上限；不改后台日志与 `tools.process output` 口径。
- 不做检查点损坏行的自动修复 / 隔离文件（只告警 + 跳过）。
