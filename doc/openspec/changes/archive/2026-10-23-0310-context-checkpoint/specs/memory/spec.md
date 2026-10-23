# Spec Delta — memory（0310 上下文检查点：转录工件列与水位读取）

## MODIFIED Requirements

### Requirement: 对话转录持久化（非记忆层级）

系统 SHALL 以**按轮追加**（append-only）的方式持久化对话转录：每一条 SHALL 携带 `session_id`、
`role`（`user` / `assistant`）、`content` 与时间戳，落于 `$CORE_STATE_DIR` 下的**单一文件**。
系统 SHALL 支持按 `session_id` 读取该会话转录与取「最近 N 轮」。

转录 SHALL **不是**记忆层级的任何一层（含 L4 —— L4 是遗忘与压实的**归档层**，非对话原文）：
转录条目 SHALL NOT 被 `MemoryStore.read` 返回，SHALL NOT 参与温度分层检索、排名、`reuse_count`
强化、压实、固化与遗忘。转录只能经**按会话的转录读取面**取出。

转录 SHALL 为**单店 + `session_id` 列**（与记忆同店形态一致，不得为每会话建独立存储实例）。

转录行 SHALL 支持**可选** `artifacts` 列（字符串列表，缺省不写入该键 ⇒ 旧行与旧写入逐字
不变）：记录该轮产出/修改的 workspace 工件路径（`file_write` / `file_patch` 的 `path`，
去重、每轮有界）。该列 SHALL 只服务检查点的工件引用聚合，SHALL NOT 改变转录的任何既有语义。

#### Scenario: 追加后可读

- **GIVEN** 某会话一次性追加了若干轮对话
- **WHEN** 另一进程或另一实例按该 `session_id` 读取转录
- **THEN** 读回全部已追加条目，顺序与追加次序一致

#### Scenario: 按会话读取只见本会话

- **GIVEN** 转录中已有 A、B 两个会话的条目
- **WHEN** 以会话 A 的标识读取转录
- **THEN** 返回结果只含 A 的条目

#### Scenario: 反例守门 —— 他人会话转录不可见

- **GIVEN** 转录中已有 A、B 两个会话的条目
- **WHEN** 以会话 B 的标识读取转录
- **THEN** 返回结果**不含** A 的任何条目

#### Scenario: 反例守门 —— 转录不进记忆检索

- **GIVEN** 转录中已有某会话的对话条目
- **WHEN** 经 `MemoryStore.read` 以同一会话标识检索
- **THEN** 检索结果**不含**任何转录条目（转录非记忆层级）

#### Scenario: 文件缺失或坏行降级

- **GIVEN** 转录文件不存在，或其中某一行损坏（非法 JSON）
- **WHEN** 读取转录
- **THEN** 缺失按空转录处理、坏行被跳过，读取不抛错、不阻断主流程

系统 SHALL 支持**三层滑窗的切分读取**：一次读取 SHALL 同时给出**短带原文**与**中带原文** ——
短带为最近 `short_turns` 轮（沿用既有「按 token 从新到旧截断 + 丢弃开头孤儿 assistant 行」语义），
中带为紧邻短带之前的 `mid_turns` 轮（**不**按 token 截断，其内容由中层摘要承接）。两带 SHALL
**不重叠**；轮数不足时短带吃满、中带为空；`short_turns` 非正 ⇒ 两带皆空。该切分 SHALL 只做一次
转录读取（不重复全量解析）。

#### Scenario: 切分短带与中带且不重叠

- **GIVEN** 某会话已有若干轮转录
- **WHEN** 以短层轮数与中层轮数切分读取
- **THEN** 短带 = 末 `short_turns` 轮原文、中带 = 其前 `mid_turns` 轮原文，两带**无交集**

#### Scenario: 短带沿用 token 截断与孤儿行丢弃

- **GIVEN** 短带原文的 token 超过短层 token 上界
- **WHEN** 切分读取
- **THEN** 短带按 token 从新到旧截断、丢弃开头的孤儿 assistant 行；中带**不**截断

#### Scenario: 轮数不足时中带为空

- **GIVEN** 会话轮数少于短层与中层轮数之和
- **WHEN** 切分读取
- **THEN** 短带取尽可用轮次，中带为空（无更旧内容可摘）

#### Scenario: 关闭短层时两带皆空

- **GIVEN** 短层轮数非正
- **WHEN** 切分读取
- **THEN** 短带与中带皆为空

#### Scenario: 工件列可选且旧行兼容

- **GIVEN** 一行以 `artifacts=["a.py"]` 追加、另一行未提供 `artifacts`
- **WHEN** 按会话读取转录
- **THEN** 前者带 `artifacts=["a.py"]`，后者**不含** `artifacts` 键；读取与既有读取面一致

## ADDED Requirements

### Requirement: 上下文检查点的水位读取

`MemoryStore` SHALL 提供只读、零效应的 `checkpoint_watermark(session_id) -> int`：返回该会话
既有 `context_checkpoint` 条目中**最大**的 `seq_to`；不存在 ⇒ `-1`；`session_id` 为空 ⇒ `-1`。

水位判据 SHALL **只**按条目标签 `context_checkpoint` + `session_id` 匹配，SHALL NOT 过滤层、
`status` 或 `forgotten` 标签 —— 检查点被迁移（L4）、墓碑化（`retracted`）或遗忘后仍计入，
保证水位**单调不回退**（否则重复回写同一淘汰区间）。坏标签（`seq_to:` 非整数）SHALL 被跳过。

#### Scenario: 无检查点 ⇒ -1

- **GIVEN** 某会话从未写过检查点
- **WHEN** 读取水位
- **THEN** 返回 `-1`

#### Scenario: 取最大 seq_to

- **GIVEN** 同一会话存在 `seq_to:3` 与 `seq_to:7` 两条检查点
- **WHEN** 读取水位
- **THEN** 返回 `7`

#### Scenario: 跨层跨状态单调

- **GIVEN** `seq_to:7` 的检查点已被墓碑化（`status="retracted"`、迁 L4）
- **WHEN** 读取水位
- **THEN** 仍返回 `7`，不回退

#### Scenario: 只认本会话

- **GIVEN** 会话 A 有 `seq_to:9` 的检查点，会话 B 无
- **WHEN** 以会话 B 读取水位
- **THEN** 返回 `-1`
