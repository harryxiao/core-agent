# Design — 0231

## D1. 不变式：忙态复位先于一切呈现收尾

忙态（`_turn_busy`）是 `ui` spec「忙碌中拒绝 / 切换仅在本轮结束后」的**实现载体**，语义是
「本轮执行在途」。**呈现收尾**（固化挂起尾段 / 隐藏状态行）是**尽力而为**的表现层动作。
把表现层动作放在状态复位之前 ⇒ 表现层的一次失败**倒灌**为**状态**失败。修法：状态复位是
**不变式**，必须无条件执行；表现层动作各自容错。

## D2. 归到一个 helper（而非散改三处 `finally`）

三处 `finally` 结构相同 ⇒ 抽 `_end_turn(*, flush_live=False)`，唯一差异（`_run_turn` 需先 flush
挂起尾段）用关键字参数表达。散改三处易漏、易漂移（后续新增 runner 无从对齐）。

## D3. 容错用 `contextlib.suppress(Exception)`（而非裸 `try/except/pass`）

`_flush_live` / `_spin_stop` 的失败类无法穷举（挂载 / 取件 / 屏幕栈拆除期的多种 `Exception`），
而**不变式要求「任何失败都不得阻断复位」** ⇒ 刻意宽捕。用 `contextlib.suppress(Exception)`
显式表达「已知将吞掉、意图如此」，并注成因；`except Exception: pass` 会触发 `SIM105`。

## D4. 不吞轮体异常

`_end_turn` **只**容错**收尾**步骤；轮体（`async for` 循环体）抛出的异常仍由 `finally` 之后
冒泡至 worker（`exit_on_error` 语义不变）。本 change 收窄的是「收尾失败的后果」，不是
「轮体失败的可见性」。

## D5. `_spin_start` 移入 `try`

`_spin_start` 亦触碰 widget（`query_one("#spinner")`）⇒ 其失败同样需要收尾复位。移入 `try` 后
其异常先经 `finally` 的 `_end_turn` 收尾（`_spin_stop` 容错）再冒泡。

## D6. 分发口同不变式（窄改）

`on_input_submitted` 在忙态置位后调用 `run_worker` / 神兽入口；这些调用若抛错，`_turn_busy`
遗留为真。包 `try/except Exception: self._turn_busy = False; raise`（**重新抛出** ⇒ 崩溃可见性
不变，只补复位）。

## 局限

- 不回滚 `_turn_busy` 的置位时机（`:846` 与忙检同上下文、无竞态窗口；勿动）。
- 不治理「收尾失败」的**根因**（`_flush_live` / `_spin_stop` 自身为何抛错）——本 change 只保证
  其失败不再**倒灌**为状态失败；若真抛错，降级为「状态行可能残留」而非「UI 卡死」。
- 不做「重试进度可见」（属后续 change）。
