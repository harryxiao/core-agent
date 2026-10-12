# Proposal 0228 — 文件工具 `~` 展开（change 乙）

## Why

模型/用户以 `~/.core/…` 这类**家目录路径**调用 `tools.file_read` / `file_write` / `file_patch` 时，
`Path(path)` **不做** `~` 展开 ⇒ 路径被解释为**当前工作目录下字面名为 `~` 的目录**下的文件。父目录
`./~` 不存在 ⇒ 读/写均以 `FileNotFoundError` 失败（实测 `Path('~/x').write_text(...)` 抛
`No such file or directory: '~/x'`）。**意图（家目录）与行为（字面 `~` 目录）静默背离**，且错误信息
（`'~/x'` 不存在）对模型毫无线索 ⇒ 易触发重试 / 退化（与 change 0227 的上游压力同源）。

两个缺口：

1. **路径不展开**：`~` 未归一到家目录 —— 用户/模型的常见写法直接失败。
2. **撤销点错位（隐患）**：撤销闭包 `_restore` 按快照 `path` 恢复 —— 若只在 I/O 处展开、快照仍存
   原串，则撤销会作用到**字面 `~` 路径**（与写入点不一致）。故展开须**一次做、全程一致**。

## What Changes

- **`~` 展开（无条件）**：`src/core/tools/builtin.py` 新增模块级 `_expand(path) -> Path`
  （`Path(path).expanduser()`，与 `core_profile.loader` 同口径）。`file_read` / `file_write` /
  `file_patch` 三个 handler 入口用它取目标路径；`file_write` / `file_patch` 把**展开后**的路径存入
  撤销快照 ⇒ `_restore` 恢复点与写入点一致（`_restore` 本身不动）。
- **返回体 contract 不变**：三个工具返回的 `{"path": …}` 仍回**模型给的原文**（`~/x`）—— 形状与
  值域语义不变，仅**落盘位置**改变。

## Impact

- 影响模块：`src/core/tools/builtin.py`（3 handler ＋ 1 新 helper）。
- **规格中性**：`tool-use` spec **不约束**文件工具路径语义（该 spec 只覆盖 code_run / web_fetch 与通用
  契约；文件工具无专属 Requirement）⇒ `skip_specs: true`、零 spec delta、canonical 计数不变。行为在
  `doc/03-interfaces/tool-use-interface.md` §3 落注。
- 零配置键、零三方依赖、零新暴露面（展开后的绝对家目录路径与既有路径解析一致）。
- **不覆盖** `code_run` 的 `cwd`（非 `file_*` 工具；同源缺口，登记为后续候选）。

## Migration

无需迁移。既有以**相对/绝对路径**调用者行为**逐字不变**（`expanduser` 对无 `~` 的路径是恒等变换）；
仅 `~` 开头路径从「失败」变为「正确落到家目录」。
