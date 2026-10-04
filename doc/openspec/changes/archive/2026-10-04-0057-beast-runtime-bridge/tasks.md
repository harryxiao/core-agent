# 任务：beast-runtime-bridge

## 1. 规格（先行）

- [x] 1.1 `doc/openspec/changes/0057-.../specs/beast-mode/spec.md` MODIFIED R4 + R5（已写）
- [x] 1.2 归档时合并进 `doc/openspec/specs/beast-mode/spec.md`

## 2. 测试先行（`tests/test_beast_wiring.py`）

- [x] 2.1 `build_runtime` 后全局技能库含 20 枚 `beast.*` 神通，且字段符合 Skill 契约
- [x] 2.2 主 Agent 路由（`domain=None`）**看不到**任何 `beast.*` 专属神通
- [x] 2.3 按域可见：`domain="beast.qinglong"` 只见 `beast.qinglong.*`，不见他兽神通
- [x] 2.4 通用技能对任意 domain 恒可见（作用域不误伤）
- [x] 2.5 生产 `summon` 注入：会话 loop ≠ 默认 echo loop；共享 `runtime.memory`
- [x] 2.6 端到端：`summon` 经真实 loop（假 LLM）跑完 → `remember()` 落 L2 且
      `source == beast.<agent_id>`，主记忆（`source=loop`）不受染
- [x] 2.7 `Runtime` 暴露非空 `beast_manager` / `beast_activator`

## 3. 实现

- [x] 3.1 `src/core/skills/router.py`：`match(..., domain=None)` + `_dedicated_domain` 辅助
- [x] 3.2 `src/core/beast/manager.py`：`loop_factory` / `memory` 注入 → `BeastSession(loop=, memory=)`
- [x] 3.3 `src/core/beast/skills.py`：docstring 去掉「runtime 调用 deferred」
- [x] 3.4 `src/core/runtime.py`：注册神通 + `_loop_hooks(domain)` + `_beast_loop` +
      `BeastManager`/`BeastActivator` + `Runtime` 两字段
- [x] 3.5 `src/core/entry.py`：`_summon`/`_recall` 经 `build_runtime` + `runtime.beast_activator`

## 4. 文档

- [x] 4.1 `doc/03-interfaces/beast-mode-interface.md`：路由作用域 + 组合根装配
- [x] 4.2 `doc/01-architecture/adr.md`：ADR-0060 + 映射表行
- [x] 4.3 `doc/02-modules/beast-mode.md`（若有）装配小节

## 5. 验证与收尾

- [x] 5.1 ruff check / ruff format --check / pyright / pytest 四门全绿
- [x] 5.2 `openspec validate 0057-...` → 手动归档 → `openspec validate --all` 29/29
- [x] 5.3 账本 `coding-plan/phase-19.md` E3 关闭（行 + §3 段 + §0 计数 + §9 步骤）+ README 同步
- [x] 5.4 提交 `feat(beast): 神通运行时桥接（注册 + 专属路由作用域 + 注入 loop/memory，change 0057）`
