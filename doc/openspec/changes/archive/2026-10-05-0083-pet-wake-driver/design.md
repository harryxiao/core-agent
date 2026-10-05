# design — 宿主驱动的唤醒节拍（change 0083 / 账本 E28）

## 决策 1：驱动落点 = 新 CLI `pet run`（用户裁决）

| 选项 | 评价 |
|---|---|
| ① **新 CLI `pet run [--interval S]`** ✅ | 驱动者 = **用户显式启动的宿主进程**（与 E17「内核不自建 daemon」相容）；无隐式副作用（宠物唤醒会真调 LLM/工具，不能靠开 WebUI 顺带发生）；纯 CLI 部署亦可驱动；无 UI 层改动（红线最少）；端到端可测 |
| ② `ui serve` 内置后台线程 | 隐式副作用 + 线程生命周期（`threading.Event` 关停）+ 需新增配置键（间隔）+ 测试需过线程/计时；且无 UI 的部署仍不可驱动。文档 `0065` 曾指向它，但那句是「当时能承载的只有它」，非规格条款 |
| ③ 保持开放 | 三入口无一驱动 `wake()` ⇒ pet 自治循环在生产**不可达**（E16 三环白接）——本账本正在清的正是这类「接线已备、驱动缺席」 |

**与 E17 的一致性**：`0065` 的裁决是「**内核**不自建 daemon」，而 `pet run` 是**宿主显式常驻** ——
正是「谁按周期调用它由宿主决定」的落地。故接口 §5 那句「能承载常驻驱动的只有 `ui serve`」
需订正为「`ui serve` 或 `pet run`」（同样本变更的文档面）。

**间隔的归属**：`--interval` 是**宿主命令的运行参数**（同 `ui serve --host/--port`），
**不进 `ConfigSpec`** —— 配置面是「事实」（`pet.enabled`/`persons_dir`），这是「这次怎么跑」。

## 决策 2：驱动薄壳的形态（可测 + 故障隔离）

```
PetWakeDriver(sessions, *, sleep=time.sleep)
  ├─ tick() -> list[WakeOutcome]        # 一轮：逐会话唤醒
  └─ run(interval, *, on_tick=None)     # 常驻：tick → on_tick → sleep(interval) → …
```

- **`sessions` 是可调用体**（`manager.list`），每轮**重取** ⇒ 驱动期间新注册的宠物自动纳入；
- **`tick()` 返回结构化结果**而不是自己打印 ⇒ 库层无副作用、单测无需 capsys；
  `WakeOutcome.status ∈ {woken, skipped, failed}` + `reason`；
- **故障隔离**（规格 R8「A 宠物异常不影响 B 宠物」）：
  `PetError`（让行 `PET_YIELDING` / 退避 `PET_BACKOFF` / 未激活 `PET_NOT_ACTIVE`）= **预期态，静默跳过**；
  其他异常 = **意外失败**，记 `FAILED` 并**继续**其余宠物（同 B4「单端点不可达只告警跳过」口径）。
  为什么预期态静默：让行是**设计中的常态**（主循环 busy），每次唤醒都刷 stderr 就是噪音；
  意外失败才需要主人可见。
- **`sleep` 可注入** ⇒ 节拍测试**确定性**（注入的 sleep 在第二轮后抛 `KeyboardInterrupt`，
  断言恰好驱动两轮），不为测试引入 `--iterations` 生产表面（对齐 `0052` 给 `CircuitBreaker`
  注入 `clock` 的先例）。

## 决策 3：CLI 面（`--interval` 从 `rest` 提取）

`pet` 子命令用 `nargs=argparse.REMAINDER` 收自由文本（`pet gather 今日新闻`），
故 `pet run --interval 5` 的两个 token 落在 `rest` 里 —— 与既有 `--name` **同一处理方式**
（`_split_pet_name` 先例），不为此改 parser 结构（改 `REMAINDER` 会波及其余 verb 的
自由文本语义）。非法 / 非正取值 ⇒ 报用法并返回 1（复用既有 `PET_*` 之外的 CLI 用法错误口径）。

**无已注册会话**：打印提示（引导三入口激活）并退出 0 —— 不自动造宠物（激活归三入口）。

## 已否决

- `ui serve` 后台线程（见决策 1）；
- `pet.wake_interval_s` 配置键（决策 1 末段）；
- 自动激活 / 缺省 persona 造宠物（第二真源）；
- `--oneshot` / `--iterations` / `--max-ticks`（测试用注入 `sleep` 覆盖）；
- 把驱动放进 `runtime.py`（组合根只装配，不驱动；驱动是**宿主行为**）；
- 让 `wake()` 内部吞异常后返回结果对象（改领域语义以迁就驱动，方向反了）。

## 转出

- **E26**（`surprise()` / `MicrotaskRunner` 零调用方）保持开放（用户裁决）；
- **E27**（`IMGateway` 零生产装配）需真实平台凭证；
- E28 关闭后，账本 E 类仅余 E5 / E20①（保持开放）/ E26 / E27。
