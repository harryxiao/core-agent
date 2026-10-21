# Design — 0299 TUI 视觉密度改版

## 设计原则（商业级终端观感 = 五条军规）

1. **信息密度优先**：每一行都要载信息。chrome 行数预算 idle ≤ 4 / busy ≤ 5。
2. **层级靠色彩与字形，不靠边框**：边框只留给唯一交互锚点（输入框）与浮层（命令面板）。
3. **单行状态语法**：`glyph 动词(目标) · 元信息`；展开体首行放 dim 元信息行；
   标题语法不动（TUI+Web 共享标题表）。
4. **空行只在语义组之间**：段落间留白保留（可读性），块内/围栏四周零留白；
   轮次间 1 行 dim 分隔。
5. **单一 token 源**：全部落在 `App.CSS` 一处；色板沿用 terracotta（`_ACCENT=#d97757`）。

## 密度账目（改版前后）

| 元素 | 现行成本 | 目标成本 |
|---|---|---|
| 底部 chrome（idle / busy） | 6 / 8 行 | 4 / 5 行 |
| 代码围栏（N 行内容） | N+4 | N |
| H1 / H2–H6 | +3 / +2 | +1 / +1 |
| 水平线 `---` | 3 行 | 1 行 |
| 展开块顶空行 + 缩进 | 1 行 + 3 列 | 0 行 + 2 列 |
| 启动横幅 | 5 行 | 2 行 |
| 命令面板 max-height | 8 | 6 |

实例：3 段 + 2 个 6 行围栏的回复 ≈ 26 行 → 21 行（−19%）；纯代码密集回复降幅更大。

## 关键决策

### D1 状态行合并（8 → 5 行）

`#spinner` 从主流程移入 footer，与 `#hints` 同住 `Horizontal#status`（高 1 行、无边框、
`margin: 0 1`）。spinner 隐藏时行仍存在（hints 占位）。`#input-box` 保留 round 边框 +
focus 高亮（交互锚点）。widget id 全部不变（`#spinner` / `#hints` 查询面不动 ⇒ 既有测试
与 `action_hints` 逻辑零改动）。

### D2 文件呈现（本 change 的主要新逻辑）

事件面事实（实现期查证，构成方案修正依据）：

- `action_completed.output` = `str(result.data)[:400]`（change 0152 有界）——内置文件工具
  的 `data` 是 dict ⇒ TUI 收到的是 **dict repr**（换行被转义、400 字符截断）。
- `action_started.args` 是**结构化 dict**，逐值 ≤ 400 字符（`_args_excerpt`，字符串保持
  字符串）⇒ `content` / `old_content` / `new_content` / `path` 在 TUI 侧可直接确定性取用。

据此的呈现策略（全部 TUI 侧、容错回退到现状灰显）：

- **file_write**：正文 = `args["content"]`（真实字符串）；元信息 = output repr 中
  `'bytes_written': (\d+)` + content 行数 ⇒ `N 字节 · M 行写入`（content 带 `…` 截断标记
  时只报 `N 字节写入`）。
- **file_patch**：由 `args` 的 old/new 节选**合成 unified diff**（difflib，`a/<path>` /
  `b/<path>` 头），正文用 diff lexer 红绿呈现；元信息 `+N −M · hunk H`（对合成 diff 计数），
  `replaced: False` 追加 `· 未命中`，任一侧截断追加 `· 节选`（计数为下界，不谎报全量）。
- **file_read**：从 output repr 中按字面标记 `'content': '` 切出转义正文，单遍
  `re.sub(r"\\(.)")` 反转义常用转义（`\n \t \r \\ \' \"`，其余保持字面）；repr 完整
  （`'}` 收尾）⇒ `N 行`，否则 `N 行 · 节选`。切不出 ⇒ 原样灰显（回退，不崩）。
- **lexer 映射**：`_LEXERS_BY_SUFFIX` 白名单（py/js/ts/json/yaml/toml/md/sh/rs/go/c/…），
  未知后缀 ⇒ None（plain）。**只在文件三件套上启用**；`code_run` 等其他工具逐字不变。

### D3 行数上界 40（非计划的 200）

事件面已有 400 字符上界 ⇒ 200 行永不触达（死代码）。40 行可被换行密集输入触达
（如 400 个换行符的病态读入 ⇒ 空白行洪泛），正常内容（≤400 字符）不可达。
截断尾行 `…（共 X 行，已截断）`。上界同时约束 plain 与高亮两条渲染路径。

### D4 轮次分隔

`_run_turn` 的 `finally` 末尾追加 `Static("", classes="turn-sep")`（`border-top: dashed`
⇒ 1 行虚线）。`Static("").render()` 为空文本 ⇒ `_timeline_text` 类文本断言面不受影响；
每轮恰好一条（`_run_turn` 每次用户输入调用一次）。

### D5 反转义的边界

read 正文抽取面对的是**自家工具**的固定 dict 形态（`{'path': …, 'content': …}`），
非任意 Python 字面量解析；不执行任何求值（纯正则/切片）。路径中含 `'content': '` 的
病态构造会得到错误切分 ⇒ 落入不可读文本，但无崩溃、无副作用（呈现层降级）。

## 测试策略

新增用例（`tests/test_repl.py`，复用 `_step_app` / `_blocks` / `_inner` 惯用法）：

1. chrome 预算：idle footer 高 4；标签栏可见时 5；`#hints` 区域高 1（无边框）。
2. 展开体无顶空行：code_run 块展开后 `body.region.y == contents.region.y`（且 2 列缩进）。
3. 围栏高度预算：3 行围栏的 `MarkdownFence` 区域高恰 3。
4. 截断上界：构造 180 换行的 file_read repr ⇒ 正文 40 行 + 尾行含 `共 180 行`。
5. 元信息行：file_write `12 字节 · 1 行写入`；file_patch `+1 −1 · hunk 1`。
6. 语法高亮冒烟：file_write 正文 renderable 为 `Syntax`；code_run 仍为纯文本。
7. 欢迎横幅 2 行。
8. 轮次分隔存在且高 1 行。

反证（cp 到 /tmp + md5sum 复原）：

- 去 `MarkdownFence` 覆盖 ⇒ 围栏高度用例红；
- 去 `_MAX_BODY_LINES` 截断 ⇒ 病态长输出用例红；
- 恢复 `#hints` 边框 ⇒ chrome 预算用例红。

## 风险与回退

- 全部改动集中在 `src/core/ui/repl.py` 呈现层，一次 revert 即整体回退。
- 观感验收以人工目检为准（`uv run core-agent`）；测试守护的是**行数账目**与**回退不变性**，
  不是美学。
