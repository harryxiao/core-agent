# Phase 9 — 产品化入口层（entry / serve / repl / pet.md / user-guide）

> 里程碑：**M6 可启动产品**
> 位置：接入层（入口 + 三桥落地）+ 横切（配置收口 + pet 配置）
> 上游：Phase 7（三桥抽象 + 统一后端 API）+ Phase 8（pet 会话/激活器）+ 门禁基线（cli-contract-baseline.md）

---

## 1. 范围与定位

本 Phase 把 core-agent 从「库可导入但无法启动」补齐为「**可安装、可启动、可调试的完整产品**」，交付 5 个能力：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| entry | console_scripts + `__main__.py` + argparse 全命令面（`-h/--help` 三级帮助） | 接入层 |
| serve | WebBridge 真实 FastAPI/HTTP+SSE 服务（替换 `_default_serve` 占位抛错） | 接入层 |
| repl | CLIBridge 交互会话循环（`core-agent` 无子命令进 REPL） | 接入层 |
| pet.md | 多宠物 persona 文件加载 + `pet.*` 纳入 ConfigSpec | 横切 |
| user-guide | 用户指南（安装/主 Agent 配置/Pet 配置/help 清单/启动入口/LLM 配置） | 交付层 |

> **范围边界（三模之二）**：三模入口（CLI/Web/Desktop）中，本 Phase 只落地 **CLI（repl）+ Web（serve）**；**Desktop（`core-agent.app` Tauri 壳 + sidecar）本 Phase 不落地**（Tauri 壳超出 M6 范围），三模契约维持抽象层 `DesktopBridge.start_sidecar()` 占位，验收清单显式标 deferred，不默认勾选。

**里程碑口径（M6）**：完整产品形态可**启动** —— `pip install` 后 `core-agent` 命令可用，`-h/--help` 可见全量指令，serve/repl 双入口跑通，pet.md 多宠物可加载。

> **M6 与 M5 的关系**：M5「可发布产品」（Phase 7）交付了管道与抽象（ci-cd/ui/im/git + 配置收口），但可启动入口（`core-agent` 命令、serve/repl）未落地；本 Phase 的 M6「可启动产品」是 M5 的**入口侧补缺**，避免「启动」排在「发布」之后的语义倒挂。

---

## 2. 契约红线（实证现状 vs 契约）

> 现状缺口全部实测坐实：无 `[project.scripts]`、无 `__main__.py`、无 argparse `-h`；`WebBridge.serve()` 调 `_default_serve` 抛 `RuntimeError`；`CLIBridge.connect()` 仅 `return UIAPILayer` 无循环；`ConfigManager.load()` 强制读 config.yaml 抛错（正确入口 = `resolve()`）；pet.md 无加载、`pet.*` 不在 ConfigSpec；pyproject 仅 `litellm` 依赖。

**entry（cli-ops-interface + cli-contract-baseline 原文）**：
- 能力：argparse 解析 argv，命令分组路由到 dispatcher，`-h/--help` 输出全量指令
- 契约：命令面**权威 = baseline 30 动词 + 14 flag**（§2.1-2.10），不得另起命令解析；`CommandGroup` 六组（LIFECYCLE/STATUS/ASSET/CONNECTION/SECURITY/GATEWAY）路由；`ParamMapper` 三源映射
- 入口结构：`src/core/__main__.py` + `src/core/entry.py`（`main()` 供 console_scripts 引用）+ pyproject `[project.scripts] core-agent = "core.entry:main"`
- 三级帮助：`core-agent -h`（顶层 + 全局 flag）→ `core-agent <group> -h`（子命令列表）→ `core-agent <cmd> -h`（参数详情）

**serve（ui-interface §1 原文）**：
- 能力：统一后端 API（FastAPI，HTTP+SSE）、SSE 流式、断线重连
- 契约：三模复用同一内核与 LLM 配置，CLI 也不绕过；`WebBridge.serve()` 起真实 HTTP server（替换占位）
- 接口：`WebBridge.serve()`；方法（**9 个**，与 `UIAPILayer` 全量对齐）：`create_session()`/`run_loop()`（SSE）/`barge_in()`/`get_memory()`/`compact()`/`list_tools()`/`invoke_tool()`/`get_llm_config()`/`set_llm_config()`
- 依赖：pyproject 补 `fastapi` + `uvicorn`（**接入层边界依赖**，按 ADR-0040 MAL 四条：抽象接口 `UIAPILayer` 已存在、具体库隔离在单一适配器懒 import、DI seam = `WebBridge` 注入、spec 说抽象不说具体库）

**repl（ui-interface §1 + cli-ops 边界原文）**：
- 能力：`core-agent` 无子命令进入交互会话循环（多轮上下文保持、barge-in 打断）
- 契约：`CLIBridge` 只承载**交互会话面**（无子命令进 `run_loop()`）；运维命令面（status/doctor/logs/install/mcp/auth/gateway）复用 cli-ops，**不并入 REPL**
- 实现：`connect()` 从「仅返回 UIAPILayer」扩展为 **Textual** 交互循环（ADR-0013 已定 Textual，不引入 readline 二选一；Textual 同为接入层边界依赖，按 ADR-0040 MAL 隔离）

**pet.md（pet-mode-interface + configuration-interface 原文）**：
- 能力：多宠物，每宠物设定角色/性格/喜好；`pet.md` 作 persona 提示词；日常随机小任务（可配置关闭）
- 契约：`PetActivator` 三入口（`activate_from_slash`/`activate_from_cli`/`activate_from_nl`）统一走 `PetSession` 生命周期，**不新增第二真源**；`pet.*` 纳入 `ConfigSpec` 单一真源
- 配置：`pet.enabled`（feature flag）+ `pet.persons_dir`（多宠物目录，`<name>.md` 每只一个）+ persona 字段（角色/性格/喜好，pet.md 内解析）
- 加载：`resolve()`（configuration 模块级纯函数，非 `ConfigManager.load()`）经优先级链读取 `pet.*`，`PetSession` 构造时加载对应 pet.md

---

## 3. 验收口径（M6 里程碑）

- `pip install -e .` 后 `core-agent` 命令可用；`python -m core` 等价
- `core-agent -h` / `<group> -h` / `<cmd> -h` 三级帮助覆盖 **30 动词 + 14 flag** 全量，与 baseline 逐条对齐
- `core-agent serve` 起真实 HTTP server（FastAPI/uvicorn），SSE 流式 run_loop 跑通
- `core-agent` 无子命令进 REPL，多轮上下文保持 + barge-in 打断
- `core-agent pet ...` 命令可激活 pet（pet 动词已入 baseline 30 动词）；pet.md 多宠物加载，`pet.*` 经 `resolve()` 读取
- 用户指南文档落盘：安装 / 主 Agent 配置项 / Pet 配置项 / help 清单 / CLI+WebUI 启动入口 / LLM API-URL 配置，每条例证实测可跑

---

## 4. 首步任务

**首步补 2 个契约缺口 + 3 项对齐**（走 openspec_sop 补契约再编码）：

1. **补 `pet.*` ConfigSpec**——走 openspec_sop：在 `configuration-interface.md` 的 ConfigSpec 清单补 `pet.enabled` / `pet.persons_dir`（CLI flag `--pet-enabled` / `--pet-dir`，env `CORE_PET_ENABLED` / `CORE_PET_DIR`，map_to `pet.*`）；在 `pet-mode-interface.md` 补 persona 字段契约（角色/性格/喜好 + 随机任务开关）。禁止 pet 配置绕过 ConfigSpec 另起解析。
2. **补 serve/REPL 落地契约**——ui-interface §1 已有「FastAPI HTTP+SSE」「CLIBridge 交互会话面」契约，但实现当时 deferred（✅ **已落地**：`src/core/ui/fastapi_serve.py` + `src/core/ui/repl.py`，见 `phase-19.md` G 类）；补 `WebBridge.serve()` 端点清单（`POST /session`、`POST /run` SSE、`POST /barge-in`、`GET /memory`、`POST /session/compact`、`GET /tools`、`POST /tools/invoke`、`GET/PUT /llm-config`——覆盖 `UIAPILayer` 全部 9 方法）+ `CLIBridge.connect()` 循环语义，validate 通过后编码。
3. **对齐 help 清单**：argparse 的 30 动词 + 14 flag 必须与 `cli-contract-baseline.md` §2.1-2.10 逐条一致（复用 `cli-ops` 的 `CommandGroup`/`ParamMapper`，不得另起命令解析——与 ci-cd「不得另起一套」同一原则）。
4. **核对入口 ↔ cli-ops 边界**：argparse 只做「解析 + 路由」，具体动作进 `dispatcher.py` 六组方法；argparse 层不得内联实现命令逻辑。
5. **对齐 pet 激活入口**：`core-agent pet ...` 命令族必须落到 `PetActivator.activate_from_cli()`（不是自己 new PetSession），与 `/pet` 斜杠、WebUI 自然语言三入口同源。

**启动前核对**（按顺序执行）：
1. 读 `cli-contract-baseline.md` §2.1-2.10 原文（30 动词 + 14 flag 全量）。
2. 补 pet.* ConfigSpec + serve/REPL 落地契约，openspec validate 通过后再编码。
3. 读 `configuration-interface.md` §2 确认 `pet.*` 经 `resolve()`（模块级纯函数）链读取，而非 `ConfigManager.load()`。

---

## 5. 依赖与顺序

- entry 依赖：Phase 7（dispatcher/ParamMapper 已就位）+ Phase 2（config 模块）
- serve 依赖：Phase 7（UIAPILayer 9 方法）+ pyproject 补 fastapi/uvicorn（按 ADR-0040 MAL 隔离）
- repl 依赖：Phase 7（CLIBridge 抽象）+ Phase 3（loop）
- pet.md 依赖：Phase 8（PetSession/PetActivator）+ Phase 2（configuration.resolve()）
- user-guide 依赖：以上四项全部落地后，据实测输出

**建议顺序**：补 pet.* 契约 + serve/REPL 契约 → pyproject 依赖（fastapi/uvicorn/textual，接入层边界依赖按 ADR-0040 MAL）→ entry（__main__/argparse）→ serve → repl → pet.md → user-guide → 门禁全绿单次提交

---

## 6. 里程碑验收清单

- [x] 契约补齐：pet.* ConfigSpec + serve 端点清单 + REPL 循环语义，openspec validate 通过
- [x] pyproject：`[project.scripts] core-agent` + fastapi/uvicorn/textual 依赖（接入层边界依赖，按 ADR-0040 MAL 四条落契约）
- [x] entry：`core-agent` / `python -m core` 可用，三级帮助覆盖 30 动词 + 14 flag
- [x] serve：`core-agent serve` 起真实 FastAPI，SSE 流式 run_loop 跑通
- [x] repl：`core-agent` 无子命令进交互循环，多轮上下文 + barge-in
- [x] pet.md：多宠物加载 + `pet.*` 经 resolve() 读取 + `core-agent pet ...` 激活（pet-notify 真实通道 im 本 Phase 不接，维持注入回调 deferred）
- [x] user-guide：安装/配置/help/启动/LLM 六节落盘，每条例证实测
- [x] M6 冒烟：entry + serve + repl + pet.md 四入口全链路跑通，门禁四件套全绿

---

## 7. 测试要点

- [x] entry：`-h` 三级帮助与 baseline 30 动词 + 14 flag 逐条 diff 一致；未知命令错误码；`--version` 输出
- [x] serve：HTTP 端点 CRUD + SSE 流式事件 + 三模复用同一内核（**「断线重连」已移出本行**，见下条）
- [ ] serve：**断线重连** —— **未实现**（账目校准 change `0141` / 账本 **E86** 假绿订正：前端 `frontend/src/lib/api.js:55-63` 用 `fetch` + `ReadableStream` 读 **POST** SSE，**非** `EventSource` ⇒ **无**浏览器原生自动重连；`frontend/src/` 与 `src/core/ui/` grep `reconnect|retry|Last-Event-ID` **零命中**；TUI 为进程内直调、无此面）
- [x] repl：多轮上下文保持 + barge-in 打断 + 空输入/EOF 退出 + 运维命令面不并入 REPL
- [x] pet.md：多宠物隔离加载 + persona 解析（角色/性格/喜好）+ 随机任务开关 + 三入口同源 + pet.* 经 resolve() 链
- [x] user-guide：文档中每条命令/配置项与实测输出一致（交叉验证，禁止凭记忆写）

---

## 8. 提交规范

- **一个 Phase 一个 commit**：entry + serve + repl + pet.md + user-guide 五模块 + 契约变更 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase9): 产品化入口层 entry/serve/repl/pet.md/user-guide（M6）`
- 提交后更新 `README.md` §2 总览表 Phase 9 行状态列为「完成」。
- 契约变更走 openspec 归档（changes/），与代码同 commit 或紧邻提交。
