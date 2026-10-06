# Tasks · 0139 Harness Host 心跳 + Desktop 交付面（skip_specs）

## 1. 规格（先行）

- [x] 1.1 **无 delta**（`deployment/spec.md:59-70` 与 `ui/spec.md`「桌面打包」早已是硬 SHALL，实现侧纯背离
      ⇒ conformance）：写 `.openspec.yaml`（`schema: spec-driven` + `skip_specs: true`）
- [x] 1.2 `openspec validate 0139-desktop-bundle-and-heartbeat` 通过

## 2. 测试（先行 · 红）

- [x] 2.1 `tests/test_deployment.py`：心跳续命 —— `accept` → 时钟推进 → `touch` ⇒ 不回收；
      再推进（超过阈值且期间无 touch）⇒ 回收
- [x] 2.2 `tests/test_deployment.py`：未知会话 / 已断线 / 已回收 ⇒ `touch` 返 `False` 且**不复活**
- [x] 2.3 `tests/test_deployment.py`：`touch` 持久化 —— 落盘后新实例按新时钟 `reap` **不**回收
- [x] 2.4 **验绿**：实现后全绿（红因 `touch` 不存在而红）

## 3. 实现

- [x] 3.1 `src/core/deployment/host.py`：`touch(session_id) -> bool`（只对 `CONNECTED` 生效、
      拒刷不复活、成功即 `_persist`）
- [x] 3.2 `src-tauri/tauri.conf.json`：`app.windows` 清空（去硬编码 `url`）；
      `bundle.active: true` + `targets: "all"`
- [x] 3.3 `src-tauri/src/main.rs`：`resolve_port()` 单点取端口 + sidecar 就绪后
      `WebviewWindowBuilder` 程序化开窗（端口与 sidecar 同源）

## 4. 文档

- [x] 4.1 `doc/03-interfaces/deployment-interface.md`：§6 补 `touch` + 心跳/超时语义 + 驱动面已知局限
- [x] 4.2 `doc/01-architecture/adr.md`：ADR-0132 + `## 变更追踪` 行
- [x] 4.3 `doc/04-testing/test-cases.md`：§55（TC-DEPLOY，change 0139 / ADR-0132，账本 E81 + E83）

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— **1665 passed**（基线 1662 + 3）
- [x] 5.5 `openspec validate --all` —— **31 passed / 0 failed**（归档后回落 30 / 0）
- [x] 5.6 **额外（非门禁）**：`cargo check`（`src-tauri/`）—— **本轮未跑通**（缓存依赖树与
      `Cargo.lock` 版本不一致 + 联网取包未成功）；如实登记为**未验证**，壳编译归手工验收（Rust 面**无**四门禁）

## 6. 收口

- [x] 6.1 手工归档至 `archive/2026-10-07-0139-desktop-bundle-and-heartbeat/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（E81 / E83 行 + §9 表）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`fix(deployment): Host 心跳 + Desktop 交付面（change 0139）`）
