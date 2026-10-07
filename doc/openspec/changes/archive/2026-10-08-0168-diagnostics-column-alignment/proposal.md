# 0168 · 诊断视图列对齐：残留 `\t` 全清 + 对齐助手单一实现

> 触发：用户 2026-10-08 复查 change `0165` 的改动后追问 ——
> 「`render_sessions / render_mcp / render_config` **仍在用 `\t`** 可以修正吗」。
> 范围经确认取**全部 5 处**（`sessions` / `config` / `mcp` / `skills` + `collect_status`）。

## Why（遗留缺陷）

change `0165` / ADR-0158 只修了**一个**视图（`render_notes`）：把 `\t` 三列改为按**显示宽度**
补齐的双空格列。但**同一缺陷类的其余 5 处一字未动** —— 诊断源里所有列表型视图本来都用 `\t` 拼列：

| 视图 | 站点 | `\t` 数 | 形态 |
|---|---|---|---|
| `render_sessions` | `views.py:31-32` | 2 | 表格（id / 标题 / 更新时间） |
| `render_config` | `views.py:51-62` | 7 | 键值（6~7 行 `标签 值`） |
| `render_mcp` | `views.py:74` | 2 | 表格（名 / 传输 / 来源） |
| `render_skills` | `views.py:86,100` | 2 | 键值 + 明细行 |
| `collect_status` | `checks.py:160-168` | 8 | 键值（8 行 `标签 值`） |

**根因与 `0165` 逐字相同**：诊断视图的消费面是 `Static(markup=False)`（TUI，change `0163`）与
`print`（CLI，change `0162`）—— **两者都不解释制表符**，`\t` 退化为字面空白或不定宽跳格 ⇒
列随内容参差。`render_notes` 已经证明这个修法，只是**没有推广**。

**次生问题（结构）**：`0165` 的两把助手 `_display_width` / `_pad` 落在 `views.py` **私有**，
`checks.py` 的 `collect_status` **够不着** ⇒ 即便只改一处，也会被迫复制第二份实现
（"列宽怎么算"记两遍正是本仓反复消掉的病：真源只应有一处）。

## What Changes

1. **新模块 `src/core/diagnostics/align.py`**（**对齐的单一实现**）：

   ```python
   def display_width(text: str) -> int: ...          # 东亚宽 / 全角 ⇒ 2 列（承 0165）
   def pad(text: str, width: int) -> str: ...        # 按**显示宽度**左对齐补齐
   def align_rows(rows: list[list[str]]) -> list[str]: ...   # 表格型：每列按列内最长显示宽度补齐
   def align_pairs(entries: list[tuple[str, str] | str]) -> list[str]: ...  # 键值型：标签列补齐
   ```

   `align_pairs` 接受 `str` 条目并**原样透出** —— 技能视图的 `· …` 明细行夹在键值行之间，
   不参与补齐（混合形态是刻意的，不给它单独一条代码路径）。

2. **六个视图全部改走共用助手**：`render_sessions` / `render_mcp`（`align_rows`）；
   `render_config` / `render_skills` / `collect_status`（`align_pairs`）；`render_notes` **回填**
   同一助手（删掉 `0165` 的 `_display_width` / `_pad` 私有副本）。

3. **`collect_status` 由 f-string 拼接改为条目列表**（`align_pairs` 的输入形态）—— 读数逻辑
   （`_model` / `_budget` / `_field`）与各行**取值**一字不改。

4. **规格 `cli-ops`「诊断视图列对齐」MODIFIED**：作用域由「`render_notes`」扩为「诊断源**全部**
   列表型视图」，明写**两形态**（表格型 / 键值型）与各自的补齐口径；既有 3 个 Scenario 逐字保留，
   新增 2 个（会话与 MCP 端点清单 / 键值型视图标签列）。

## Non-goals

- **不引三方库**（`wcwidth` / `rich`）：`unicodedata.east_asian_width` 是标准库，够用且零依赖。
- **不改** TUI 呈现层（`Static(markup=False)` 的调用点、`_show_*` 命令族）与 `Report` / `Deps` /
  六个视图的**签名** —— 对齐是渲染层的事，改的只是**行内空白**。
- **不动** `doctor` 的 `Check` 明细（`✓/!/✗ <名>：<明细>` 是**单行项**，不是列表）。
- **不加**列宽上限 / 截断 / 省略号（长字段使行长增长可接受，同 `0165` 的取舍）。
- **不改** `0162` 的空清单 / 句柄缺失降级路径（`（空）` / `未接线（句柄未注入）` 照旧）。

## Risks

- **`render_config` 的「密钥引用」行由三列变两列**（`${VAR}` 与「可解析」以两个空格相连）——
  `align_pairs` 是二列形态；读数与结论不变，仅少一处分隔符。**不涉密钥值**（只出 `${VAR}` 引用名）。
- **歧义宽字符**（`±` / `→`）按 1 列计（`"WF"` 不含 `A`）—— 承 `ADR-0158` 局限③，本 change 不裁决。
- **值内含 2+ 空格**时，「值起点」在视觉上仍对齐，但按「2 空格分列」的解析（含测试助手）会把
  一个值拆成多格 —— 各值均为单空格形态（`max_rounds=N, token_budget=M` / `a=on, b=off`），无实例。
