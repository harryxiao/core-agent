# design — 0094 会话注册表持久化

## 决策

### ① 落 `core/ui/sessions.py`，房间型对齐 `SkillLibrary`

消费方只有 `UIAPILayer`（`core/ui/api.py`）与 `entry._session`（`entry.py:877`）。`ui` 是接入层顶点包，
`tests/test_architecture.py:354-357` 只禁 `ui → {ci_cd, im, git}`；`core.persistence` 是**顶层模块**
（非 `CAPABILITY_MODULES`），且 `skills/library.py:17` 已有 `skills → core.persistence` 先例
⇒ 新模块仅 import stdlib + `core.persistence` **完全安全**。

（备选 `core/durability/`：语义更贴，但会新增 `ui → durability` 依赖边且无收益，不采用。）

### ② 读透 + 写时合并（**本变更的核心**）

照抄 `SkillLibrary` 的「ctor `read_state` 载入一次、之后纯内存」会**双失灵**：

| 失灵 | 机制 | 后果 |
|---|---|---|
| 长驻进程看不到晚建会话 | `serve` ctor 早于 CLI `session create` | 长驻 WebUI 的 `_require_session` 永远拒绝新 id；枚举端点恒空 |
| 并发创建相互覆盖 | 两进程各持内存副本、各自整体重写文件 | last-writer-wins，后写者抹掉先写者条目 |

故：

- `exists(sid)` / `list()` **每次 `read_state(path)`**（读透）；
- `create(mode)` 走 **read → merge → write**（写时合并）。

文件仅几十字节，成本可忽略；`write_state` 本身是 `tmp + os.replace` 原子写，不会读到半截文件。

### ③ 磁盘结构 + 损坏降级

```json
{"version": 1, "sessions": {"<sid>": {"mode": "cli", "created_at": 1759600000.0}}}
```

外层包 `version` 是为将来容忍额外字段而不破旧文件。`read_state` 对非法 JSON / 缺失文件返回 `None`，
ctor 据此落**空态**、`create` 据此从空起 —— 与 `SkillLibrary` 同口径：**派生状态损坏不阻断启动**。

### ④ `path=None` ⇒ 纯内存（后向兼容的关键）

`read_state(None)` → `None`，`write_state(None, ...)` no-op ⇒ 不落盘、`exists` 只查内存字典。
`UIAPILayer()` 无参构造仍得内存注册表 ⇒ 既有语义**逐条不变**：

- `tests/test_ui.py:83-87` / `:445-451`（未知会话 → `UI_SESSION_NOT_FOUND`）仍成立；
- `tests/test_serve.py:48-52`（`GET /memory?session_id=nope` → 404）仍成立；
- 全部 `api.create_session("cli")` + `run_loop` 的用例走内存注册表，行为等价。

**只有显式传 `registry=SessionRegistry(path=...)` 才落盘**（`conftest.py` 的 `_isolate_state_dir` 已隔离
`CORE_STATE_DIR`，测试互不污染）。

### ⑤ 单点注入：`_build_ui` 是全四入口的共享装配点

`_repl`（`entry.py:372`）/ `_serve`（`:381`）/ `_app`（`:397`）/ `_run`（`:1048`，内部 `api = _build_ui(args)`）
**全部**经 `_build_ui`（`:339-369`）。在该处构造 `UIAPILayer(...)` 时加一行
`registry=SessionRegistry(path=_state_path("conversations.json"))` ⇒ CLI 建的会话、serve 进程、REPL、`--app`
看到的是**同一文件**。（`WebBridge`/`CLIBridge`/`DesktopBridge` 只持有 `api`。）

### ⑥ CLI：`session` 子命令接共享注册表，`sessions` 命令不动

- `_session`（`entry.py:877-884`）现建**裸** `UIAPILayer()` 并打印 id —— 该 id 别处不可用。改为经
  共享注册表 `SessionRegistry(path=_state_path("conversations.json")).create(args.profile or "cli")`
  ⇒ 跨进程立即可见；并新增 `list` 分支。
- `_add_session_parser`（`entry.py:211`）加 `list` 子命令。
- **`sessions`（`entry.py:679-687`）保持不动**：列 `HarnessHost` 连接记录，是另一套 id 空间。仅把
  `entry.py:124` 的 help 文案改为「枚举 Harness Host 连接记录（≠ 对话会话；对话会话见 `session list`）」
  以消歧。`tests/test_entry.py` 的 `_TOP_LEVEL_COMMANDS` 只校验命令**存在性**，改 help 不破。

### ⑦ `SessionRegistry` 无 `remove()`

无消费者（无 `session remove` 命令），且删除牵出「`memory.jsonl` 中该 session 条目怎么办」
（记忆是追加日志、召回不按 session 过滤）—— 独立议题。见 `proposal.md`「明确不做」。

## 影响面

- `UIAPILayer.__init__` 增 1 个 keyword-only 参数（纯加法，既有调用点零改动）。
- `api.py` 删 `self._sessions`；`create_session` / `_require_session` 内部实现替换（**外部契约不变**：
  仍返回 32 位 hex、仍抛 `UI_SESSION_NOT_FOUND`）。
- `fastapi_serve.py` 新增 1 个 `GET /sessions` 端点；`POST /session`（单数）与 `GET /sessions`（复数）不冲突。
- 既有测试：`test_ui.py` / `test_serve.py` / `test_entry.py` 缺省装配（无 `registry=`）行为不变 ⇒ **零破坏**。
- `tests/test_architecture.py`：`ui` 新增对 `core.persistence` 的依赖不在任何禁名单内。
