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

    # 记忆（会话维度：session_id 由 create_session 生成并无改写透传至 loop 与记忆写入）
    def get_memory(self, session_id: str) -> dict:
        """读会话记忆：只返回归属该会话的条目（他会话与未归属条目不可见）。"""
    def compact(self, session_id: str) -> None:
        """压实该会话记忆：触发存储层真实压实（按会话聚合摘要 + 重要度写回，可撤销）。"""

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

    # 宠物：激活（三入口之一）+ 控制面（change `0088`）；组合根装配，None 时报 UI_PET_UNSET
    pet_activator: PetActivator | None
    def activate_pet(self, user_input: str) -> str:
        """WebUI 自然语言激活宠物（`/pet <描述>` 落到此；返回会话 id）。"""
    def pet_command(
        self, verb: str, *, session_id: str | None = None, goal: str | None = None
    ) -> Any:
        """前台 `/pet [cmd]` 控制面：verb → 会话操作。

        `status` / `sleep` / `wake` / `assign` / `stop` 经注入的 `PetControl` 收口
        （与 CLI `pet <verb>` **同一实现**，见 `pet-mode-interface.md` §5.3）；
        未接 ⇒ `UI_PET_UNSET`，未知动词 ⇒ `UI_PET_UNKNOWN_VERB`。
        """
```

### 1.1 流式事件（SSE）

| 事件 | 载荷 | 说明 |
|---|---|---|
| `session.created` | session_id | 会话建立 |
| `loop.perception` | turn_id, observation | 感知阶段 |
| `loop.reasoning` | turn_id, plan | 推理阶段（折叠块展示） |
| `loop.action` | turn_id, action | 回合推进（step_completed 映射，既有契约） |
| `loop.action_started` | round, tool_id, args | 工具动作开工（⏺ 动作行，TUI 折叠块呈现） |
| `loop.action_completed` | round, tool_id, ok, duration_ms, output | 工具动作收尾（标题落 ✓/✗+耗时，展开含输出节选） |
| `loop.result` | turn_id, result | 结果回传 |
| `loop.error` | turn_id, error | 结构化错误（不中断循环） |
| `task.*` | 编排事件载荷 | 任务进度（task_started / plan_ready / wave_started / subtask_started / subtask_completed / task_checkpoint / task_finished / task_failed，type 前缀 `task.`；TUI 时间线呈现：任务/波次浅灰单行，子任务 Collapsible 折叠块，展开含验收/判定/结果节选） |

### 1.2 HTTP 端点清单（WebBridge.serve）

`WebBridge.serve(host, port)` 将 `UIAPILayer` 11 方法暴露为 HTTP 端点（REST + SSE）：

| 端点 | 方法 | 映射 | 说明 |
|---|---|---|---|
| `POST /session` | create_session | `create_session(mode)` | 新建会话（登记至共享注册表，见 §1.3） |
| `GET /sessions` | list_sessions | `list_sessions()` | 枚举对话会话（`{session_id, mode, created_at}` + 注入转录时的派生 `title`/`updated_at`，见 §1.3.1） |
| `GET /session/{id}/messages` | session_messages | `session_messages(session_id)` | 读该会话**对话转录**（按追加次序）；未登记仍 `UI_SESSION_NOT_FOUND` |
| `POST /run` | run_loop | `run_loop(session_id, user_input)` | SSE 流式 loop 事件 |
| `POST /barge-in` | barge_in | `barge_in()` | 打断当前语音播报 |
| `GET /memory` | get_memory | `get_memory(session_id)` | 读会话记忆（只含本会话归属条目） |
| `POST /session/compact` | compact | `compact(session_id)` | 压实该会话记忆（存储层真实压实，可撤销） |
| `GET /tools` | list_tools | `list_tools()` | 列出工具 |
| `POST /tools/invoke` | invoke_tool | `invoke_tool(tool_id, args)` | 调用工具 |
| `GET /llm-config` | get_llm_config | `get_llm_config()` | 读 LLM 配置（含**生效**预算，见 §1.4） |
| `PUT /llm-config` | apply_llm_config | `apply_llm_config(cfg, output_reserve, max_rounds, history_turns)` | 保存 LLM 配置（原子落盘 + 热生效） |

**`/llm-config` 字段口径**（change `0099`）：`GET` 回 `provider` / `model` / `endpoint` / `api_key_ref` /
`reasoning_effort` / `embedding_model` / `context_window` / `max_rounds` / `token_budget`；后两者为
**派生后的生效值**（`token_budget = context_window − output_reserve`，见 ADR-0091），无配置源时为 `null`。
`PUT` 收 `provider` / `model` / `endpoint` / `api_key_ref`（**只接受 `${VAR}` 引用，明文拒绝**）/ 可选
`reasoning_effort` / `embedding_model` / `context_window` / `output_reserve` / `max_rounds` /
`history_turns`（change `0115`）。

- **落盘**：`PUT` 经 `UIAPILayer.apply_llm_config` → `apply_change`（校验）→ `write_patch`（**原子提交**）→ 重读，
  一次 patch 承载 `llm` 与 `loop` 两段 ⇒ 不留半写状态；写盘失败**旧文件逐字不变**、内存回退。
- **热生效**：保存后按 `LimitsConfigurable` 协议把派生上限推给**运行中**的 loop（不支持者静默跳过）；
  `set_llm_config`（启动期 hydrate）**不落盘**，二者分工见 ADR-0092。
- **失败**：非法取值 / 落盘失败 ⇒ `UI_LLM_CONFIG_INVALID`（HTTP 400）。

### 1.3 会话注册表（SessionRegistry）

对话会话标识的**创建 / 校验**事实来源。可落盘（`path=$CORE_STATE_DIR/conversations.json`）⇒
CLI / Web / Desktop 三入口（含各自独立进程）共享同一注册表；`path=None` ⇒ 纯内存
（缺省，后向兼容既有进程内语义）。

| 方法 | 说明 |
|---|---|
| `create(mode) -> str` | 新建会话（**读回 → 合并 → 写回**），返回 32 位 hex；**进程内互斥**（`RLock`） |
| `exists(session_id) -> bool` | 是否已登记（**每次读透磁盘**） |
| `list() -> list[{session_id, mode, created_at}]` | 枚举全部会话（**每次读透磁盘**） |

- **读透 + 写时合并**（非「ctor 载入一次」）：长驻 `serve` 进程可即时见到 CLI 新建的会话。
  注册表为**派生状态**，文件缺失 / 损坏 ⇒ 空态启动（不阻断）。
- **并发口径（change 0115 据实收窄）**：`create` 以**进程内互斥**保护，**同进程多线程**并发创建
  互不覆盖；**跨进程**同刻并发创建**不受保护**（进程内锁不跨进程，属已知局限，不得据此断言跨进程安全）。
- **fail-closed 不放宽**：未登记 id 仍抛 `UI_SESSION_NOT_FOUND`。
- 与 `sessions.jsonl`（`HarnessHost` **连接记录**，`session-{N}` 另一套 id 空间，见 `core-agent sessions`）
  **名与义均不同**。取舍见 `ADR-0089`。

#### 1.3.1 枚举条目的派生字段（change 0115 / ADR-0108）

注入转录存储（`UIAPILayer(transcript=...)`）时，`GET /sessions` 的条目**逐条**附派生字段：
`title`（该会话**首条用户消息**截断 30 字；无用户消息 ⇒ **空串**，不伪造标题）与
`updated_at`（最近一条转录时间戳；该会话无转录 ⇒ 回落注册表 `created_at`）。派生值**不写注册表**
（注册表只承载标识与模式，避免第二真源）。**未注入**转录 ⇒ 条目形状逐字不变（只增不减）。
数据面见 `memory-interface.md` §1.1。

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
    def start_sidecar(self) -> None: ...   # spawn `sys.executable -m core.entry serve …`（change 0100）
```

**sidecar 拉起口径（change 0100 / ADR-0093 ④）**：列表形式 argv、**不经 shell**、用 `sys.executable`
（同解释器）；固定 `--host 127.0.0.1 --port <port>`（端口取自 `DesktopBridge(port=…)`，CLI 面为 `app --port`）。
失败（`OSError`）⇒ `UI_SIDECAR_FAILED`，**不静默成功**。离线验证经 `start_impl` 注入缝（不真起 uvicorn）。

**CLIBridge 交互会话循环（REPL）**：`connect()` 进入 Textual 交互循环（而非仅返回 `UIAPILayer`）——无子命令时进 REPL，多轮上下文保持，`barge_in()` 支持打断语音播报；运维命令面（status/doctor/logs/install/mcp/auth/gateway）复用 cli-ops，不并入 REPL。

**会话续聊（change 0116 / ADR-0109）**：`CLIBridge(api=…, session_id=…)` 的会话标识透传至
`run_repl` → `build_app`；非空 ⇒ **复用**该会话（载入其转录铺进时间线；未登记 ⇒ `UiError`，
fail-closed，先于进入 TUI 拒绝），缺省 ⇒ 新建（既有行为不变）。CLI 侧读取面：
`core-agent session show <session_id>` 打印同一 `TranscriptStore` 的会话转录（未登记以非零退出码拒绝）。

**Web 会话列表面（change 0116 / ADR-0109）**：SPA 由 `GET /sessions` 呈现右栏会话列表
（派生标题 + 最近活跃，**呈现层**降序），点选经 `GET /session/{id}/messages` 渲染转录并继续对话；
会话标识与列表由 `App.svelte` 单点持有，「新建会话」为**显式**动作（无选中会话时发送被拒，
不隐式建会话 ⇒ 列表不留空会话）。

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
| `UI_LLM_KEY_UNSET` | LLM API Key 未配置 / 传入明文（change `0099`） |
| `UI_LLM_CONFIG_INVALID` | LLM 配置非法或落盘失败（HTTP 400，change `0099`） |
| `UI_SESSION_NOT_FOUND` | 会话不存在 |
| `UI_MODALITY_MISSING` | 模型不具备该模态理解能力 |
| `UI_BARGEIN` | 语音播报被打断（barge-in） |
| `UI_SIDECAR_FAILED` | 桌面 sidecar 后端拉起失败（change `0100`） |
| `UI_ORCHESTRATOR_UNSET` | 编排器未注入（run_task 前校验） |
| `UI_PET_UNSET` | 宠物激活器 / 控制面未注入（`activate_pet` / `pet_command` 前校验） |
| `UI_PET_UNKNOWN_VERB` | `pet_command` 收到未支持的控制动词（change `0088`） |

---

## 6. 关联

- 模块：`06-ui-frontend/ui-architecture.md`
- 规格：`openspec/specs/ui/spec.md`
- LLM 归一化：经 `llm-provider` 虚拟接口调用（可替换默认实现）
- 决策：ADR-0013 ~ 0015、ADR-0031、ADR-0083（宠物控制面）
- 测试：`04-testing/test-cases.md`（TC-UI 系列）
