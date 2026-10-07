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

    # 神兽：三入口中的两个（WebUI 自然语言 + TUI 斜杠 `/summon` `/recall`，change `0137`）
    # 组合根装配（Runtime.beast_activator），None 时报 UI_BEAST_UNSET；与 pet 同型
    beast_activator: BeastActivator | None
    async def activate_beast(self, user_input: str) -> str:
        """WebUI 自然语言激活神兽（返回 agent_id；神兽激活是异步 handoff ⇒ async）。"""
    async def beast_command(
        self, verb: str, target: str, *, task: str = ""
    ) -> dict[str, object]:
        """前台 `/summon <兽> [任务]` · `/recall <兽>` 控制面（与 CLI 同一激活器）。

        verb → `activate_from_slash` / `recall_from_slash`；返回 `result_summary()`
        摘要 + 会话 `state` —— 结果正文**只经只读查询面**取用。未接 ⇒ `UI_BEAST_UNSET`，
        未知动词 ⇒ `UI_BEAST_UNKNOWN_VERB`，领域错误在边界归一
        （无匹配神兽 ⇒ `UI_BEAST_NOT_FOUND`；状态冲突 ⇒ `UI_BEAST_STATE_INVALID`）。
        """
```

### 1.1 流式事件（SSE）

| 事件 | 载荷 | 说明 |
|---|---|---|
| `session.created` | session_id | 会话建立 |
| `loop.perception` | turn_id, observation | 感知阶段 |
| `loop.reasoning` | text | **思考原文增量**（`Thinking` item 映射；**与 `loop.delta` 同形相异类**，change `0145`/ADR-0137）—— 仅 `show_thinking=True` 时产出，三端**折叠块默认收起**呈现（TUI 单块 `▸ 思考`、同轮增量归并；Web `<details>`；APP 同构），关闭时不产、输出与既有缺省逐字一致 |
| `loop.action` | turn_id, action | 回合推进（step_completed 映射，既有契约） |
| `loop.action_started` | round, tool_id, args | 工具动作开工（⏺ 动作行，TUI 折叠块呈现） |
| `loop.action_completed` | round, tool_id, ok, duration_ms, output | 工具动作收尾（标题落 ✓/✗+耗时，展开含输出节选） |
| `loop.delta` | text | **流式增量**（`reply_delta` 映射；**专类型**，change `0132`/ADR-0125）—— 消费方按类型分流后以**文本追加**呈现（TUI 落 live 尾部、Web 原地拼接），**不**逐帧新建行 |
| `loop.result` | turn_id, result | **终态**结果回传（`loop_finished` 映射，载荷 `LoopResult`；**不**承载增量） |
| `loop.error` | turn_id, error | 结构化错误（不中断循环） |
| `task.*` | 编排事件载荷 | 任务进度（task_started / plan_ready / wave_started / subtask_started / subtask_progress / subtask_completed / task_checkpoint / task_finished / task_failed，type 前缀 `task.`；TUI 时间线呈现：任务/波次浅灰单行，子任务 Collapsible 折叠块（标题含运行态徽标 `⟳`，收尾落 ✓/✗），展开含验收/**里程碑**（`subtask_progress` 逐条追加，工具类复用动作行**友好名**，见下注）/判定/结果节选；Web 任务区呈现见 §1.2 末） |

> **注（TUI 流式结构化块整体解析，change `0146` / ADR-0138）**：TUI 流式增量固化以**结构化块为
> 单位** —— 当尾段处于**未闭合的结构化块**内（Markdown 表格：表头行 / `|---|` 分隔行 / 数据行；或
> 代码围栏）时，**延后**按行边界或字符阈值的固化，使该块作为**整体**落入**同一**渲染块（表格渲染
> 为表格、围栏渲染为代码块），**不**依行边界拆成多个块；块**闭合**（出现空行或块外内容开始）后方
> 恢复常规固化。未闭合块的缓冲**有界**（超硬上限兜底，约束内存）。围栏判定优先于表格（围栏内 `|`
> 不作表格）。**注**：Web 端 `Chat.svelte` 以纯文本呈现（无 Markdown 渲染器），表格在 Web 恒显
> 竖线原文，属**另一端**（见 ADR-0138 已知局限②）。

> **注（TUI 流式回显合帧节流 + 表格整块延后渲染，change `0147` / ADR-0139）**：TUI 流式增量**不保证
> 每分片一次重绘** —— delta 先**入缓冲**，按固定节拍（`_TAIL_FLUSH_S = 0.04`，懒启动 timer）**合并
> 渲染一次**，使渲染次数与分片速率**解耦**（消除逐 delta 全量 re-parse/re-layout 的**阶梯抖动**）。
> 处于**未闭合**状态的 Markdown 表格块**延后渲染**（不绘制中间态），待块闭合或超硬上限后**一次整块
> 成型**（列宽只算一次）；**代码围栏分支维持流式可见**（不延后）。挂**非尾** widget（动作行 / 思考块 /
> 审批提示 / 打断提示）前 SHALL 先提交挂起尾段（时序不乱）。所有挂起缓冲**有界**，且回复收尾
> （含异常 / 中断）时挂起尾段**被最终固化**（不丢字）。**注**：本机制对 Web / APP 端**不适用**
> （`Chat.svelte` 纯文本，见 ADR-0139 已知局限③）。

> **注（`subtask_progress` 载荷，change `0121` 数据面 / change `0124` 消费面）**：载荷
> `{task_id, subtask_id, event, data, ts}` —— `event` 为内层事件类型，`data` 为**按类型白名单**取键的
> 子集（`action_started`：round/tool_id/args；`action_completed`：round/tool_id/ok/duration_ms/output；
> `step_completed`：round/failed），**表外类型不外发**。TUI 展开区**只**呈现 `tool_id` 的**友好名**与
> 耗时（轮次级落轮次与成败）——原始 `args` / `output` / 内部 `tool_id` **不进用户可见层**；无对应折叠块
> 的里程碑**静默忽略**。非交互 `core-agent task` 入口**不呈现**里程碑（既有单行粒度不变）。
> TUI 另可经 `/focus <子任务标识>` 进入**单子任务焦点视图**（复用同一折叠块已渲染文本，零新增数据源；
> change `0125` / ADR-0118，见 §1 末）。

### 1.2 HTTP 端点清单（WebBridge.serve）

`WebBridge.serve(host, port)` 将 `UIAPILayer` 12 方法暴露为 HTTP 端点（REST + SSE）：

| 端点 | 方法 | 映射 | 说明 |
|---|---|---|---|
| `POST /session` | create_session | `create_session(mode)` | 新建会话（登记至共享注册表，见 §1.3） |
| `GET /sessions` | list_sessions | `list_sessions()` | 枚举对话会话（`{session_id, mode, created_at}` + 注入转录时的派生 `title`/`updated_at`，见 §1.3.1） |
| `GET /session/{id}/messages` | session_messages | `session_messages(session_id)` | 读该会话**对话转录**（按追加次序）；未登记仍 `UI_SESSION_NOT_FOUND` |
| `POST /run` | run_loop | `run_loop(session_id, user_input)` | SSE 流式 loop 事件 |
| `POST /task` | run_task | `run_task(session_id, goal)` | SSE 流式**编排任务**进度（`task.*`；change `0122`。未登记仍 `UI_SESSION_NOT_FOUND`、编排器未注入 ⇒ `UI_ORCHESTRATOR_UNSET`，二者均以**错误帧**报告） |
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

**会话续聊（change 0116 / ADR-0109；渲染格式 change 0157 / ADR-0149）**：`CLIBridge(api=…, session_id=…)` 的会话标识透传至
`run_repl` → `build_app`；非空 ⇒ **复用**该会话（载入其转录铺进时间线；未登记 ⇒ `UiError`，
fail-closed，先于进入 TUI 拒绝），缺省 ⇒ 新建（既有行为不变）。铺入时 **agent 回复按 Markdown 渲染**
（与实时流式路径**同一** widget / 格式 ⇒ 代码围栏成代码块、表格成表格，**不退化为逐行明文**），
**用户消息**仍以 `❯` 回显行呈现；既有转录**内容**不被改写（仅对齐呈现格式）。CLI 侧读取面：
`core-agent session show <session_id>` 打印同一 `TranscriptStore` 的会话转录（未登记以非零退出码拒绝）。

**代码块视觉（change 0158 / ADR-0150）**：TUI **代码块（围栏）**背景由 `ReplApp.CSS` 的
`MarkdownFence` 规则指定 —— **不透明**且与 TUI 主背景的 **WCAG 相对亮度对比度 ≥ 2.0**（本主题解析为
中性灰 `#4F4F4F`，对 `#121212` ≈ 2.3）；Textual 默认的 `black 10%` 在深色底上合成近同色（≈ 1.02）
**不可辨识**，故被覆盖。语法高亮 token 色仍为亮色（`$text-*` 系）⇒ 取**深灰**而非浅灰（浅底会吃掉高亮）。
本项为**纯样式**，渲染路径（change 0157/ADR-0149 已统一为 Markdown）与主题均未改动。

**Web 会话列表面（change 0116 / ADR-0109）**：SPA 由 `GET /sessions` 呈现右栏会话列表
（派生标题 + 最近活跃，**呈现层**降序），点选经 `GET /session/{id}/messages` 渲染转录并继续对话；
会话标识与列表由 `App.svelte` 单点持有，「新建会话」为**显式**动作（无选中会话时发送被拒，
不隐式建会话 ⇒ 列表不留空会话）。

**Web 任务区（change 0122 / ADR-0115）**：SPA 右栏在**会话列表之上**新增**任务区**（`views/TaskPanel.svelte`），
经 `POST /task` 驱动编排器并消费 `task.*` 事件：逐子任务渲染**标题**（`subtask_started.goal`）与**状态**
（待执行 / 运行中 / 完成 / 失败），`<details>` 展开**详情**（里程碑行由 `subtask_progress` 的 `event`/`data`
转写、验收标准、完成 / 失败理由）—— 全部取自**既有事件载荷**，不建第二数据源。任务区与会话列表
**并列不混池**（在途运行态 vs 持久记录）；任务收尾（`task_finished` / `task_failed`）该任务**移出在途列表**
（回落）并以一次性提示呈现终态，**不**进入会话列表。「进入子 agent 会话 / 主-子焦点切换」不在其内
（子 Agent 消息流**无数据源**：转录只注入主 loop，见 change `0115`）。

**TUI 子 Agent 焦点视图（change 0125 / ADR-0118）**：REPL 支持**主视图 ⇄ 子任务焦点视图**切换 ——
`/focus <子任务标识>` 进入该子任务的焦点视图（`#panel`：标题沿用折叠块口径 `▸ 子任务 <sid>  ⟳|✓|✗ <goal>`，
正文取该折叠块详情的**已渲染文本**：验收 / 里程碑 / 判定 / 结果节选），`/main` 或 **`F2`**（绑定
`focus_main`）返回主视图。切换**只改 `display`**（`#panel` 与 `#timeline` 互斥，**绝不 unmount** 时间线）；
焦点**绑定 widget 身份**（`self._open` 跨任务不清空而 sid 逐任务复用）；成功切换**零时间线写入** ⇒
返回后主时间线内容**逐字不变**。焦点命令在 `on_input_submitted` 中**先于忙态拒绝**处理（任务运行中亦可用，
且**不进推理**）；未知标识不切换（提示「未找到」）。`task_started` 与**审批挂起**时强制回主视图
（计划头 / 审批提示写在时间线上，隐藏即不可见）。Web 侧**不做**焦点视图（面板式布局，沿用 `TaskPanel`）。

**TUI 神兽斜杠命令（change 0137 / ADR-0130）**：REPL 命令面补 `/summon <神兽> [任务]` 与
`/recall <神兽>`，经 `UIAPILayer.beast_command` 落到**与 CLI `summon`/`recall` 同一** `BeastActivator`
（三入口无第二真源）。解析走纯函数 `_parse_beast_command`（`/recall` **不带**任务位元）；缺目标时
只提示用法、**不**发起激活。呈现为一行状态（`已召唤/已召回神兽 <agent_id>（状态 <state>）`）+
**有结果才打印**的一行结果（与 `summon` CLI 同口径；结果正文只经只读查询面，不编造）。领域错误
（无匹配神兽 / 状态冲突）在 API 边界归一为 `UI_BEAST_*` 并落时间线 fail 行，**不**抛裸领域异常。

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
| `UI_BEAST_UNSET` | 神兽激活器未注入（`activate_beast` / `beast_command` 前校验，change `0137`） |
| `UI_BEAST_UNKNOWN_VERB` | `beast_command` 收到未支持的控制动词（change `0137`） |
| `UI_BEAST_NOT_FOUND` | 无匹配神兽（领域 `NO_AGENT_MATCH` 在 API 边界归一，change `0137`） |
| `UI_BEAST_STATE_INVALID` | 神兽状态不允许该操作（`BEAST_ALREADY_MANIFEST` 重复召唤 / `BEAST_NOT_MANIFEST` 无在岗可召回，change `0137`） |

---

## 6. 关联

- 模块：`06-ui-frontend/ui-architecture.md`
- 规格：`openspec/specs/ui/spec.md`
- LLM 归一化：经 `llm-provider` 虚拟接口调用（可替换默认实现）
- 决策：ADR-0013 ~ 0015、ADR-0031、ADR-0083（宠物控制面）
- 测试：`04-testing/test-cases.md`（TC-UI 系列）
