# 变更提案：notes 写回效应闸门 —— 纯读轮不落盘（change `0176`）

> 规格：`doc/openspec/specs/notes/spec.md`「Consult → Build → Update 循环纪律」（**MODIFIED**）

## 为什么

用户实测（2026-10-09）：逐轮写回仍把**纯读型工具轮**整篇塞进 canonical 知识库。change 0171 的
「有意义闸门」只挡**零工具动作**的纯文字轮（"你好/谢谢"），挡不住"有工具行动但结果无沉淀价值"的轮次：

| 实际落盘的笔记 | 为什么不该记 |
|---|---|
| `榴莲：水果之王…`、`柬埔寨：盛产榴莲…` | `web_fetch` 抓取的**原始内容转储**，非"行动与结果" |
| `Markdown 控件创建位置: repl.py 第471行` | `file_read` 一次性排查产物，无复用价值 |
| `网易要闻`、`水果/国家表格` | 问答原文，非沉淀 |

根因（读代码取证）：

1. `notes/store.py::observe_turn` 的闸门判据是 `if not ok or not steps: return None`——
   只看 steps **是否为空**，不看轮内是否产生**可沉淀的效应**。
2. `loop/default.py::_action_steps` 对**所有**工具动作（读/写/执行）一律产出行，
   导致"调过 `web_fetch`/`file_read`"即满足写回条件。
3. 这违背记忆系统第一原则「**无行动不记忆：只沉淀行动与结果**」——字面满足"有行动"，
   但"结果值得沉淀"无任何判据；而纯读产出的事实属"素材"，归 memory 的 keyfact 抽取管，
   不该进 canonical notes（刻意知识层）。

## 改什么

**只动一处实现 + 一处规格**（判据确定性、零 LLM 依赖、零新增可调参数）：

- **③ 效应闸门**（`notes/store.py::observe_turn`，在既有 `ok`/`steps` 闸门之后追加）：
  本轮行动序列中**不含任何写效应工具动作**（轮内未产生持久化效应）⇒ **不落盘**（返回 `None`）。
  写效应判据（确定性、按工具名前缀）：
  - `file_write` / `file_patch`（文件系统写）
  - `code_run` **成功**（执行产生副作用）
  - `gate_run` 通过（质量门禁产出的验证结论）
  - `install` / `uninstall`（插件安装/卸载的注册表效应）

  纯读型工具（`web_fetch` / `file_read` / `context_read` / `list` 等）产出的内容是**素材**，
  归 memory 的 keyfact 抽取路径沉淀，不进 canonical notes。

**不变**：来源守护、派生主题、覆盖式写回、可读渲染、纯文字轮闸门（0171）均逐字不变。

## 影响

- 用户会话实测中约 80% 的垃圾笔记（纯读轮转储）被消除。
- 真正的任务轮（含写操作 / 代码执行 / 门禁验证）不受影响——这些才产生"值得沉淀的行动与结果"。
- memory 侧 keyfact 抽取不迁移、不修改——纯读素材已有归属路径，本 change 只堵 notes 侧的漏。
- **既有用例连带调整**：闸门依赖 steps 的**工具行形态**，而 10 个既有用例（7 × `test_notes.py` +
  1 × `test_notes_pinned_budget.py` + 2 × `test_notes_loop.py`）的 steps 是**散文占位**（`["滚动更新"]`）
  或**只读替身**（`tools.echo`）⇒ 均改为**工具行形态的写效应 steps**（断言的不变量不变）。
