# 沉淀质量重构：候选区 + 晋升（notes/skills）

## Why

当前「经验 → 技能」与「对话 → 笔记」两条沉淀链路都**默认把对话原文直接固化**，缺少质量判定与人工闸门：

- `~/.core/state/notes/` 35 篇中 34 篇为 `source=notes.turn`：文件名是用户原话（`写一个吧.md`、
  `刚才我第一次提问的是啥话题.md`），正文是 `## 解决过程` + 原始动作行。它们由
  `runtime._loop_hooks` 在每次成功写效应轮无条件调用 `NoteStore.observe_turn` 产生，并随即进入
  Consult 命中面与笔记清单，污染每轮上下文。
- `skills.json` 的 3 条 active SOP 全为垃圾：`继续`（某次变更的 trace 细节）、`hi`（模型**拒绝文本**
  被当作 SOP 发布）、`完成了吗`（占位步骤）。`SopExtractor` 在 3 条样本达阈后直接以
  `status="active"` 入库，自动进入路由。
- `sop-samples.json` 91 组样本中大量为闲聊；空行动序列也会被累积。

用户已确认方向：**① 笔记两段式（候选区 + 晋升）② 技能先 draft、显式启用后生效 ③ 存量移入回收目录，
不删除**。

## What Changes

- **notes**：成功轮不再直写 canonical。新增确定性预滤 + 注入式提炼器（严格 JSON）产出**候选**，
  候选对 `list/search/digest` 不可见；`notes candidate-promote` 经来源守护写入 canonical
  （`source=notes.sediment`），保留既有 `pinned/pin_priority`；`candidate-reject` 丢弃。
- **notes 存量清理**：`notes prune --source notes.turn` 把指定来源笔记**移动**到
  `$CORE_STATE_DIR/notes-trash/<stamp>/` 并写 0600 manifest；默认跳过 pinned；`--dry-run` 只报告。
- **skills**：`SopExtractor` 增加准入闸（空 steps / 短任务 / 无工具轨迹 / 重复轨迹）、线程安全与
  拒绝文本门；提炼产物一律 `status="draft"`，经 `skill activate` 才进路由；已 active/gray 的技能
  不被重抽覆盖。新增 `skill list [--status]` 与 `skill deprecate`。
- **loop 契约**：`TurnObserver` 扩为 4 参（追加最终回复 `reply`），供沉淀判定使用。
- **配置**：`notes.candidate_distill`（缺省 true）与 `notes.candidate_auto_promote`（缺省 false）
  两条 ConfigSpec；`config set notes.*` 可用。

## Non-Goals

- 不做默认自动晋升；不删除任何存量文件（只移入回收目录）。
- 不新增会话维度（notes 仍为全局层）；notes 不 import LLM/skills/loop，skills 不 import notes/loop。
- 不引入第三方向量库 / RAG 依赖；不改前端。
- 不做「定期重蒸馏」第三阶段；不做跨进程候选区文件锁（登记为已知风险）。
