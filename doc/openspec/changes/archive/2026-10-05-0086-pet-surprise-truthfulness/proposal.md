# 0086 — pet 惊喜去谎报与上报（账本 E26 的 surprise 半边）

## 为什么（账本 E26）

`PetSession.surprise()` 在 `src/` 与 `tests/` **零调用方**（E16 收口时有意不接线），且行为有两个毛病：

```python
def surprise(self) -> str:
    if self._preferences:
        key, value = next(iter(self._preferences.items()))
        return f"发现可代办：{key}={value}，已帮你安排"   # ← 只返回字符串，从未真的「安排」
    return "发现一件你可能喜欢的小事，已帮你安排"          # ← 无偏好也报「已安排」＝谎报
```

- **无偏好分支是谎报**：没有任何可代办前提，却宣称「已帮你安排」。
- **有偏好分支也是谎报**：宣称「已帮你安排」，但**从未执行任何动作** —— 只是拼了条文案。

用户诉求（本次裁决）：宠物**在干活时可以随时上报惊喜**。要满足它，惊喜必须**真的有产出**，
而不是往主人耳朵里塞一句「已安排」。

## 用户裁决

- **闭环范围：全量 ①②+③**（① 控制面 / ② 惊喜去谎报 / ③ 空闲自治睡眠），跨进程**仅同进程**。
- 本变更 = **② 的 surprise 半边**（E26 记名的两半之一）；微任务半边 → change `0087`，控制面 → change `0088`。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/pet/core/session.py` | `surprise()` 签名改 `str \| None`：**无偏好 ⇒ `None`**（不产出、不谎报）；有偏好 ⇒ 经**真实 loop** 执行一次偏好驱动的代办、回报**真实结果**。`_notify_owner()` 在**同一反馈节拍**上追加惊喜投递（`None` 不投递），**失败 fail-soft**（惊喜非关键路径，不阻断唤醒收尾） |
| `doc/openspec/specs/pet-mode/spec.md` | MODIFIED「Periodic Feedback and Surprise」：惊喜以**真实可代办**为前提 + 无可代办不产出 + 节拍同源 + 失败不阻断；新场景 3 条 |
| `doc/03-interfaces/pet-mode-interface.md` | §1 签名 `str \| None` + §5 表「惊喜」行订正 |
| `doc/02-modules/pet.md` | §3.5 / §5 订正（`surprise()` 已接线，不再是「零调用方」） |
| `doc/01-architecture/adr.md` | ADR-0081（真实化 + 节拍同源 + fail-soft）+ 映射表行 |
| `doc/04-testing/test-cases.md` | TC-PET-1x（惊喜） |

## 明确不做

- **不让 `surprise()` 编造可代办事项**：没有真实前提就没有输出（这是本变更的全部意义）。
- **不新增触发心跳**：复用既有 `_on_feedback_cycle()` 判据（同 `report()`），每周期至多一次，不刷屏；
  「随时」= 工作节拍内**自动**上报，无需主人催问。
- **不改 `report()`**：周期反馈语义独立，本变更只在其后追加惊喜。
- **不处理跨进程**（用户裁决仅同进程）：本变更不引入任何控制通道。
- **不接线 `MicrotaskRunner`**：转出 change `0087`（微任务真实化 + 空闲入睡）。
