# Tasks: fix-notes-view-alignment

- [x] 1. 规格 delta：`specs/cli-ops/spec.md` 新增「诊断视图列对齐」Requirement（**按显示宽度**补齐、
      双空格分隔、禁 `\t`；3 Scenario，含「含中日韩字符的清单仍对齐」）
- [x] 2. 测试先行：`tests/test_diagnostics.py` 新增 `test_render_notes_columns_aligned`
      （按**显示列**断言时间戳起点一致；显示宽度在测试内**独立实现**，不复用被测代码以免自证）
- [x] 3. 实现：`src/core/diagnostics/views.py` 新增 `_display_width` / `_pad`，`render_notes` 改用它
- [x] 4. 回归：`gate_run: test` + `lint` + `openspec validate` 全绿
- [x] 5. 人工确认后提交并归档

## 复核纪要（2026-10-08 review 后的修正）

首轮提交的两处问题（**均非实现方向问题**，review 时发现并修正）：

1. **实现按字符数补齐 ⇒ 对中文清单无效**。`f"{v:<{w}}"` 只按 `len()` 补齐，而中日韩字符占 2 显示列 ——
   实测三行字符长度全等 36、显示宽度 **37 / 43 / 36**，时间戳列根本没对齐（本仓标题以中文为主）。
   ⇒ 改按**显示宽度**（`east_asian_width in "WF"` ⇒ 2 列）补齐。
2. **新测试自身写错（这才是红的直接原因）**：
   - 选行谓词 `ln.startswith("a ")` 未计 `render()` 给每行加的 **2 空格缩进** ⇒ `a` 行永不命中
     ⇒ `len(body) >= 2` 恒失败。⇒ 改为先 `strip()` 判空、去标题行后断言行数。
   - 第二段断言（`ln.split("  ")[1]` 取 index）**恒真**（两行都返回 2）⇒ 假断言，**没测到**它注释里
     声称的「title 起始列」—— 即使修好 (1) 也抓不住 CJK 错位。⇒ 改为按**显示列**计算时间戳起点并断言相等。
3. 顺带：清掉 3 处 ruff（E501 + PLR2004 ×2）+ 1 处格式；`design.md` 一处字面 `\n` 泄漏进正文。

> 归档口径：本 change 为 `cli-ops`（既有 capability）的 delta ⇒ canonical 追加一个 Requirement
> （4 → 5 条），capability 数不变。
