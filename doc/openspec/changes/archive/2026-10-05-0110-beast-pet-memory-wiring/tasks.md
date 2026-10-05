# tasks — beast / pet「专属记忆命名空间」接线收尾（change 0110 / E37 + E38 + E39）

## 1. 规格（先行）
- [x] 1.1 **规格中性**：`beast-mode`（`:54/:58-61` 独立命名空间、`:89/:99` 封存自动回归）/
      `pet-mode`（`:75/:77-85` 偏好追踪、`:231-234` 生产激活偏好落 L2）均已要求本 change 的内容
      ⇒ 无 spec delta，`.openspec.yaml` 置 `schema: spec-driven` + `skip_specs: true`
- [x] 1.2 复核：不新增 / 不修改任何 Requirement；两条**判据订正**（E38 封存=效果非 API /
      E39 观察点=主人原话入口非 `wake()`）见 proposal 与 ADR-0103

## 2. 测试（先写，红）
- [x] 2.1 `DefaultLoop(source="beast.x")` 落记忆 ⇒ `entry.source == "beast.x"`；**缺省** ⇒ `"loop"`（红线）
- [x] 2.2 `MemoryStore.read(..., exclude_source_prefixes=("beast.",))` 排除神兽条目且**缺省调用**
      仍返回（缺省检索语义不变）；排除项**不吃预算**、`reuse_count` 不增
- [x] 2.3 `MultiAgentRouter.handoff` 转交 `TaskHandoff.session_id` ⇒ 子 loop 落条目带该 session_id
      （证明 ③ 已接，非仅加字段）；`TaskHandoff` 缺省 `session_id == ""`（向后兼容）
- [x] 2.4 `DynamicAssembler(exclude_source_prefixes=("beast.",))` 的事实不含 `beast.*`；缺省含
- [x] 2.5 端到端（`build_runtime` + 离线 LLM 替身）：生产召唤 ⇒ 共享记忆出现
      `source == "beast.<agent_id>"` **且** `session_id == "beast.<agent_id>"` 的条目（**由 loop 写入**）
- [x] 2.6 端到端：主 loop 的装配器（`runtime.loop` 的 planner）事实里**无** `beast.*`（E37 ①/③ + E38 封存证据）
- [x] 2.7 `PetSession.observe_owner`：无记忆后端 ⇒ 静默 `None`（fail-soft）；空文本 ⇒ 不写；
      `"editor: vim"` ⇒ `_preferences` 非空 + L2 `source="user"` 条目
- [x] 2.8 端到端：`pet_activator.activate_from_cli("gather", ["editor: vim"])` ⇒ 共享记忆有
      `source="user"` 偏好条目、`session.prefer("editor") == "vim"`、`surprise()` 非 `None`（走真实 loop）
- [x] 2.9 端到端：`PetControl.assign("theme: dark")` ⇒ 同上落 L2
- [x] 2.10 **反例（不谎报）**：`/pet` 斜杠激活（合成 goal）与空 `rest` ⇒ **零**偏好写入
- [x] 2.11 运行确认**红**（新增用例失败、其余全绿）

## 3. 实现
- [x] 3.1 `loop/default.py`：`__init__` 加 `source: str = "loop"`；`remember` 用 `self._source`
- [x] 3.2 `memory/protocol.py` + `memory/store.py`：`read` 加 `*, exclude_source_prefixes=()`，
      在排名/预算**之前**过滤候选
- [x] 3.3 `context/assembler.py`：加同形参数并透传给 `read`
- [x] 3.4 `orchestration/models.py`：`TaskHandoff.session_id: str = ""`；
      `orchestration/router.py`：`handoff` 转交 `session_id=handoff.session_id`
- [x] 3.5 `beast/manager.py`：`summon` 传 `TaskHandoff(..., session_id=beast.agent_id)`
- [x] 3.6 `runtime.py`：`_beast_loop` 注入 `source=beast.agent_id`；`DynamicAssembler(...)`
      传 `exclude_source_prefixes=("beast.",)`
- [x] 3.7 `pet/core/session.py`：`observe_owner`（fail-soft 包装，`observe` 语义/异常面不动）；
      `pet/core/activator.py`（CLI / NL 入口）+ `pet/core/control.py`（`assign`）接线
- [x] 3.8 四门全绿（直连二进制，不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/`：`loop-interface.md`（`DefaultLoop(source=…)`）、`memory-interface.md`
      （`read` 排除参数）、`context-interface.md`（装配器参数）、`orchestration-interface.md`
      （`TaskHandoff.session_id`）、`beast-mode-interface.md`（§4/§10 命名空间口径）、
      `pet-mode-interface.md`（§1 `observe_owner` + 入口观察口径）
- [x] 4.2 `doc/01-architecture/adr.md`：**ADR-0103**（命名空间 = `source` 注入 + read 侧排除；
      E38/E39 两条判据订正；已知局限两条）+ 末尾映射表行
- [x] 4.3 `doc/04-testing/test-cases.md`：新增 §28（TC-NS-01…）用例登记

## 5. 收口
- [x] 5.1 手工归档（无 delta ⇒ 直接 `shutil.move` 进
      `doc/openspec/changes/archive/2026-10-05-0110-beast-pet-memory-wiring/`；tick tasks）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填（`phase-26.md` §0 现状列 + §3 验收勾选 + §6 收口；`README.md` §2 第 26 行）
- [x] 5.4 记忆更新 + 提交（`feat(...)`，一个 Phase 一个 commit）
