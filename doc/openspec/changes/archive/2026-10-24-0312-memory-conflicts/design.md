# Design — 冲突裁决的可见性与计数（0312）

## 目标与非目标

让 SDD §5.5 的「裁决留痕」在当前数据模型下**可实现、可查询、可计数**：新增冲突事件、
指标、统计字段与只读 CLI。**不改**版本链、检索、注入、压实与遗忘语义。

## D1 只实现第 3 级裁决（新证据 > 旧证据），其余规则登记为不可达

**决策**：关键事实取值变化时，裁决规则固定为 `newer_wins`（SDD §5.5 第 3 级）。

理由：
- 关键事实的唯一生产路径是压实抽取（`_write_key_fact`，`source="extraction"`），
  `MemoryEntry` 没有 `trust` / `confidence` 字段，也没有「显式用户更正」信号 ⇒ 规则 1/2/4
  无法判定；若强行按 `ts` 冒充规则 3 之外的规则，只是把同一条规则改名，属伪实现。
- 同批同实体冲突已由 `_plan_key_facts` 按「首条保留 + 告警」归并（0172，规格已钉住），
  不存在「同批并列」这一规则 5 触发点。
- 因此 `disputed` 状态在当前数据模型下**不可达**；引入它会产生永不发生的状态分支
  （违反「不做投机抽象」）。

**被拒**：
- 引入 `trust` / `confidence` 字段并实现规则 2/4：无写入方、无消费方，且与 0303 的裁决
  （P1-1 只落有消费者的字段）冲突。
- 同批冲突标 `disputed`：同批已由首条归并，改变该语义需要重开 0172。
- 规则 5 的「并列注入」：注入面（0302）不做矛盾标注，需要重开上下文渲染，超出观察面。

## D2 冲突计数口径：`superseded_by` 非空，而非 `status=="superseded"`

`entries_superseded` 统计当前状态；旧版被 `retract()` 墓碑化后状态变为 `retracted`，
但仍是一次历史冲突。`conflicts` SHALL 以 `superseded_by != ""` 为判据（与当前状态正交），
保证 `conflicts == 0` ⇔ 从未发生取代。两者不相等是**预期**，文档写明。

## D3 `memory conflicts` 从条目派生，不依赖审计开关

冲突链的两端都在条目里（旧版 `superseded_by` → 新版 id），因此 CLI 只读
`MemoryStore.audit(None)`（全层全状态，零强化）即可覆盖**升级前**的历史链；审计日志只承担
「裁决时刻」的持久事件，不作为 CLI 的唯一数据源（审计可关闭、可丢行）。

排序按**新版时间**（`new.ts`，缺失时退回旧版 `ts`）降序；`--limit N` 缺省 20、`0` 为全部
（对齐 `memory list` / `memory audit`）。取值一律走 `_one_line_summary`（先 `redact_secrets`
再截断）。实体名从 id 派生：`keyfact.<slug>[.vN]` ⇒ `<slug>`；非关键事实 id 原样展示。

## D4 审计事件形状

`MemoryAuditLog.record(op="conflict", entry=旧版, reason="newer_wins", target=新版 id)`：
- `id` / `layer` / `kind` / `source` / `session_id` / `trace_id` / `content_hash` 记旧版元数据；
- `target` 记新版 id（便于与 `memory audit` 的行对齐）；
- 不含正文 / 取值（与 0308 的元数据口径一致）。

`_audit_event` 增加可选 `target` 参数（缺省 `""`），其余调用方逐字不变。审计未接线 ⇒
no-op；追加失败 ⇒ fail-open（0308 语义），指标仍照常计数。

## D5 指标 `memory.conflicts`

`_supersede` 内 `self._metrics.increment("memory.conflicts")`，加入 `FIXED_METRIC_KEYS`
（未发生 ⇒ 0）。实例作用域、零 I/O，与 0311 其余指标同口径。

## 测试与反证

- 新 `tests/test_memory_conflicts.py`：取代计数 / 同值不计数 / 审计行形状 / 审计关闭仍计数 /
  stats 口径（含墓碑化的旧版）/ CLI 文本与 JSON / 排序与 limit / 空库 / 零强化零写入 /
  实体名派生。
- 反证（`cp` 到 `/tmp` + `md5sum` 复原）：去 `_supersede` 指标 ⇒ 计数红；去审计事件 ⇒
  审计行红；`conflicts` 改按 `status=="superseded"` ⇒ 墓碑用例红；CLI 改按审计派生 ⇒
  历史链（无审计）用例红；去脱敏 ⇒ 脱敏用例红。

## 局限（写入 ADR-0302）

- 仅覆盖关键事实链；其他条目的同 id 覆盖不算冲突（无「同实体多值」语义）。
- 规则 1/2/4/5 未实现（无信号 / 不可达），`disputed` 不进入状态机。
- 升级前的历史冲突只能从条目链看到（无 `conflict` 审计行）。
- 审计关闭 / 丢行时，`memory audit` 看不到冲突事件（`memory conflicts` 仍可用）。
- 冲突计数不跨进程汇总（实例指标）。
