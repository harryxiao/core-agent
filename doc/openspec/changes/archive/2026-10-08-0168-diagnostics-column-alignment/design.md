# Design: diagnostics-column-alignment

## 目标

诊断源**全部**列表型视图在任意等宽终端下各列对齐：`render_sessions` / `render_config` /
`render_mcp` / `render_skills` / `render_notes` / `collect_status`。

## 方案

### 1. 抽一个模块（`src/core/diagnostics/align.py`）

`0165` 把 `_display_width` / `_pad` 放在 `views.py` 私有 —— `checks.py` 够不着。本 change
把它们**上提为模块级公开助手**并补两个形态入口，成为**对齐的单一实现**：

```python
_SEP = "  "                                     # 列间分隔符：两个空格（不是 \t）

def display_width(text) -> int                  # 东亚宽 / 全角 ⇒ 2 列，其余 ⇒ 1 列
def pad(text, width) -> str                     # 按显示宽度左对齐补齐
def align_rows(rows: list[list[str]]) -> list[str]        # 表格型
def align_pairs(entries: list[tuple[str, str] | str]) -> list[str]   # 键值型（str 原样透出）
```

- `align_rows`：`widths[i] = max(display_width(row[i]))`，**行末不补**（`i == len(row) - 1` 时
  原样出）⇒ 不产生尾随空白；
- `align_pairs`：`width = max(display_width(label))`（**只看元组条目的第 0 位**；`default=0`
  使全 `str` 输入自然透出），逐条 `f"{pad(label, width)}{_SEP}{value}"`。

### 2. 为什么是「两形态」而不是「一个通用函数」

两个形态的**不变量不同**：

| 形态 | 视图 | 不变量 |
|---|---|---|
| 表格型 | 会话 / MCP 端点 / 笔记 | **每列**对齐（多列独立求宽） |
| 键值型 | 配置 / 技能 / 运行状态 | **值的起始列**对齐（标签列求宽，值不补） |

硬合成一个函数，就得给「哪些列参与求宽」加开关 —— 那正是被消掉的复杂度。两个入口各 5~8 行，
比一个带模式参数的函数更好读。

`align_pairs` 收 `str` 条目的理由：**技能视图的明细行（`· <标识>（<状态>, <版本>）`）夹在键值行之间**，
不参与补齐。混合形态让 `render_skills` 只维护**一个有序条目列表**（已装段 + 目录段拼起来一次对齐）——
若分成两段各自对齐，"标签列宽"会被算成两段各自的最大值 ⇒ 同一视图里 `已装技能库` 与 `市场目录`
起始列错开（正是要修的观感）。

### 3. 视图改法（逐处）

| 视图 | 改法 | 说明 |
|---|---|---|
| `render_sessions` | `align_rows([[id, title, updated_at], ...])` | 先构表再对齐（原来在 f-string 里拼 `\t`） |
| `render_mcp` | `align_rows([[name, transport, source], ...])` | 同上；**仍不出 `args`**（红线不变） |
| `render_notes` | `align_rows([[id, title, f"{ts}{marker}"], ...])` | 常驻标记**并入时间戳格**（不是第四列）⇒ 无尾随空白、列数恒为 3 |
| `render_config` | `align_pairs([(标签, 值), ...])` | 「密钥引用」行由三列变二列（值 = `${VAR}  <结论>`） |
| `render_skills` | `align_pairs(entries)` | `已装技能库` / `市场目录` 两个标签**同段求宽**，中间夹明细行 |
| `collect_status` | `align_pairs([...])` | 8 行由 tuple of f-string 改为 list of tuple；读数逻辑不动 |

`views.py` 的 `_catalog_lines` 随之更名为 `_catalog_entries`（返回条目而非成行文本），
明细行构造抽成 `_detail_lines(items)`（两处调用：已装 / 目录）。

## 备选与取舍

- **只改 `render_notes` 之外的 5 处、不抽模块** ⇒ `checks.py` 需要第二份 `_display_width` 副本 —— 弃用
  （真源两处即漂移起点）。
- **一个通用 `align(rows, *, pair=False)`** ⇒ 需要模式参数与「哪些列求宽」开关 —— 弃用（两形态不变量不同，
  见上）。
- **引 `wcwidth` / `rich`** ⇒ 三方依赖换标准库 5 行 —— 弃用（本仓「尽量不依赖三方库」）。
- **TUI 换 `DataTable` 呈现** ⇒ 与 `0165` 同一取舍：跨 UI 不一致且诊断视图承诺同源同形状 —— 弃用。
- **`align_rows` 未补齐的行末**：若某行列数少于同伴，最后一格仍按**该行自己的**末格判定（不补）
  ⇒ 少列行不会有尾随空白。当前 6 个视图列数均齐（笔记的常驻标记并入末格即为此）。

## 兼容性

- **`Report` / `Deps` / 六个视图签名零变更**；`render`（标题 + 2 空格缩进）不动 ⇒ 行前缀不变。
- 既有松散断言在新格式下仍成立：`"s1" in out` / `"remote" in out` / `"${CORE_DIAG_KEY}" in out` /
  `"skills.demo.one" in out` / `"alpha" in out` / `"常驻" in out` / `_CANARY not in out`。
- 空清单（`（空）`）、句柄缺失（`未接线（句柄未注入）`）、配置不可用（单行说明）三条降级路径**逐字不变**。
- `TUI` 只读命令族（`0163` 的 7 个 `_show_*`）与 CLI（`0162` 的 `_doctor` / `_status`）**零改动**
  —— 它们消费 `Report`，不感知空白。

## 风险

1. **歧义宽字符**（`±` / `→` / `°`）：`east_asian_width` 返回 `"A"`，本实现按 1 列计 —— 与多数现代终端
   默认一致；若终端按双宽渲染，该行偏 1 列。承 `ADR-0158` 局限③，本 change 不裁决（**已知局限**）。
2. **超长字段**：列宽按内容动态求，长 `source`（URL）会使行变长 —— 可接受（列表规模有限，同 `0165`）。
3. **测试助手的解析口径**：断言按「2+ 空格分列」定位单元格；若某**值**内含 2+ 空格会被拆成多格。
   当前各值均为单空格形态，无实例；该口径与「视图约定：列间 2 空格、值内单空格」一致（写进规格的
   其实是同一件事的两面）。
