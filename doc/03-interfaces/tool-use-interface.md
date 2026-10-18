# 接口设计：工具接口（Tool Use Interface）

> 层：L1 ｜ 对应规格 `tool-use/spec.md` ｜ 模块 `02-modules/tool-use.md`

---

## 1. ToolDef（工具契约）与 Tool（运行时原子）

```python
@dataclass
class ToolDef:
    tool_id: str            # tools.code_run
    description: str        # 供 LLM 阅读的用途说明
    schema: dict            # JSON Schema（参数定义，供 LLM 与校验）
    coeffects: list[str]    # 执行前需注入的约束
    reversible: bool
    timeout_s: float = 30.0
    max_output: int = 8192

@dataclass
class Tool:
    definition: ToolDef
    handler: Callable[..., Any]
    undo: Callable[[], Callable[[], None]] | None = None   # 撤销闭包**工厂**
```

`undo` 是**按次生成**的工厂，不是一次性闭包（change `0129` / ADR-0122 / 账本 E64）：

- 写类工具每次成功执行后，`ToolProvider` 取一次 `tool.undo()` 得到**绑定该次写入前快照**的
  撤销闭包，交 `EffectTracker.record(effect, undo)` 记账；
- 同一工具实例跨多次调用**各持独立快照**（按 trace 的 LIFO 序）⇒ 撤销第 N 次恢复**该次**写入前
  的内容，SHALL NOT 被后续调用覆写、SHALL NOT 跨 trace 串写；
- 快照栈为空时工厂返回 **no-op 闭包**（未写入即撤销不报错）。
- 纯读工具 `undo=None`。

---

## 2. ToolProvider 接口

```python
class ToolProvider:
    def active_tools(self) -> list[ToolDef]:
        """返回当前 profile 激活的工具 schema 列表（供 loop 注入）。"""

    def invoke(self, tool_id: str, args: dict, *, trace_id: str, approved: bool = False) -> ToolResult:
        """统一调用入口：schema 校验 → coeffect 解析 → 确认门 → 执行 → 效应记录。"""

    async def ainvoke(self, tool_id: str, args: dict, *, trace_id: str, approved: bool = False) -> ToolResult:
        """异步统一调用入口：与 invoke 同构，事件循环内非阻塞，支持真并发执行。

        确认门判 confirm 时经 approver 请求人工批准（approved=True 表示上层
        已批准、跳过重复询问）；无 approver 时 fail-closed 返回 IRREVERSIBLE_BLOCKED。"""
```

调用前 schema 校验（必填 / 类型）**口径单一真源**为 `constraints.Validator.validate_input`，
`ToolProvider` 委托之、不另实现副本（change `0059`；拒绝码 `INVALID_ARGS` 与错误消息不变）。

`ToolResult`：

```python
@dataclass
class ToolResult:
    ok: bool
    data: Any                # 工具输出
    error: ToolError | None  # 结构化错误
    effect_id: EffectId | None
```

`ToolError`：

```python
@dataclass
class ToolError:
    code: str                # INVALID_ARGS / COEFFECT_MISSING / TIMEOUT / ...
    message: str
    details: dict
```

---

## 3. 内置工具签名（示例）

| tool_id | 主要参数 | 说明 |
|---|---|---|
| `tools.code_run` | `script`, `type`, `timeout`, `cwd`, `background` | 执行代码（缺省 timeout 120s、上限 600s；`background=true` 立即返回 pid + 日志路径） |
| `tools.file_read` | `path`, `start`, `count` | 读文件 |
| `tools.file_write` | `path`, `content`, `mode` | 写文件 |
| `tools.file_patch` | `path`, `old_content`, `new_content` | 精确替换 |
| `tools.web_scan` | `text_only`, `switch_tab_id` | 读页面 |
| `tools.web_execute_js` | `script`, `switch_tab_id` | 执行页面 JS |
| `tools.web_fetch` | `url`, `timeout` | GET 抓取网页（仅 http/https，出站经确认门） |
| `tools.ask_user` | `question`, `candidates` | 人机确认 |
| `tools.process` | `action`, `pid`, `max_chars` | 后台任务巡检（`list` / `status` / `output`；只读可逆，`process:read`；仅本进程注册表内任务；`output` 读日志尾部，缺省 8K、上限 64K） |
| `tools.process_kill` | `pid` | 终止本进程启动的后台任务及其后代（`process:write` + 不可逆 ⇒ 确认门；未知 pid `found=false`） |
| `tools.memory` | `layer`, `action`, `entry` | 记忆读写 |
| `tools.install` | `source`, `kind`, `name` | 安装插件（discover→verify→install→register→activate；写 + 不可逆 ⇒ 走确认门） |
| `tools.uninstall` | `plugin_id` | 卸载插件（deactivate→uninstall 对称回退；写 + 不可逆 ⇒ 走确认门） |
| `tools.list` | — | 列出已装插件（只读，`coeffects=[]`） |
| `tools.gate_run` | `gate` | 按名运行质量门禁（`lint`/`typecheck`/`test`/`build`）；门禁名与门禁命令取自 `ci-cd` **单一真源** `GATE_COMMANDS`，**执行器经组合根注入**（工具层不依赖 L5）；`coeffects=["process:spawn","filesystem:write"]` + 不可逆 ⇒ 走确认门；`timeout_s=660` > 执行器内部 600 上界 |
| `tools.context_read` | `pointer` | 按信息地图指针（`doc_id#section`）取文档片段详情（只读，`coeffects=[]` + 可逆 ⇒ 自动放行）；**取数器经组合根注入**（工具层不依赖 context 层）；指针无命中返空串不报错（context spec「信息地图」；change 0140 / ADR-0133） |

> 上表为示例清单。插件安装三工具（`tools.install` / `tools.uninstall` / `tools.list`）经组合根
> `build_runtime` 注册进**生产工具面**、与 `Runtime.installer` **同一实例**（change 0108 / 账本 E33）。
> `tools.gate_run`（change 0111 / phase-27 切片 S1）同样经组合根注册进**生产工具面**，但**只挂主工具面**：
> 子 Agent / 宠物 loop 的注入点不含它（不扩散越界暴露面）；未知门禁名 fail-closed（不触达执行器）。
> `tools.context_read`（change 0140 / 账本 E77）同样经组合根注册进**生产工具面**：它是「信息地图按需取详情」
> 的**模型侧唯一通道**（`DynamicAssembler.fetch_detail` 此前零生产调用点）；工具 id 含 `read` 词元 ⇒
> 权限分级按**完整词元**判只读放行（不落 deny-by-default）。
>
> **零注入内置集有单一真源**：`core.tools.builtin_tools() -> tuple[Tool, ...]`（change `0162` / ADR-0153）
> 给出**不需注入执行器**的七件（`file_read` / `file_write` / `file_patch` / `code_run` /
> `web_fetch` / `process` / `process_kill`）；`code_run` 与两个进程工具共享**同一份**后台任务注册表；
> 组合根 `build_runtime` 的注册与只读诊断面（`doctor` / `status` 的「内置工具数」）**共用同一份** ——
> 计数面不另抄一张表（`gate_run` / `context_read` 的执行器由组合根注入，故不在其中，另装配）。
>
> **文件工具的 `~` 展开（change `0228` / ADR-0218）**：三个 `file_*` 工具的 `path` 参数在入口做
> **`~` 展开**（`Path(path).expanduser()`，与 `core_profile.loader` 同口径）—— `~/x` 指**家目录**，
> 不再是当前工作目录下的字面 `~` 目录。**无条件**生效（属缺陷修复、非可选能力，不设门）；**只**展开
> `~`（`~user` 一并处理），不 `resolve` / 不 `abspath` / 不展开环境变量；对无 `~` 的路径是恒等变换。
> `file_write` / `file_patch` 把**展开后**路径存入撤销快照 ⇒ 撤销点与写入点一致（**不**误建字面 `~`）。
> 返回体 `{"path": …}` 仍回**模型给的原文**（contract 不变）。
>
> **覆盖写原子性（change `0257` / ADR-0248）**：`file_write` 覆盖模式（`w` / `write` /
> `overwrite`）经同目录临时文件 + `flush` + `fsync` + 保留既有权限位 + `os.replace` 原子替换；
> 失败清理临时文件、目标逐字不变。并发读者只可能看到完整旧内容或完整新内容。追加模式
> （`a` / `append`）语义不变；撤销快照仍在写入成功后压栈（记录写入前原内容）。
>
> **`code_run` 的输出与目录（change `0240` / ADR-0228）**：`stdout` / `stderr` 固定以 **UTF-8**
> 解码（`errors="replace"`），不依赖宿主 locale；PowerShell 子进程在用户脚本前设置
> `[Console]::OutputEncoding`，Python 子进程带 `PYTHONIOENCODING=utf-8`。`cwd` 在入口做
> **`~` 展开**（`Path(cwd).expanduser()`，其余不 `resolve`）；每次调用为**全新进程**，
> `cd` / 环境变量不跨调用保留。显式 `type` 优先于平台缺省。
>
> **进程治理与后台任务（change `0259` / ADR-0249）**：前景执行经
> `core.tools.execution.run_foreground`，以**独立进程组**启动（POSIX `start_new_session` /
> Windows `CREATE_NEW_PROCESS_GROUP`）；超时 / 取消先终止**整棵进程树**（POSIX `killpg(SIGKILL)` /
> Windows `taskkill /T /F`）并回收，再归一为 `TIMEOUT`。`timeout` 缺省 **120s**、允许 `(0, 600]`
> 内的有限秒数（越界 / NaN / inf ⇒ `EXECUTION_FAILED` 且不启动子进程）；工具外层 `timeout_s=660`。
> `background=true` 时 stdout / stderr 合并写入 `$CORE_STATE_DIR/run/<type>-<uuid>.log`
> （目录 0700、文件 0600），立即返回 `pid` / `output_path` / `started_at`；**不接受**模型指定输出路径。
> 后台任务不随 loop 结束强杀，由 `tools.process_kill` 显式终止；注册表有界（32，仅进程内）。
> `tools.process` / `tools.process_kill` 只能看到 / 终止**同一份注册表**内由本进程启动的任务。
>
> **输出首尾保留（change `0264` / ADR-0254）**：前景 `stdout` / `stderr` 超过
> `_MAX_OUTPUT_CHARS = 8192` 时按「头部约 1/3 + `\n…[truncated N chars]…\n` + 尾部其余」
> 返回，总长 **≤ 8192**（错误结论多在尾部）；`stdout_truncated` / `stderr_truncated` 仍按
> 原始长度是否超限判定。该口径只作用于 `code_run` 前景结果；后台日志文件不截断，
> `tools.process output` 只读尾部（默认 8K、上限 64K）。

---

## 4. 确认门接口

```python
class SafetyGate:
    def confirm(self, tool_id: str, args: dict) -> GateDecision:
        """判定该调用是否需要人工确认；返回 confirm/deny/auto。"""
```

- 只读工具 → `auto`
- 可逆写 → `auto`（可自动回滚）
- 不可逆/高风险 → `confirm`（触发 `tools.ask_user`）

---

## 5. 错误码

| code | 含义 |
|---|---|
| `INVALID_TOOL_SCHEMA` | 工具 schema 非法 |
| `INVALID_ARGS` | 参数不符 schema |
| `COEFFECT_MISSING` | 约束缺失 |
| `TIMEOUT` | 执行超时 |
| `EXECUTION_FAILED` | handler 执行异常归一 |
| `GATE_DENIED` | 确认门拒绝 |
| `IRREVERSIBLE_BLOCKED` | 不可逆操作未确认被阻止 |
| `UNDO_FAILED` | 撤销失败 |

---

## 6. 关联

- 模块：`02-modules/tool-use.md`
- 插件契约：`plugin-registry-interface.md`
- 校验口径（委托）：`constraints-interface.md` §2（`Validator.validate_input`）
- 规格：`openspec/specs/tool-use/spec.md`
