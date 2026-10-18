# 模块设计：工具使用（L1 Tool Use）

> 对应规格：`doc/openspec/specs/tool-use/spec.md` ｜ 接口：`doc/03-interfaces/tool-use-interface.md`

---

## 1. 模块定位

L1 提供**最小可逆能力单元（原子工具）**。原子工具是 LLM 可调用的最小动作，每个都满足：

> **副作用 + 撤销 + Schema + coeffect 声明** 四要素齐全，缺失其一不能成为原子工具。

---

## 2. 原子工具清单（MVP，≥9 个）

| 工具 | 类别 | 副作用 | 撤销（undo） | 可逆 |
|---|---|---|---|---|
| `code_run` | 执行 | 运行代码（可能有文件/网络副作用） | 通过 EffectTracker 回滚文件副作用 | 部分 |
| `file_read` | 读 | 无 | —— | 是（纯读） |
| `file_write` | 写 | 写文件 | 恢复原内容/删除新文件 | 是 |
| `file_patch` | 写 | 修改文件 | 恢复原片段 | 是 |
| `web_scan` | 读 | 无 | —— | 是（纯读） |
| `web_execute_js` | 执行 | 执行页面 JS（可点击/提交） | 视操作而定，标注 irreversible | 部分 |
| `ask_user` | 交互 | 中断问询 | —— | 是（无破坏） |
| `process` / `process_kill` | 进程 | 巡检 / 终止本进程启动的后台任务 | 巡检只读；终止不可逆（确认门） | 部分 |
| `memory_tool` | 记忆 | 写记忆 | 删除/回滚记忆条目 | 是 |

> `file_read`/`file_write`/`file_patch` 对应现有 `file_read`/`file_write`/`file_patch` 能力；
> `web_scan`/`web_execute_js` 对应现有 `web_scan`/`web_execute_js`；其余为 CORE 抽象后的统称。
>
> **覆盖写原子性**（change `0257`／ADR-0248）：`file_write` 的覆盖模式（`w` / `write` /
> `overwrite`）先在同目录写临时文件并 `flush` + `fsync`，保留既有文件权限位后 `os.replace`
> 原子替换；失败清理临时文件、目标逐字不变。追加模式（`a` / `append`）语义不变；撤销快照仍记录
> 写入前原内容（写入成功后压栈），撤销语义逐字不变。

---

## 3. 关键设计

### 3.1 工具契约（四要素）

```python
@dataclass
class ToolDef:
    tool_id: str                 # 全局唯一，如 "tools.code_run"
    schema: dict                 # JSON Schema，供 LLM 与校验
    coeffects: list[str]         # 执行前需注入的环境约束
    reversible: bool             # 是否可逆
    undo_hint: str               # 撤销策略说明
```

- 参数非法 → 返回结构化错误 `{"code":"INVALID_ARGS","errors":[...]}`，不抛异常给模型。
- 每个工具必须声明 `coeffects`（如 `code_run` 声明 `["filesystem:read", "constitution:v1"]`）。

### 3.2 可逆效应接入（与 L0 联动）

- 写类工具执行时向 `EffectTracker.record(effect, undo)` 注册撤销闭包。**撤销闭包按次生成**
  （change `0129` / ADR-0122 / E64）：每次成功执行后取**一份**绑定**该次**写入前快照的闭包 ⇒ 同一
  工具实例跨多次调用**各持独立快照**，撤销第 N 次恢复该次内容、跨 trace 不串（`Tool.undo` 为工厂
  `Callable[[], Callable[[], None]]`）。
- 纯读工具（`file_read`/`web_scan`）不产生效应，天然可逆。
- `code_run` 属"灰盒"：其内部文件副作用由沙箱/监控归因，能恢复的恢复，不能恢复的标注 `irreversible`。

### 3.3 确认门（Safety Gate）

| 操作 | 是否需确认 |
|---|---|
| 只读（read/scan） | 否 |
| 可逆写（write/patch 到非关键路径） | 否（可自动回滚） |
| 不可逆/高风险（rm、杀进程、系统级、支付、写密钥文件） | **是**（ask_user） |

### 3.4 资源与超时

- 每个工具声明 `timeout` / `max_output` 上界；超限截断或中止，不拖垮 loop。
- **`code_run` 输出首尾保留**（change `0264` / ADR-0254）：前景 `stdout` / `stderr` 超过
  `_MAX_OUTPUT_CHARS`（8192）时保留头部约 1/3 与尾部其余，中间以 `…[truncated N chars]…`
  分隔，总长仍 ≤ 上限；`*_truncated` 判据不变。仅前景结果，后台日志文件不截断。
- 工具执行异常被捕获为结构化结果，回传给模型而不是崩溃。
- **同步 handler 卸载（change `0265` / ADR-0255）**：`ToolProvider._call` 对非协程 handler 经
  `asyncio.to_thread` 在工作线程执行，协程 handler 仍在事件循环上 await —— 多个 `ainvoke`
  可真并发，普通调用不再阻塞事件循环。`asyncio.wait_for` 超时只停止等待、不能终止已进入的
  工作线程（已知局限；同步 handler 均为本地短操作）。
- **子进程治理（change `0259` / ADR-0249）**：`code_run` 前景以独立进程组启动（POSIX
  `start_new_session` / Windows `CREATE_NEW_PROCESS_GROUP`）；超时 / 取消终止**整棵进程树**并归一
  `TIMEOUT`，不遗留仍可写文件的子进程。`timeout` 缺省 120s、上限 600s（有限数校验）。
  后台任务（`background=true`）写 0600 日志并登记到有界注册表，经 `tools.process` 巡检、
  `tools.process_kill` 终止；注册表不存脚本正文。
- **后台任务跨重启登记（change `0266` / ADR-0256）**：注册表元数据（pid / 输出路径 / 启动时间 /
  运行类型 / 启动时刻标识）原子落盘 `$CORE_STATE_DIR/processes.json`（0600，临时文件 + `fsync`
  + `os.replace`）；进程重启后加载为**恢复项**（`proc=None`），`list` / `status` / `output`
  可用并标 `restored=true`。恢复项存活用 `kill(pid, 0)` 探测（Windows 改用 `OpenProcess`），
  Linux 再核对 `/proc/<pid>/stat` starttime 防 PID 复用。恢复项**只读**：`process_kill`
  返回 `killed=false` / `restored=true`，不触达进程（无句柄、非 Linux 无身份核对）。
  落盘失败与损坏文件均静默降级，不阻断后台任务登记。

---

## 4. 工具聚合（ToolProvider）

`ToolProvider` 把注册表中**当前 profile 激活的**工具聚合为 LLM 可见的 tool schema 列表：

```
Provider.active_tools() -> [ToolDef...]   # 供 loop 的 Reason 阶段注入
Provider.invoke(tool_id, args) -> Result  # 统一调用入口（含效应追踪 + 校验 + 确认门）
```

调用前 schema 校验**不在此层实现**：口径唯一真源为 `constraints.Validator.validate_input`，
`ToolProvider` **委托**之（`tools → constraints`，与 `loop → constraints` 同型；change `0059`）。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 参数不符合 schema | 结构化 `INVALID_ARGS`，不执行 |
| coeffect 缺失 | `COEFFECT_MISSING`，拒绝执行 |
| 执行超时 | 中止，返回 `TIMEOUT` |
| undo 失败 | 进入 QUARANTINE，人工介入 |

---

## 6. 关联

- 规格：`doc/openspec/specs/tool-use/spec.md`
- 插件基底：`doc/02-modules/plugin-registry.md`
- 接口：`doc/03-interfaces/tool-use-interface.md`
- 测试：`doc/04-testing/test-cases.md`（TOOL 系列）
