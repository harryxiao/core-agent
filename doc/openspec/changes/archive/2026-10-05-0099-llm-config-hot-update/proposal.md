# 提案 — LLM 配置热生效与落盘持久化（change 0099）

## Why

规格「LLM API 可配置」的三条场景（`doc/openspec/specs/ui/spec.md:42-58`）要求 UI 保存 LLM 配置后
**「配置写入后端配置源并立即生效」**、**「key 存储在本地受保护配置文件中」**、写失败时
**「回滚本次配置变更并提示用户，不留下半写状态」**。而实现（`src/core/ui/api.py:181`
`UIAPILayer.set_llm_config`）**只改内存 `self._llm_config`**：

- **不落盘** —— `set_llm_config` 无任何 `ConfigManager` 调用 ⇒ 进程重启即丢（归档 change `0003`
  tasks 1.3 明文 deferred，至今未做）。
- **不触达运行中的 loop** —— change `0098` 把 `token_budget` / `max_rounds` 接进配置链并注入
  `DefaultLoop(...)`，但注入发生在**装配期**；UI 改配置后，**运行中的 loop 预算不变**（改了个寂寞）。
- **API 面字段不全** —— `PUT /llm-config`（`fastapi_serve.py:122`）body 只认
  provider/model/endpoint/api_key_ref，0098 新增的 `context_window` 与预算旋钮**无入口**。

即「规格要求 X 而实现没有」（与 change `0094`/`0095` 同型）。本项补齐：落盘 + 热生效 + 字段扩展。

## What Changes

- **`DefaultLoop.set_limits(*, max_rounds=None, token_budget=None)`** —— 运行期改上限。两属性本就在
  `_should_compact` / 硬停判定处**每轮读取**（`loop/default.py:199/243/305`）⇒ 赋值即下次生效，
  无需重建 loop。
- **`core.loop.LimitsConfigurable`** —— `@runtime_checkable` Protocol（仅声明 `set_limits`），
  供 `UIAPILayer` 按**协议**调用（`ui` 已 import `core.loop`，不新增依赖方向；避免 `isinstance(DefaultLoop)`
  把 UI 层焊死在具体实现上）。
- **`UIAPILayer.apply_llm_config(cfg, *, output_reserve=None, max_rounds=None)`** —— 新入口：
  校验密钥引用 → 组 **一个** patch（`llm.*` + `loop.*`）→ `apply_change` → `write_patch` → `load`
  （复用 `entry._config_set` 的范式）→ 把 `config.loop_limits()` 派生值经 `LimitsConfigurable` 推给运行中 loop。
  **一次 patch、一次落盘** ⇒ 规格「不留半写状态」由构造满足。
- **`set_llm_config` 语义不变**（纯内存 hydrate）—— 它被 `entry._build_ui`（`:371`）在**每次启动**调用，
  若改为落盘则**每次 CLI 启动都重写 config.yaml**（真回归）。两个意图分成两个入口。
- **`PUT /llm-config`** body 扩 `context_window` / `output_reserve` / `max_rounds`；**`GET`** 回显
  `context_window` 与**生效值** `token_budget` / `max_rounds`（旋钮是输入、预算是可观测结果）。
- **`UiErrorCode.UI_LLM_CONFIG_INVALID`** —— `ConfigurationError` 归一为结构化码（不向调用方抛裸异常）。
- **`ConfigManager.write_patch` 改原子提交**（tmp + `os.replace`）—— 原 `write_text` 是**先截断再整写**，
  写盘中途失败会留下**空/半写** `config.yaml`（同 change `0062` 的 `CheckpointStore` 病灶、
  `0074` 的端点注册表先例）⇒ 规格「不留半写状态」无法由「失败后 `load()` 回滚」兜住（半写文件读不回来）。

## Non-goals

- **前端设置页**（Svelte SPA + Tauri 壳）归 change `0100`；本项只做后端 API 与规格。
- **`ConfigManager` 不做并发写锁**（同 change `0094` 口径：人工低频操作）。
- **不新建 `loop.token_budget` 显式键**（0098 决策）：预算仍由窗口派生，UI 只暴露旋钮。
- **密钥明文不入库/不进日志**不变（`${VAR}` 引用原样落盘）。

## 风险

- **写盘失败的回滚**：`write_patch` 失败时 `apply_change` 已在内存生效 ⇒ 须保证「写失败 ⇒ 回滚内存」。
  `ConfigManager.apply_change` 已把前值经 `EffectTracker.record(undo=...)` 登记（`manager.py:460+`），
  故 catch 后 `self._config.load()` 从盘重读即可回到落盘态。测试须覆盖「写失败 ⇒ 内存与 yaml 均不变」。
- **`output_reserve` / `max_rounds` 的非法值**：由 0098 的校验器在 `apply_change` 内阻断 ⇒ UI 面自动获得
  「非法值拒绝且原值不被破坏」（无需在 UI 层重复校验）。
- **无 `ConfigManager` 的 `UIAPILayer()`**（裸构造，测试/独立用）：无配置源可写 ⇒ 保持纯内存 +
  尽力热生效 loop（不假装持久化成功）。
