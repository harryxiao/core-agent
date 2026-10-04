# 任务：skill-ranking-feedback

## 1. 规格（先行）
- [x] 1.1 `specs/skills/spec.md` MODIFIED「技能路由」+「语义路由」（已写）
- [x] 1.2 归档时合并进 `doc/openspec/specs/skills/spec.md`

## 2. 测试先行（`tests/test_skill_ranking.py`）
- [x] 2.1 冷启动：无样本技能排序分 == 基础分（不惩罚新技能）
- [x] 2.2 有样本：基础分相同、全成功 vs 全失败 → 全成功排前，全失败仍返回（下限）
- [x] 2.3 阈值不受加权影响：语义分达阈值 + 历史全失败 → 仍返回（score 被缩放）
- [x] 2.4 未注入 feedback → 与纯基础分一致（零回归）
- [x] 2.5 组合根注入同一实例：`runtime.skill_router._feedback is runtime.skill_feedback`
- [x] 2.6 端到端：写入成败后 `match` 顺序随之改变

## 3. 实现
- [x] 3.1 `src/core/skills/router.py`：`feedback` 注入 + `_rank` 因子
- [x] 3.2 `src/core/runtime.py`：`skill_feedback` 构造前移 + 注入 `skill_router`

## 4. 文档
- [x] 4.1 `doc/03-interfaces/skills-interface.md`：排序口径表 + `score` 语义
- [x] 4.2 `doc/02-modules/skills.md`：排序小节
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0061 + 映射表行

## 5. 验证与收尾
- [x] 5.1 四门全绿（ruff / format / pyright / pytest）
- [x] 5.2 `openspec validate 0058-...` → 手动归档 → `openspec validate --all` 29/29
- [x] 5.3 账本 A7 关闭 + 新增 **A11**（预筛推迟，含前置）+ §0 计数 + §9 步骤 8
- [x] 5.4 提交 `feat(skills): 技能排序接历史成功率因子（change 0058）`
