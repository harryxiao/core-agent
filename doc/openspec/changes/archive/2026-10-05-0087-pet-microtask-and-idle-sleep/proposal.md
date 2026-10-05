# 0087 — pet 微任务真实化与空闲自治睡眠（账本 E26 的 microtask 半边 + ③）

## 为什么

两件互锁的事，合在一个变更里：

1. **E26 的 microtask 半边**：`MicrotaskRunner` 在 `src/` **零生产调用方**、无触发策略。且其「产出」是
   **预制文案**（`terminal_walk` 谎称「看了看最近的命令历史」、`system_hint` 谎称「发现一条系统小提示」）
   —— 与 change `0086` 修掉的 `surprise()` 谎报**同型**：投出即谎报。
2. **用户诉求 ③「干完无任务也可以自己睡觉」**：今天 `wake()` **不消费任务**（规格测试断言 `_tasks` 不减少），
   空队列时回退**编造**一个「闲逛探索」任务 ⇒ 宠物**永不空闲、永不休眠**、且在做假事。

两者天然咬合：**「空闲」正是微任务的触发点**（规格 R14「宠物空闲触发日常微任务」）。

## 用户裁决

- **全量 ①②+③**、跨进程**仅同进程**；本变更 = **E26 的 microtask 半边 + ③**。
- 前序：`0086`（惊喜真实化）已闭；后续：`0088`（`/pet [cmd]` 控制面）。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/pet/core/session.py` | `wake()` **消费队首任务**（`popleft`）；队列清空 ⇒ `_go_idle()`（进入让行态 = 休眠，不编造任务）；注入面增 `microtasks: Callable[[], str \| None] \| None`；`restore()` 同步；`dispatch()` 清让行态 ⇒ **新任务自动唤醒** |
| `src/core/pet/core/activator.py` | `PetActivator` 增 `microtasks` 注入面并透传给 `PetSession` |
| `src/core/pet/microtask/microtask.py` | 三条微任务**真实化**：`terminal_walk` 只读命令历史**只报条数**（绝不外泄内容）、`system_hint` 真探负载（不显著则**不出声**）、`nonsense_comment` 仅在有 `comment_writer` 时真写回；**无真实产出 ⇒ `None`**（不谎报）。探测函数可注入（测试确定性 / 生产缺省真探） |
| `src/core/runtime.py` | 组合根装配 `MicrotaskRunner()`，`microtasks=runner.run` 注入 `PetActivator` 与注册表恢复工厂 |
| `doc/openspec/specs/pet-mode/spec.md` | MODIFIED「Background Pet Session Lifecycle」（任务出队 / 空闲入睡 / 新任务唤醒 + 3 场景）；MODIFIED「Pet Micro-tasks」（真实产出 + 空闲触发 + 2 场景） |
| `doc/03-interfaces/pet-mode-interface.md` | §1 注入面 + §5 表「空闲/微任务」行 |
| `doc/02-modules/pet.md` | §3.5 / §5 订正（微任务已接线） |
| `doc/01-architecture/adr.md` | ADR-0082（任务一次性 / 空闲=让行态 / 微任务真实化）+ 映射表行 |
| `doc/04-testing/test-cases.md` | TC-PET-07 |

## 明确不做

- **不新增会话枚举**：休眠复用既有**让行态**（规格明文「仅四态」「让行复用 orchestration `SUSPENDED` 语义」）。
- **不引入调度线程**：内核不常驻（`0065`／E17 已登记），入睡只是让行态 ⇒ 宿主驱动（`0083`）**天然**把
  它当 `skipped` 跳过，**零改驱动**。
- **不让微任务报预制文案**：内容不真就 `None`（与 `0086` 同口径）。
- **不外泄命令历史内容**：`terminal_walk` **只报条数**（历史可能含密钥/隐私；对齐「密钥只引用不读取」）。
- **不处理跨进程控制**（用户裁决仅同进程）——`0088` 的控制面同样只作用本进程。
