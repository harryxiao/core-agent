# 0083 — 宿主驱动的唤醒节拍（`pet run`，账本 E28）

## 为什么（账本 E28）

`0065`（账本 E17）裁决：**「周期触发」由宿主驱动，内核不常驻、不自建调度线程**。
但一手核实：三入口**无一调用 `wake()`** —— `pet gather` 只激活并打印、`ui serve` 不调、`/pet` 同。
⇒ pet 自治循环与反馈通知（`0079` 三环）**在生产仅在「有人手动驱动」时才可达**，而
**没有任何宿主在驱动**。E28 的前置「常驻宿主」今日不存在。

## 用户裁决

**新 CLI `core-agent pet run [--interval S]`**（禁 `ui serve` 内隐式后台线程）：

- 驱动者 = **用户显式启动的宿主进程** —— 与 E17「内核不自建 daemon」相容：这不是内核
  偷偷起线程，而是宿主**显式常驻**；
- **不做隐式副作用**：WebUI 一开就让宠物在后台真调 LLM / 真跑工具，是「用户没要求的动作
  却发生了」—— 与本仓「一切副作用可逆、可解释」的取向相悖；
- **无 UI 的部署也能驱动**（纯 CLI / 服务器场景）；
- 复用既有**跨进程注册表**（`pets.json`，change `0053`）——`pet run` 恰好兑现「注册表跨进程
  恢复」的设计意图：新进程读回 `ACTIVE` 会话（含任务队列 / 唤醒计数）继续驱动。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/pet/core/driver.py`（新） | `PetWakeDriver`：`tick()` 逐会话唤醒 + **故障隔离**（`PetError` 预期态跳过、意外异常记为 `FAILED` 不中断其余宠物 —— 规格 R8）；`run(interval, on_tick=…)` 常驻节拍（`sleep` 可注入 ⇒ 可测） |
| `src/core/pet/core/__init__.py` | 导出 `PetWakeDriver` / `WakeOutcome` |
| `src/core/entry.py` | `pet run` 分支（在激活分支之前）+ `--interval` 从 `rest` 提取（`argparse` 的 `REMAINDER` 使然，同 `--name` 先例）+ usage 串补 `run` |
| `tests/test_pet_driver.py`（新） | 驱动薄壳：逐会话唤醒 / 预期态跳过不影响其余 / 意外失败隔离 / 节拍（注入 `sleep` 中断） |
| `tests/test_entry.py` | `pet run` 组合面：从跨进程注册表恢复会话 → 交给驱动（断言 interval 与「已驱动 N 只宠物」） |

**规格中性**（`.openspec.yaml`：`schema: spec-driven` + `skip_specs: true`）：pet-mode 规格无
「宿主必须是哪个入口」的条款（`0065` 已核实），本变更实现的是**既有条款的宿主侧落地**。

## 明确不做

- **不做 `ui serve` 后台线程**（用户裁决）：隐式副作用 + 线程生命周期 + 需要新配置键，且无 UI 的
  部署仍不可驱动。
- **不新增配置键 `pet.wake_interval_s`**：`--interval` 是**宿主命令的运行参数**（同 `ui serve --host/--port`
  的层级），不是配置面事实；进 `ConfigSpec` 会再现「构造面可注入而生产调用点不传参」的旧患
  （E15/B5 教训的反面：这里 CLI 就是唯一生产调用点）。
- **不自动激活**：无已注册会话时打印提示并退出 0 —— 激活仍是三入口的职责（避免第二真源）。
- **不做 `--oneshot` / `--iterations`**：测试用注入 `sleep` 的确定性节拍覆盖，不为测试加生产表面。
- **不改 `wake()` 语义**：让行/退避/未激活仍抛 `PetError`，由驱动侧隔离。
