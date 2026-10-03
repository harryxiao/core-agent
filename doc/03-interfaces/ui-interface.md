# 接口设计：UI 界面接口（UI Interface）

> 层：交互层（三模入口） ｜ 对应规格 `ui/spec.md` ｜ 模块 `06-ui-frontend/ui-architecture.md`

---

## 1. 统一后端 API（FastAPI）

三种模式复用同一内核与同一 LLM 配置，走同一套后端 API（HTTP + SSE），不各自维护一份实现。

```python
# 统一 API 层（三模共用，CLI 也不绕过）
class UIAPILayer:
    # 会话与循环
    def create_session(self, mode: str) -> str: ...
    def run_loop(self, session_id: str, user_input: str) -> AsyncIterator[Event]:
        """SSE 流式输出 loop 事件：perception / reasoning / action / result。"""
    def barge_in(self) -> None: ...
        """打断当前语音播报（barge-in）：语音输出为抽象能力（TTS 后端未接）。"""

    # 任务编排（TUI `/task` / 复用 CLI 同一编排器）
    def run_task(self, session_id: str, goal: str) -> AsyncIterator[Event]:
        """SSE 流式输出编排任务进度事件（task.*）；编排器未注入时 UI_ORCHESTRATOR_UNSET。"""

    # 记忆
    def get_memory(self, session_id: str) -> dict: ...
    def compact(self, session_id: str) -> None: ...

    # 工具
    def list_tools(self) -> list[Tool]: ...
    def invoke_tool(self, tool_id: str, args: dict) -> ToolResult: ...

    # LLM 配置（三模唯一配置源）
    def get_llm_config(self) -> LLMConfig: ...
    def set_llm_config(self, cfg: LLMConfig) -> None: ...

    # 审批通道（高风险工具 confirm 门的终端 y/n 交互；非交互入口为 None）
    approval: ApprovalChannel | None

    # 编排器注入（组合根装配；None 时 run_task 报 UI_ORCHESTRATOR_UNSET）
    orchestrator: TaskScheduler | None
```

### 1.1 流式事件（SSE）

| 事件 | 载荷 | 说明 |
|---|---|---|
| `session.created` | session_id | 会话建立 |
| `loop.perception` | turn_id, observation | 感知阶段 |
| `loop.reasoning` | turn_id, plan | 推理阶段（折叠块展示） |
| `loop.action` | turn_id, action | 行动阶段（含 diff / 审批提示） |
| `loop.result` | turn_id, result | 结果回传 |
| `loop.error` | turn_id, error | 结构化错误（不中断循环） |
| `task.*` | 编排事件载荷 | 任务进度（task_started / plan_ready / wave_started / subtask_started / subtask_completed / task_checkpoint / task_finished / task_failed，type 前缀 `task.`） |

### 1.2 HTTP 端点清单（WebBridge.serve）

`WebBridge.serve(host, port)` 将 `UIAPILayer` 9 方法暴露为 HTTP 端点（REST + SSE）：

| 端点 | 方法 | 映射 | 说明 |
|---|---|---|---|
| `POST /session` | create_session | `create_session(mode)` | 新建会话 |
| `POST /run` | run_loop | `run_loop(session_id, user_input)` | SSE 流式 loop 事件 |
| `POST /barge-in` | barge_in | `barge_in()` | 打断当前语音播报 |
| `GET /memory` | get_memory | `get_memory(session_id)` | 读会话记忆 |
| `POST /session/compact` | compact | `compact(session_id)` | 压实上下文 |
| `GET /tools` | list_tools | `list_tools()` | 列出工具 |
| `POST /tools/invoke` | invoke_tool | `invoke_tool(tool_id, args)` | 调用工具 |
| `GET /llm-config` | get_llm_config | `get_llm_config()` | 读 LLM 配置 |
| `PUT /llm-config` | set_llm_config | `set_llm_config(cfg)` | 写 LLM 配置（热更新） |

---

## 2. 三模桥接

| 模式 | 入口 | 桥接方式 | UI 层 |
|---|---|---|---|
| CLI | `core-agent` | Textual 层直连内核，但同样调统一 API 层，保证行为/鉴权/日志一致 | `src/cli/`（app.py + widgets/ + bridge.py） |
| Web | `core-agent serve` | HTTP + SSE 打开单 SPA | Svelte/React SPA（chat / 会话管理 / 用量 / 设置） |
| Desktop | `core-agent.app` | Tauri 壳复用同一 SPA + sidecar 拉起 Python 后端 | 与 Web 100% 一致 |

```python
class CLIBridge:      # ① CLI：Textual → 统一 API（同进程，无 IPC）
    def connect(self) -> UIAPILayer: ...

class WebBridge:      # ② Web：FastAPI 暴露 HTTP + SSE
    def serve(self, host: str, port: int) -> None: ...

class DesktopBridge:  # ③ Desktop：Tauri 壳 + sidecar
    def start_sidecar(self) -> None: ...
```

**CLIBridge 交互会话循环（REPL）**：`connect()` 进入 Textual 交互循环（而非仅返回 `UIAPILayer`）——无子命令时进 REPL，多轮上下文保持，`barge_in()` 支持打断语音播报；运维命令面（status/doctor/logs/install/mcp/auth/gateway）复用 cli-ops，不并入 REPL。

**Web Client 与 Host 分离**：Web 前端（SPA）作为纯静态资源独立托管，`WebBridge` 仅暴露统一后端 API；前端经该 API 连接远程 / 本机常驻 Harness Host（见 `deployment-interface.md`），前端升级无需重启 Host 后端。

---

## 3. LLM 配置源（单一配置）

LLM API（provider / endpoint / key / base URL）只在后端配置一次：

- `config.yaml`（声明式默认）
- `settings.local.json`（本地覆盖，密钥隔离）

三模不重复配置；`set_llm_config` 热更新，无需重启。

---

## 4. 约束（四条设计原则）

1. **前端单一代码库**：Web 与 Desktop 跑同一 SPA 构建产物，桌面只是换个壳。
2. **桌面壳职责最小化**：Tauri 只做开窗口 / 挂 SPA / 启 sidecar 三件事。
3. **统一 API 解耦**：三模走同一后端 API（HTTP + SSE），CLI 的 Textual 层也不绕过。
4. **单一配置源**：LLM API Key 只在后端配置一次，三模不重复配置。
5. **前后端解耦部署**：Web 前端独立托管、独立升级，经统一后端 API 连接常驻 Harness Host，前端发布不要求后端重启。

---

## 5. 错误码

| 错误码 | 含义 |
|---|---|
| `UI_LLM_KEY_UNSET` | LLM API Key 未配置（运行 loop 前校验） |
| `UI_SESSION_NOT_FOUND` | 会话不存在 |
| `UI_MODALITY_MISSING` | 模型不具备该模态理解能力 |
| `UI_BARGEIN` | 语音播报被打断（barge-in） |
| `UI_ORCHESTRATOR_UNSET` | 编排器未注入（run_task 前校验） |

---

## 6. 关联

- 模块：`06-ui-frontend/ui-architecture.md`
- 规格：`openspec/specs/ui/spec.md`
- LLM 归一化：经 `llm-provider` 虚拟接口调用（可替换 LiteLLM）
- 决策：ADR-0013 ~ 0015、ADR-0031
- 测试：`04-testing/test-cases.md`（TC-UI 系列）
