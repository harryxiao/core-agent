# Spec Delta — memory（0309 情景保留期与删除墓碑）

## MODIFIED Requirements

### Requirement: 记忆条目的治理信封

每条记忆条目 SHALL 携带治理信封字段，缺省值保证旧数据与既有构造点**逐字兼容**：

- `content_hash`：正文 `strip()` 后的 SHA-256（十六进制）。写入路径 SHALL 在字段为空时自动计算；
  调用方显式给值 SHALL 被尊重。该字段只服务幂等比较 / 内容寻址，SHALL NOT 参与排序打分。
- `status`：`"active"`（缺省）、`"superseded"` 或 `"retracted"`。`"retracted"` SHALL 仅由
  墓碑化（`retract`）设置；墓碑化 SHALL 清空正文并保留 `content_hash` 作为审计关联键。
- `version`：版本号，缺省 `1`，同链递增。
- `parent_id`：被本版本替代的条目 id；首版为空串。
- `superseded_by`：仅旧版本填写，指向替代它的新版本 id。

反序列化 SHALL 对缺键的旧行应用默认值（`active` / `1` / 空串）。检索面 `read()` SHALL 在
**排名与预算之前**剔除 `status != "active"` 的条目（与遗忘 / 层过滤同一位置 ⇒ 不吃预算、
不被复用强化）；`audit()` / `index()` / `_all_entries()` SHALL NOT 施加该过滤（历史可追溯）。
非 `active` 条目 SHALL 同样不进入压实材料（`_episodic_groups` / `_material_for_session`）、
遗忘衰减面与 L2 软上限计数。本条 SHALL NOT 引入 `namespace` / `trust` / `confidence`
（当前无消费方）。

#### Scenario: 旧行缺键 ⇒ 默认值加载
- **GIVEN** `memory.jsonl` 中某行为变更前写入（无治理字段）
- **WHEN** `FileBackend` 重新加载
- **THEN** 条目 `status="active"`、`version=1`、`parent_id=""`、`superseded_by=""`，
  `content_hash` 为空串，且其检索可见性与变更前一致

#### Scenario: 写入自动计算内容哈希
- **GIVEN** 调用方写入条目时未提供 `content_hash`
- **WHEN** 写入完成
- **THEN** 条目 `content_hash == sha256(content.strip())`（正文仅差首尾空白 ⇒ 哈希相同）

#### Scenario: 检索默认排除 superseded
- **GIVEN** 同一实体的两个版本：旧版 `status="superseded"`、新版 `status="active"`
- **WHEN** 以缺省参数 `read()` 检索
- **THEN** 只返回新版；旧版不占预算、`reuse_count` 不递增

#### Scenario: 审计面保留历史版本
- **GIVEN** 同一实体存在 `superseded` 旧版与 `active` 新版
- **WHEN** 调用 `audit()`
- **THEN** 两个版本都返回，旧版 `superseded_by` 指向新版

#### Scenario: 墓碑退出活性面但审计可见
- **GIVEN** 一条条目已墓碑化（`status="retracted"`）
- **WHEN** 分别调用 `read()`、`failure_lessons()` 与 `audit()`
- **THEN** 前两者不返回该条目；`audit()` 返回墓碑，且正文为空、`content_hash` 保留

## ADDED Requirements

### Requirement: 情景记忆保留期与墓碑化

`MemoryStore` SHALL 接受可选构造参数 `episodic_retention_days`（`int | None`，缺省 `None`
⇒ 保留期关闭、行为逐字不变）。配置为正整数 `N` 时，`forget()` SHALL 在自然衰减归档**之前**
执行保留期阶段：

- 判据：`layer == "L2"`、`kind == "episodic"`、`status == "active"`、`ts > 0` 且
  `ts < now - N×86400`；
- 动作：墓碑化该条目——迁至 L4、清空 `content`、置 `status="retracted"`、追加 `retracted`
  标签，保留 `id / content_hash / ts / source / session_id / trace_id / version`；
- 可撤销性：迁移与墓碑化 SHALL 记录同一 `retract.<id>` trace 的可逆效应，回滚后正文、
  状态与层 SHALL 复原；
- 审计：SHALL 追加 `op="delete"`、`reason="retention"`（沿用治理审计日志的字段与
  fail-open 语义）；
- 返回值：到期墓碑 id SHALL 并入 `forget()` 的返回列表；自然衰减归档 SHALL 继续沿用既有
  `reason="decay"`。

保留期 SHALL NOT 依赖衰减评分（近期高频复用的到期条目同样墓碑化）；`ts<=0`（时间未知）
SHALL NOT 被保留期惩罚。保留期 SHALL 由既有维护节拍驱动（循环压实收尾与 `memory maintain`
均调用 `forget()`），SHALL NOT 新增独立维护步骤或改变压实观测事件的 `steps` 组成。
保留期 SHALL NOT 落删除备份文件（备份会重新持有已到期正文）。

`MemoryStore.retract(entry_id, *, reason="tombstone") -> bool` 是墓碑化的唯一原语：存在 ⇒
迁 L4、清空正文、置 `status="retracted"`、追加 `retracted` 标签、记 `memory.retract` 可逆
效应、写一条 `op="delete"` 审计事件并返回 `True`；不存在 ⇒ 返回 `False` 且零落盘 / 零效应 /
零审计。`memory delete <id>` SHALL 在既有备份成功后调用该原语（`reason="tombstone"`）；
备份失败 SHALL fail-closed（不墓碑化）。墓碑 SHALL NOT 出现在 `read()` / `recall()` /
`failure_lessons()` / 压实材料中，但 SHALL 出现在 `audit()` 与 `memory export` 快照中
（`content=""`、`content_hash` 保留）。

#### Scenario: 到期情景墓碑化
- **GIVEN** 一条 `kind="episodic"`、`ts` 早于保留期且状态 active 的 L2 条目
- **WHEN** 调用 `forget()`
- **THEN** 该条目迁 L4、`status="retracted"`、正文为空；返回列表含其 id；审计
  `op="delete"`、`reason="retention"`

#### Scenario: 未到期与时间未知不墓碑化
- **GIVEN** 一条未到期的 episodic 与一条 `ts=0` 的 episodic
- **WHEN** 调用 `forget()`（两者衰减评分均高于阈值）
- **THEN** 两条均保持 `status="active"`、正文与层不变

#### Scenario: 非情景与摘要类不受保留期影响
- **GIVEN** 一条早于保留期的 `kind="semantic"` 摘要条目与一条早于保留期的 L2 派生事实
- **WHEN** 调用 `forget()`
- **THEN** 两条均不被保留期墓碑化（派生事实仅受既有语义遗忘开关约束）

#### Scenario: 关闭保留期恢复变更前行为
- **GIVEN** `episodic_retention_days` 为 `None` 或 `0`
- **WHEN** 调用 `forget()`
- **THEN** 保留期阶段不产生任何墓碑化；返回值与变更前逐字一致

#### Scenario: 显式删除产生墓碑
- **GIVEN** 一条待删除条目
- **WHEN** `memory delete <id>` 备份成功并调用 `retract(..., reason="tombstone")`
- **THEN** 条目仍在 L4、`status="retracted"`、正文为空、`content_hash` 与备份中一致；
  审计 `op="delete"`、`reason="tombstone"`；`read()` 不再返回

#### Scenario: 墓碑不进入压实材料
- **GIVEN** 同一会话内一条墓碑与一条 active episodic
- **WHEN** 压实取材料（`_episodic_groups`）
- **THEN** 只含 active 条目；墓碑不参与摘要 / 关键事实 / 情景归纳

#### Scenario: 墓碑化可回滚
- **GIVEN** 一条刚被 `retract` 的条目
- **WHEN** 按 `retract.<id>` trace 回滚
- **THEN** 正文、`status="active"` 与原层均复原
