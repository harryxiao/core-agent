# 接口设计：工具接口（Tool Use Interface）

> 层：L1 ｜ 对应规格 `tool-use/spec.md` ｜ 模块 `02-modules/tool-use.md`

---

## 1. ToolDef（工具契约）

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
```

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
| `tools.code_run` | `script`, `type`, `timeout`, `cwd` | 执行代码 |
| `tools.file_read` | `path`, `start`, `count` | 读文件 |
| `tools.file_write` | `path`, `content`, `mode` | 写文件 |
| `tools.file_patch` | `path`, `old_content`, `new_content` | 精确替换 |
| `tools.web_scan` | `text_only`, `switch_tab_id` | 读页面 |
| `tools.web_execute_js` | `script`, `switch_tab_id` | 执行页面 JS |
| `tools.web_fetch` | `url`, `timeout` | GET 抓取网页（仅 http/https，出站经确认门） |
| `tools.ask_user` | `question`, `candidates` | 人机确认 |
| `tools.process` | `action`, `pid` | 进程管理（精确 PID） |
| `tools.memory` | `layer`, `action`, `entry` | 记忆读写 |

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
