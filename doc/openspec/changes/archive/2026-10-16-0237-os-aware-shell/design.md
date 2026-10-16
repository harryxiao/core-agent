# Design 0237: 运行环境感知的 shell 方言

> 对标 Claude（方言执行面 + 平台选主壳）与 Cursor（prompt 注入 Shell 事实）的交集：
> **软事实（A）+ 单工具多方言（B）**；不拆双 tool_id。

## D0 目标与边界

- 目标：模型看见真实 OS/默认壳；`code_run` 按方言执行；缺解释器 fail-closed。
- 边界：不碰 MCP/远程执行面 OS；不拆双工具；不做 Phase 2 回喂；iOS ≠ macOS。

## D1 环境快照（EnvironmentSnapshot）

纯数据（dataclass 或 TypedDict），由探测函数产出，可被测试替身整体替换：

| 字段 | 类型 | 说明 |
|---|---|---|
| `os` | `str` | `Windows` / `Darwin` / `Linux`（其它归 `Other`） |
| `default_shell` | `str` | `powershell` / `bash` / `unknown` |
| `shell_label` | `str` | 给人看的短标签，如 `pwsh 7.4` / `powershell 5.1` / `bash` |
| `path_style` | `str` | `windows` / `posix` |
| `has_pwsh` | `bool` | PATH 上是否有 `pwsh` |
| `has_powershell` | `bool` | PATH 上是否有 `powershell`（Win） |
| `has_bash` | `bool` | PATH 上是否有 `bash` |

**默认壳映射（钉死）**：

| `os` | `default_shell` |
|---|---|
| Windows | `powershell` |
| Darwin / Linux | `bash` |
| Other | `unknown`（事实块仍注入 OS；`code_run` 缺省 type 保持今日 `bash` 字面默认或要求显式——见 D3） |

可选配置覆盖（若本 change 引入）：`tools.code_run.default_type` ∈ schema 枚举；
**缺省不配** ⇒ 上表。不引入则 D3 只认平台表。

## D2 Phase 0：系统提示块

装配点：`BuiltinPlanner._system_prompt`（或等价装配器），在「可用工具」**之前**插入独立块，
避免埋进工具 description 才被看见。

块标题建议：`运行环境：`

正文最小集合（有界，≤ ~400 字）：

1. OS + default_shell + shell_label（版本可得则带）；
2. 路径：windows ⇒ 可用盘符与 `\`/`/`，**勿**假设 `/usr`、`/tmp` 为 POSIX 根；
3. 句法：default=powershell ⇒ 避免 bash 独有的 `&&` 链 / `export` / heredoc；改用 PS 等价或多次调用；
4. 一句：文件读写优先 `file_*`，shell 仅用于真正需进程的操作。

**注入依赖**：planner 构造注入 `env_snapshot: EnvironmentSnapshot | Callable[[], EnvironmentSnapshot] | None`；
`None` ⇒ **不产块**（既有单测 / 离线替身逐字不变）。组合根生产装配注入真实探测。

## D3 Phase 1：`code_run` 方言

### Schema

```text
type: enum ["python", "bash", "powershell"]
# 缺省：不写死在 JSON Schema default（各端点对 default 支持不一）；
# 由 handler 在 type 缺省/空时按 EnvironmentSnapshot.default_shell 解析：
#   powershell → "powershell"
#   bash | unknown → "bash"（unknown 保持与今日「未传则 bash」兼容）
```

`python` 行为不变（`sys.executable -c`）。

### 执行映射

| type | argv（示意） |
|---|---|
| `python` | `[sys.executable, "-c", script]` |
| `bash` | `["bash", "-c", script]` |
| `powershell` | `[pwsh|powershell, "-NoProfile", "-Command", script]` |

PowerShell 解释器选择：`has_pwsh` ⇒ `pwsh`；否则 `has_powershell` ⇒ `powershell`；
两者皆无 ⇒ 结构化错误（如 `SHELL_UNAVAILABLE` / 既有执行失败码 + 明确 message），
**不得**改跑 bash。

`type=bash` 但 `has_bash` 假 ⇒ 同样结构化错误，不得改跑 powershell。

### Description

工具描述须列出三方言与「Windows 缺省 powershell、*nix 缺省 bash；显式 type 优先」。

## D4 TUI 标题

`repl`（或后继）中 `tools.code_run` 友好名不再恒为 `"Bash"`：

- 按动作 `args.type`（缺省已解析后的有效 type）映射：
  `powershell` → `PowerShell`，`bash` → `Bash`，`python` → `Python`；
- 括号摘要仍取 `script` 首行（既有口径）。

## D5 错误与兼容

- 超时 / 截断 / 确认门 / coeffect：**不变**。
- Windows 上旧会话习惯传 `type=bash`：若已装 Git Bash ⇒ 仍可跑；未装 ⇒ 清晰失败（促使用
  powershell 或装 bash），符合 fail-closed。
- 单元测试：用注入 snapshot，**禁止**依赖开发机真实 PATH 断言绿。

## D6 测试表

| # | 断言 |
|---|---|
| 2.1 | 探测：Win 快照 default_shell=powershell；Linux/Darwin=bash |
| 2.2 | planner：注入 snapshot ⇒ 系统提示含「运行环境」块与 OS/壳关键字；`None` ⇒ 无该块 |
| 2.3 | code_run：powershell 走 pwsh/powershell argv；缺解释器 ⇒ 结构化错、不调 bash |
| 2.4 | code_run：缺省 type 在 Win snapshot 下解析为 powershell；*nix 为 bash |
| 2.5 | bash 缺解释器 ⇒ 结构化错、不改 powershell |
| 2.6 | python 路径回归 |
| 2.7 | TUI：type=powershell ⇒ 标题含 PowerShell；bash ⇒ Bash |

## D7 与对标产品的差异（诚实）

| | Claude | Cursor | 本 change |
|---|---|---|---|
| 工具面 | Bash + PowerShell 两工具 | 单 Shell | 单 `code_run` 多 type |
| 主壳 | Win 上 PS primary | 探测 pwsh/5.1 | Win 默认 powershell |
| Prompt | 易漂移（已知 bug） | `Shell: …` | 显式「运行环境」块 + 可测注入 |
| 权限 | 分规则、deny 联动 | IDE allowlist | 沿用既有 code_run 确认门（不拆） |
