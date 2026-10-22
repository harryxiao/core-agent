# Design — 0303 记忆条目治理信封与关键事实版本链

## D1 信封字段：五项、全默认、单向兼容

`MemoryEntry` 新增：

| 字段 | 默认 | 语义 |
|---|---|---|
| `content_hash` | `""` | `sha256(content.strip())` 的十六进制；**写入时**由 store 计算（调用方显式给值则尊重） |
| `status` | `"active"` | `active` = 在检索面可见；`superseded` = 已被新版本替代 |
| `version` | `1` | 本条目的版本号（同链递增，从 1 起） |
| `parent_id` | `""` | 被本版本替代的条目 id（首版为空） |
| `superseded_by` | `""` | 仅旧版本填写：替代它的新版本 id |

落盘面 `FileBackend` 用 `asdict` 序列化、`MemoryEntry(**json.loads(line))` 反序列化：
旧行缺键 ⇒ 走默认值（**读旧兼容**）；新行多键 ⇒ 旧二进制加载失败（**单向兼容**，回退需同时
回退代码与数据，属已知取舍）。字段全部有默认值 ⇒ 仓内 20+ 构造点**零改动**。

被拒字段：`namespace` / `trust` / `confidence` —— 无消费方，等对应能力立项时再加（见 proposal）。

## D2 版本链只覆盖关键事实

关键事实的 `(entity → value)` 中 value 会随时间变化，**旧值本身是信息**（「当时为什么这么记」），
故必须留历史。做法：

1. 取该实体的**活跃版本**（链头）：id 为 `keyfact.<slug>` 或 `keyfact.<slug>.v<N>` 且
   `status == "active"`（旧数据无 status ⇒ 默认 active）。
2. 新正文的 `content_hash` 与链头相同 ⇒ **就地刷新**（tags / trace_id / ts 沿用规则同既往，
   版本不变）；与现值不同 ⇒ 新版本。
3. 新版本 id = `keyfact.<slug>.v<N+1>`、`version = N+1`、`parent_id = 链头 id`；
   链头置 `status="superseded"`、`superseded_by = 新 id`。
4. `slug_entity` 把 `.` 折成 `-` ⇒ `keyfact.<slug>` 前缀**不会**被其它实体的 slug 误命中。

关系条目**不做版本链**：`relation.<h>--<p>--<t>` 的 id 已编码完整三元组，同 id ⇒ 同事实；
changed tail = 新 id。覆盖写不丢信息，保持现状（仅获得信封默认值）。

## D3 读取面：默认剔除 superseded，审计面保留

`read()` 在既有过滤链（来源 → 会话 → 遗忘 → 层）**同一位置**加一条
`status == "active"` 过滤（排名与预算之前）：被剔除项不吃预算、不被复用强化。
`audit()` / `_all_entries()` / `index()` 不受影响 ⇒ 历史版本可追溯。
`failure_lessons()` 与 `_stale_key_facts()` 同步跳过非 active（前者防御性口径统一，后者避免
修复已失效版本）。

**不新增 `include_superseded` 开关**：读取面没有「看历史」的合法消费者；CLI / 审计走
`audit()`。若有真实需求再按规格加（避免无人使用的参数面）。

## D4 取代的可逆性

新版本写入走既有 `write()`（记录 `memory.delete` 效应）；旧版状态变更另记一条
`memory.supersede` 效应（undo = 恢复 `status` / `superseded_by` 并落盘），与新版**同一**
`trace_id`（`compaction.<session>`）。

回滚语义：
- 回滚产生 v2 的那次压实 ⇒ 删除 v2、v1 恢复 active（内容回到旧值）；
- 回滚更早的 v1 压实（在 v2 仍存在时）⇒ 删除 v1；v2 保持 active，链头不变（无「复活」旧值）。

## D5 content_hash 的归一化

`sha256(content.strip().encode("utf-8"))`。只去首尾空白：正文内部空白在事实语义上可辨，
过度归一（折叠空白 / 大小写）会误判「同一条」。哈希**只服务幂等比较与后续 P1-6**，不参与排序。

## D6 兼容与边界

- 旧链路：所有既有 id 不变；首次写入仍落 `keyfact.<slug>`（version=1）。
- `_enforce_l2_cap`：superseded 版本仍计入 L2 条数（未做自动降层 / 保留期，见 P2-3 面）。
- 幂等边界：同实体「取值相同但 entity 显示大小写不同」⇒ content 不同 ⇒ 产生新版本
  （记录的是正文，不是 slug）；这是有意的语义选择。
- 并发写：版本号取自读取时的链头；并发压实同实体可能撞版本号 → last-writer-wins（既有
  `FileBackend` 合并语义）。不引入链锁（压实已有 single-flight，跨进程窗口见 ADR-0291 局限）。

## 测试与反证计划

- 新 `tests/test_memory_version_chain.py`：首版信封 / 变更生成 v2 + 旧版 superseded /
  检索默认只见最新 / audit 见全链 / 同值幂等不升版 / 回滚恢复旧版 / content_hash 一致 /
  关系不升版（覆盖语义不变）。
- 改写：`test_memory_key_facts.py` 的「同实体幂等覆盖」「首见时间戳」两条为版本链口径。
- 反证（`cp` + `md5sum`）：去 status 过滤 ⇒ 检索用例红；去 supersede ⇒ 旧版仍 active 用例红；
  去 content_hash 同值判断 ⇒ 幂等用例红；去 read 的过滤位置（放到预算后）⇒ 预算用例红。
