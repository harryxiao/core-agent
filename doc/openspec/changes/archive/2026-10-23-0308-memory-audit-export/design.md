# Design — 记忆治理审计与导出（0308）

## D1 审计面挂在哪一层：`MemoryStore` 旁路，而非 CLI / 后端

**选择**：`MemoryStore` 接受可选的 `MemoryAuditLog`，在**已成功**的持久化动作后追加事件。

**理由**：
- 写入来自 loop、CLI、web / 后台子 Agent 多条路径，只审计 CLI 会漏掉绝大多数学会；
- `MemoryBackend.put` 是存储原语，混合「迁移 / 复用回写」等非治理写，语义过粗；
- `MemoryStore` 是唯一同时知道「这是新写入 / 删除 / 遗忘」的层。

**钩子位置**：
| 事件 | 位置 | 说明 |
|---|---|---|
| `write` | `_persist()` 落库后 | `write()`、会话摘要、事实/关系/情景派生、中层摘要全部覆盖 |
| `delete` | `_delete_entry()` 删除后 | 覆盖 `discard()` 与修复流程的删除 |
| `forget` | `forget()` 迁移+打标签后 | 每条一行，`reason="decay"` |
| `export` | CLI 输出成功后经 `record_export()` | 只由导出入口触发 |

**不挂的位置**：
- 幂等重放（0306 fast path）⇒ 零落盘，不审计；
- 重要度闸门拒收 ⇒ 无持久变化，不审计（拒绝告警已有 `RuntimeWarning`）；
- `_reinforce()` / `_put_many()` 复用回写 ⇒ 只改 `reuse_count`，不是知识集变化；
- `migrate()` ⇒ 层间归档已有 `memory.migrate` 效应，且 `forget` 已单独审计；
- `read()` 检索 ⇒ 逐读审计会造成不可控写放大。

## D2 事件只写元数据：密钥红线 + 可关联

事件字段（固定集合，缺省空串，`ts` 为写入时刻）：

```json
{"ts": 1761000000.0, "op": "write", "id": "fact.x", "layer": "L2",
 "kind": "semantic", "source": "extraction", "session_id": "s1",
 "trace_id": "compaction.s1", "content_hash": "sha256:…", "reason": "",
 "count": null, "target": "", "format": ""}
```

- **绝不写 `content`**：审计文件不得成为第二份明文记忆（密钥只引用不读取）；
- `content_hash` 使「删除 / 导出」可与内容关联而不暴露内容（0303 信封已维护）；
- 除 `content_hash` 外的字符串字段先 `redact_secrets` 再截断（id/source/session/trace 128、
  reason 64、target 512、format 16、hash 80）——元数据本身也可能夹带密钥形态；哈希是
  派生摘要（不含内容），只截断不脱敏，否则关联能力被误伤；
- `count` / `target` / `format` 只服务 `export`，其余事件留空。

**事件顺序**：追加在动作成功之后 ⇒ 审计行存在的充要条件是动作已生效；不存在「审计有记录但
写入失败」的假阳性。

## D3 失败语义：fail-open，每实例告警一次

**选择**：追加失败（磁盘满 / 只读 FS / 路径是目录）⇒ 吞异常、`RuntimeWarning` 一次、
记忆操作照常返回成功。

**理由**：审计是观测面，不是写入的持久化前提；把记忆写入绑死在审计可用性上会新增一个
「审计挂 ⇒ 记忆全停」的故障模式。代价是可能丢审计行 —— 登记为已知风险（E244），由外部
监控文件是否持续增长来发现。

**告警一次**：`MemoryAuditLog` 用 `self._warned` 抑制重复告警，避免每轮写入刷屏。

## D4 配置缺省开启 + kill-switch

- `memory.audit_log` 缺省 `true`；集合外取值归一为 `true`（同 `key_fact_extract`：
  笔误不得静默关掉治理能力）；
- 关闭只影响**新事件**：既有 `memory.audit.jsonl` 不被删除、`memory audit` 仍可读；
- 组合根按 `audit_log_enabled()` 决定注入 `MemoryAuditLog(path)` 还是 `None`；
- `MemoryStore` 构造缺省仍是 `None` ⇒ 所有既有单测 / 宿主直接构造零变化。

路径：`$CORE_STATE_DIR/memory.audit.jsonl`（与 `memory.jsonl` / `memory-deleted.jsonl`
同目录约定；0600）。构造函数**不**创建目录或文件，首次事件才 `mkdir(parents=True)`。

## D5 遗忘的「原因 / 墓碑」

不新增墓碑存储：0301 起遗忘条目本身留在 L4 且带 `forgotten` 标签，就是墓碑。审计行补上
`id + content_hash + ts + reason="decay"`，即可回答「何时、因何、依据哪份内容」。
未来若出现别的遗忘原因（管理员显式遗忘 / 容量驱逐），在同一 `reason` 字段扩展；本 change
只产生 `decay`（自然衰减与 L2 软上限触发的衰减共用该值 —— 两者判据同为 `_decay_score`）。

## D6 导出：显式确认 + 脱敏 + 审计

- **缺 `--yes` 一律拒绝**（退出 1，stderr 提示），stdout 不输出任何条目 —— 导出使内容离开
  状态目录，必须是一次显式动作；
- 快照来源 `memory.audit(None)`：**全层 / 全状态**（含 superseded / forgotten），定位是
  治理留档而非注入面；条目顺序沿用后端写序；
- 每行 = `asdict(entry)`，字符串值 `redact_secrets`（正文、来源、会话、trace 一并脱敏）；
  `content_hash` 除外（派生摘要，保留以支持留档关联）；
- `jsonl`（缺省）逐行 JSON；`json` 为缩进数组；
- `--out PATH`：`O_CREAT|O_TRUNC|O_WRONLY` 0600 单次写入，失败退出 1；缺省 stdout；
- 成功后在审计日志追加 `export`（`count` / `target`（stdout 记 `-`）/ `format`）；
  审计关闭时 `record_export()` 为 no-op；
- 导出**不**调用 `read()` ⇒ 不触发 `_reinforce`、不改任何条目。

## D7 CLI 面

```
memory audit  [--limit N]                  # 缺省 50，0 = 全部；坏行跳过
memory export [--format jsonl|json] [--out PATH] --yes
```

`memory audit` 只读 `MemoryAuditLog.read(limit)`（`deque(maxlen=limit)` 只保留尾部），
逐行打印 `ts / op / id / layer / kind / source / session / trace / hash / reason /
count / target / format`（空字段显示 `-`）；文件缺失或空 ⇒「（无审计记录）」退出 0。

## D8 有界性与并发

- 单行 ≤ ~1KB（字段上界之和）；一次事件 = 一次 `os.write`（`O_APPEND`）整行，口径同
  `memory-deleted.jsonl` 与转录落盘 ⇒ 多进程并发的行不会交错（本仓既有约定）；
- 文件不轮转：行数随治理动作线性增长。读取有 `--limit`，写入无上限 —— 轮转/保留期
  **显式不做**，登记 ADR 局限（外部 logrotate 可安全轮转：本进程每行独立 `os.open`）。

## 备选与否决

| 备选 | 否决理由 |
|---|---|
| 复用 `traces.jsonl` 遥测 | 遥测可能被采样 / 关闭 / 外发；治理审计需要独立、稳定、可 grep 的权威旁路 |
| 把审计行写进 `memory.jsonl` | 污染记忆检索面与 0306 幂等判据；审计是事件流，不是记忆条目 |
| 审计默认关（opt-in） | 治理能力默认缺席等于没有；kill-switch 已覆盖「不想多一个文件」的场景 |
| 审计失败 fail-closed | 新增「审计故障 ⇒ 记忆全停」故障模式，与 P1 记忆可用性冲突 |
| 导出复用 `memory get` 循环 | 无确认门、无审计、无法一次成档 |
| 哈希链 / 签名防篡改 | 需要密钥管理与外部锚定，超出 P2-2；先保证「有、且不含明文」 |

## 测试映射

| 需求 | 用例（`tests/test_memory_audit.py` / `test_memory_export_cli.py`） |
|---|---|
| 写入审计、无正文 | `test_write_appends_metadata_only` |
| 幂等重放不审计 | `test_idempotent_replay_writes_no_audit` |
| 闸门拒收不审计 | `test_importance_gate_rejection_writes_no_audit` |
| 删除审计 | `test_delete_appends_audit` |
| 遗忘原因 / 墓碑字段 | `test_forget_appends_reason_and_hash` |
| fail-open + 单次告警 | `test_audit_failure_does_not_block_write_and_warns_once` |
| 0600 / 坏行容错 | `test_audit_file_mode_and_bad_line_tolerance` |
| 配置三面 / 归一 / 接线 | `test_spec_declares_audit_log`、`test_*_can_disable_*`、`test_build_runtime_*` |
| 导出确认门 | `test_export_requires_yes` |
| 导出脱敏 + 格式 + 审计事件 | `test_export_jsonl_redacts_and_audits`、`test_export_json_to_file_0600` |
| 审计读取 / 空态 | `test_memory_audit_prints_tail`、`test_memory_audit_empty` |
