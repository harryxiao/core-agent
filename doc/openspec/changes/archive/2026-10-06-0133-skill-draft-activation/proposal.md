# 变更提案：技能 draft → active 显式启用路径（change 0133 / phase-34 E72）

## 背景

`coding-plan/phase-34.md` §1 登记的 **E72**（中，用户可见）。

技能安装链路只**进**不出：

- `skillhub/client.py:66` 下载校验通过后恒置 `skill.status = "draft"` 并入库；
- `skills/router.py:98` 路由候选集只放行 `s.status in ("active", "gray")`；
- **全仓没有 draft → active 的迁移路径**（`grep` 确认无处调用 set status active，SOP 提炼是
  另造 `status="active"` 的新技能，不是迁移）。

后果：CLI `skill install` 打印「已安装技能 X（draft，需本地显式激活后可用）」，但**没有**任何
命令能做到那件事 —— 装完的技能永远不被路由，是死胡同。而 `skillhub/spec.md` 的 Scenario
「下载默认 draft」早已写「**需显式激活后可用**」，`skillhub-interface.md:35` 也自述「需本地显式
激活后才进入可用技能集」—— 规格指着一扇不存在的门（既有 `SkillHubErrorCode.SKILL_NOT_ACTIVE`
与 `skills-interface.md:137` 的错误码表同为此门的痕迹）。

## 变更内容

1. **启用路径**（`src/core/skills/library.py`）：新增 `SkillLibrary.activate(skill_id, *,
   effect_tracker=None) -> Skill` —— 置 `status="active"` 并落盘；已 `active` 时**幂等 no-op**；
   未知 id 抛 `KeyError`（对齐 `lookup` / `remove` 口径，不静默创建）；注入追踪器时登记可逆效应
   （undo 恢复启用前状态），未注入则不记（零行为变化，同 `SopExtractor` 的接缝口径）。
2. **路由放行集不变**（`router.py`）：仍只放行 `active` / `gray` —— 本 change **只补迁移路径**，
   不改路由口径，也不自动启用任何东西。
3. **CLI 触达点**（`src/core/entry.py`）：新增 `skill activate <name>` 子命令 → `_skill_activate`
   （走**与组合根同源**的持久技能库 `$CORE_STATE_DIR/skills.json`，故启用跨进程可见）。
4. **规格**：
   - `skills/spec.md` **ADDED**「技能启用（draft → active）」：启用入口 / 幂等 / 未知 id 拒绝 /
     可逆 / 路由放行集不变 + 6 Scenario。
   - `skillhub/spec.md` **MODIFIED**「签名校验与可信下载」：把「需显式激活后可用」的悬空指认
     接到 skills 规格的启用路径上（下载恒 draft，**不自动启用**；须经显式启用方可进路由）。

## 不做（明确排除）

- **不自动启用**：下载/注册后恒 `draft` —— 启用必须是**显式动作**（安全默认，规格明写）。
- **不改路由放行集**：不把 `draft` 加进候选（那等于取消启用这一步）。
- **不新增 ErrorCode**：沿用 `KeyError`（`lookup`/`remove` 的既有口径），不扩错误码表。
- **不动 `SKILL_NOT_ACTIVE`**：它是**审核**路径的码（`publisher.py:70` 在用），与本次启用无关。

## 影响面

| 面 | 变化 |
|---|---|
| `SkillLibrary` | 新增 `activate`（唯一新 API）；`register`/`lookup`/`remove` 逐字不变 |
| 路由 | **不变**（放行集仍 `active`/`gray`） |
| CLI | 新增 `skill activate <name>`；未注册技能退出码非零 |
| 安装链路 | 不变（仍落 draft）—— 但从此**有一条门可以走出去** |

## 验证

- 四门禁：`ruff check` / `ruff format --check` / `pyright` **0/0/0** / `pytest -q`（1622 → 1629）。
- `openspec validate --all`：active 期 31/0，归档后 30/0。
