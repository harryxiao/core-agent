# Design 0267 — 委托动作并发判级修正

## D1 判定口径

```python
_CONCURRENT_DENY_TOKENS = ("write", "spawn", "outbound", "delegate")
```

- 判定仍是**fail-closed 的声明式词元匹配**：工具只要有一个 coeffect 含 deny 词元即不并发。
- `agent:delegate` 命中 `delegate` ⇒ 串行屏障。未来若出现 `agent:spawn` 等新 coeffect，
  应由其命名沿用既有 `spawn` / `write` 词元，或在新增时补词元（本 change 不预造词元）。
- 不用 `reversible` 作判据：它表达「效应能否撤销」，不是「是否只读」；既有只读测试工具
  也常声明 `reversible=False`，该口径会误伤只读并发。

## D2 批次边界

`_prepare_group` / `_absorb` 既有逻辑不变：不可并发动作留在 `pending`，作为后续并发段之间的
屏障。修正后两个连续 delegate 不再被同一 `gather` 吸收，而是各自串行执行。

## D3 不做

- 不给 delegate 增加父 loop 的效应归因（子 Agent 写入仍不进入父 `EffectTracker`）；
- 不新增运行时开关（这是正确性修复，缺省即生效）。
