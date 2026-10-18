# Design 0264 — 工具面打磨

## D1 检查点损坏行：告警一次、不阻断

`CheckpointStore._load` 逐行加载，当前只捕 `JSONDecodeError`，且 `Checkpoint(**record["checkpoint"])`
的 `KeyError` / `TypeError` / 构造期 `ValueError` 会直接冒泡，**中断整份加载**。改为：

```python
corrupt = 0
for line in ...:
    try:
        record = json.loads(line)
        checkpoint = Checkpoint(**record["checkpoint"])
        snapshot = Snapshot(**record["snapshot"])
    except (ValueError, TypeError, KeyError):
        corrupt += 1
        continue
    ...
if corrupt:
    warnings.warn(f"checkpoint store skipped {corrupt} corrupt line(s) in {self._path.name}",
                  UserWarning, stacklevel=2)
```

- 告警**只报条数 + 文件名**（对齐 `FileBackend._load` 口径），不回显行内容（可能含任务正文 /
  密钥）。
- 合法行照常加载；损坏行跳过（既有「崩溃后重启容忍局部损坏」语义不变）。
- 告警在加载结束后**一次**发出，避免逐行刷屏。

## D2 去重参数规范化：只对文件写/补丁

`_action_key` 改为先 `_normalize_action_args(action)` 再序列化：

- **作用域**：`tools.file_write` / `tools.file_patch`。`code_run`（shell 字符串等价性不可靠）与
  `web_fetch`（URL 规范化涉及重定向 / 大小写 / 编码）保持精确匹配。
- **path**：`expanduser → abspath → normpath → normcase`（`normcase` 在 POSIX 为恒等，Windows
  折大小写并统一分隔符）。
- **文本**：`content` / `old_content` / `new_content` 的 `\r\n` → `\n`（纯 CR 不动，避免误改
  二进制/古 Mac 文本）。
- **mode**：`file_write` 的 `mode` 缺省与 `"w"` 等价；`"a"` / `"append"` 归一为 `"a"`，仍与
  覆盖写不同 —— 追加动作**不**参与紧邻重复抑制（`_is_suppressible_write` 语义不变）。
- 仅影响**去重键**，不改变实际执行参数（执行仍用原始 `action.args`）。

## D3 输出首尾保留

```python
def _truncate_output(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    marker_guess = len(f"\n…[truncated {len(text)} chars]…\n")
    budget = max(0, limit - marker_guess)
    head = budget // 3
    tail = budget - head
    removed = len(text) - budget
    marker = f"\n…[truncated {removed} chars]…\n"
    return text[:head] + marker + (text[-tail:] if tail else "")
```

- 总长 ≤ `limit`（marker 用「最大位数」预算，实际 N 位数更少 ⇒ 只多不少余量）。
- 头部 1/3 / 尾部 2/3：错误结论在尾部，尾部权重更高；头部保留命令回显 / 上下文。
- `stdout_truncated` / `stderr_truncated` 判据不变（原始长度 > 上限）。
- 仅 `code_run` 前景结果；后台日志文件不截断（`tools.process output` 只读尾部）。

## 反证

1. 摘 `_load` 的 `warnings.warn` ⇒ 告警用例红。
2. `_load` 只捕 `JSONDecodeError`（结构不符行冒泡）⇒ 「结构不符行不阻断」用例红。
3. `_normalize_action_args` 直接返回原参数 ⇒ 路径 / 换行 / mode 去重用例红。
4. `_truncate_output` 退化为纯头截断 ⇒ 「尾部保留」用例红。

## 已知局限

- 路径归一用 `abspath`（依赖当前工作目录）：同一路径在不同 cwd 下可能指向同一文件却键不同；
  反向也不做 inode / 符号链接去重。
- 不做 shell / URL 语义归一（有意）。
- 截断后 `[truncated N chars]` 的 N 为「省略的字符数（含被 marker 占用的预算）」，不是精确的
  原始尾部缺口；仅作提示。
- 检查点损坏行只告警不隔离，重复启动会重复告警（未做损坏行落盘归档）。
