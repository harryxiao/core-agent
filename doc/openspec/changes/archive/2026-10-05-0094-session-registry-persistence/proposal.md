# 0094 — 会话注册表持久化与跨入口共享

## 为什么

真机活 LLM 冒烟暴露：**对话会话标识只存在于进程内存**。`UIAPILayer._sessions: dict[str, str]`
（`src/core/ui/api.py:66`）为进程内 dict，`create_session`（`api.py:76`）生成 `uuid4().hex` 写入其中，
`_require_session`（`api.py:187`）只认**本进程**建过的 id。后果（实测）：

- `core-agent session create` 建 id → **另起进程** `run --session <id>` ⇒ `UI_SESSION_NOT_FOUND`；
- CLI 建的会话在 WebUI（`serve`）**不可见**（`fastapi_serve.py` 9 端点无会话枚举）；
- `core-agent sessions` 列的是 `HarnessHost` 的**连接记录**（`sessions.jsonl` 的 `session-N`），与对话会话是
  **两套 id 空间**，同名异物、误导性强。

而**记忆本身是落盘的**（`memory.jsonl`，按 `session_id` 打标签；召回 `MemoryStore.read(query)` **查询驱动、
不按 session 过滤** —— 跨进程召回已实测成立）。⇒ 缺的只是「id → 有效」这层注册表的**持久化**。

此项正是 change `0048-session-scoped-memory` 的 **Non-goals 明文延后项**：「不做运行时段进程内状态持久化」
与「不给 CLI 入口引入会话生命周期」。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/ui/sessions.py` | **新增** `SessionRegistry`：`create/exists/list`；**读透 + 写时合并**；`path=None` ⇒ 纯内存 |
| `src/core/ui/api.py` | `__init__` 增 `registry` 注入（缺省内存注册表）；`create_session` / `_require_session` 改走注册表；新增 `list_sessions`；删 `self._sessions` |
| `src/core/ui/fastapi_serve.py` | 增 `GET /sessions` 端点（`list_sessions`）；端点计数 9 → 10 |
| `src/core/ui/__init__.py` | 导出 `SessionRegistry` |
| `src/core/entry.py` | `_build_ui` 注入 `SessionRegistry(path=_state_path("conversations.json"))`（四入口共享单点）；`session` 子命令改用共享注册表 + 新增 `list`；`sessions` help 文案消歧 |
| `doc/openspec/specs/ui/spec.md` | ADDED「会话注册表持久化与跨入口共享」+ 3 场景 |
| `doc/03-interfaces/ui-interface.md` | §1.2 端点表 9 → 10（`GET /sessions`） |
| `doc/01-architecture/adr.md` | ADR-0089 + 映射表行 |
| `doc/04-testing/test-cases.md` | TC-UI-10 |
| `tests/test_session_registry.py` | 新：注册表行为（持久化 / 内存 / 写时合并 / 读透 / 损坏降级） |
| `tests/test_entry.py` / `test_ui.py` / `test_serve.py` | 追加：CLI 跨进程可见 / 端到端 `session create` → `run --session` / 枚举端点 |

## 决策

- **落 `core/ui/sessions.py`，不入基座**：消费方只有 `UIAPILayer`（`core/ui/api.py`）与 `entry._session`；
  `ui` 是接入层顶点包（反向依赖黑名单仅 `{ci_cd, im, git}`），新增纯 stdlib + `core.persistence` 模块零架构风险。
- **读透 + 写时合并**（非「ctor 载入一次」）：`SkillLibrary` 的「载入一次、之后纯内存」房型会导致双失灵 ——
  长驻 `serve` 启动早于 CLI `session create` ⇒ 永远看不到新会话；两进程各持内存副本整体重写 ⇒
  last-writer-wins 覆盖。故 `exists/list` 每次读盘、`create` 走 read→merge→write。
- **文件名 `conversations.json`**：与 `sessions.jsonl`（HarnessHost 连接记录）**名字与语义均不同**，
  避免同名异物。
- **`path=None` ⇒ 纯内存**：与 `SkillLibrary` / `persistence` 房型一致；`UIAPILayer()` 无参构造仍得内存注册表
  ⇒ 既有 `UI_SESSION_NOT_FOUND` 断言与测试语义不变（**纯加法、后向兼容**）。
- **不引入文件锁**：会话创建是人工操作、频率极低；`write_state` 已是 tmp + `os.replace` 原子写。
  两进程在同一毫秒内 read→write 的极端竞态（丢一条）**接受**并记入 ADR「已知边界」，不引入 `fcntl`
  （WSL 上 flock 语义有坑，且属过度工程）。

## 明确不做（记录理由）

- **不做 `session remove` / 上限裁剪**：无消费者；删除还牵出「`memory.jsonl` 中该 session 的条目怎么办」
  （记忆是追加日志、召回不按 session 过滤）—— 属独立议题。代价：`conversations.json` 单调增长（每条约 60B，
  数千条仍 < 1MB），记入账本后续行。
- **不重命名 / 不改语义 `sessions` 命令**：它列 `HarnessHost` 连接记录（`session-{N}` / `client_id` / `state`），
  是**另一套 id 空间**；改名会破 CLI 契约基线与既有测试，属无收益重构。仅以 help 文案消歧。
- **不做跨进程文件锁 / 一致性保证**（注册表 ↔ `memory.jsonl`）：召回查询驱动、不按 session 过滤
  （跨进程已实测成立），无需一致性协议。
