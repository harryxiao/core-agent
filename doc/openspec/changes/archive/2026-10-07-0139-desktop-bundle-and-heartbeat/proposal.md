# 0139 · Harness Host 心跳 + Desktop 交付面（skip_specs）

> 账本：`coding-plan/phase-34.md` **E81**（`reap` 无心跳刷新 `last_seen`）＋ **E83**（Desktop 端口硬编码 + 无安装包）
> 规格面：**无 delta**（`deployment/spec.md:59-70`「客户端断线与会话清理」与 `ui/spec.md`「桌面打包」
> `:210-218` 早已是硬 SHALL）｜ ADR：**0132**

## Why

两条均为「规格已 SHALL、实现只落一半」（E81 / E83）：

1. **E81**：`deployment/spec.md`「客户端断线与会话清理」SHALL「检测客户端断开（**含心跳**/超时判定）」，
   Scenario「连接超时回收」的前提是「客户端**长时间无活动**」—— 而 `deployment/host.py` 的
   `last_seen` **仅 `accept` 赋值**（`:56`），全类**无 touch / heartbeat**：`reap`（`:78-88`）据
   `last_seen` 判超时 ⇒ 一个**始终活跃**的长连客户端同样会被判超时回收。心跳面**缺失**，
   「按活动计时」无从表达。
2. **E83**：`ui/spec.md`「桌面打包」SHALL「打包为可执行安装文件（Windows / macOS / Linux）」，
   而 `src-tauri/tauri.conf.json` ① `app.windows[0].url` **硬编码** `http://127.0.0.1:8000`
   —— 与 `main.rs` 尊重 `CORE_PORT` 的 sidecar 启动端口**可能漂移**（内核换端口 ⇒ 壳指向空地址白屏）；
   ② `bundle.active=false` ⇒ **产不出安装包**（`phase-20` C8 只记「壳二进制打包未验证」，未记端口硬编码）。

## What Changes

1. `src/core/deployment/host.py`：新增 `touch(session_id) -> bool`（心跳刷新 `last_seen`）——
   **只对在连（`CONNECTED`）会话生效**；未知 / 已断线 / 已回收 ⇒ `False`（**不复活**已判定失效的会话）；
   刷新成功即持久化（与 `accept` / `disconnect` / `reap` 同口径，重启后不误回收活跃会话）。
2. `src-tauri/tauri.conf.json`：`app.windows` 清空（**去掉硬编码 `url`**）；`bundle` 开 `active: true`
   ＋ `targets: "all"`（三平台安装包）。
3. `src-tauri/src/main.rs`：**程序化开窗** —— 端口经 `resolve_port()` 单点取自 `CORE_PORT`（缺省 8000），
   sidecar 就绪后 `WebviewWindowBuilder` 以 `http://127.0.0.1:{port}` 建窗 ⇒ 壳与 sidecar **同源端口**，
   硬编码漂移在结构上不可能。

## Impact

- 代码：`src/core/deployment/host.py`（+1 方法）；`src-tauri/{tauri.conf.json, src/main.rs}`。
- 测试：`tests/test_deployment.py`（+3：心跳续命免回收 / 未知与失效会话拒刷不复活 / 心跳持久化）
  ⇒ `.venv/bin/pytest -q` **1665 passed**（基线 1662 + 3）。
- 文档：`doc/03-interfaces/deployment-interface.md`（§6 补 `touch`）、`doc/04-testing/test-cases.md`（§55）、
  ADR-0132。
- 兼容：新增方法为**可选面**，既有调用方零改动；`reap` 语义不变（未 touch 者照旧超时回收）。
- **Rust 侧无门禁**：`cargo check`（本地 `/home/harry/.cargo/bin/cargo`）为拟用的额外验证手段，
  但**本轮未跑通**（缓存依赖树与 `Cargo.lock` 版本不一致 + 联网取包未成功）⇒ 壳编译**未经编译验证**；
  安装包产出仍属手工验收（记 `test-cases.md`）。

## 已知局限

- **驱动面**：`HarnessHost.reap` / `touch` 今日**无生产驱动**（`entry._serve` 注册一个 `serve` 会话后
  直接阻塞于 uvicorn，从不 reap）。本 change 与 change `0138` 同类 —— 补的是**规格 SHALL 的原语/
  机制面**（heartbeat 检测能力），**驱动接线**不在 E81 闭账范围（登记为残留口径，不静默当作已完成）。
- **桌面安装包**为**手工验收**项：本仓四门禁无 Rust/打包面（即便 `cargo check` 跑通也只证编译、不证产出安装包；本轮更未跑通）；
  `bundle.targets: "all"` 的实际产物随平台工具链而定（缺平台依赖时该平台 target 跳过，属 Tauri 行为）。
