# Design 0205 — SOP 技能退役

## 决策一览

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| D1 | 触发器 | **迭代连续退化**达阈（`decide()` 既有分支折叠计数） | 用户裁决③：自动、不依赖人工；信号已存在（`result.winner != draft`），缺的只是累计 |
| D2 | 阈值 | 公开常量 `RETIRE_AFTER_DEGRADATIONS = 3` | 单次是方差、连续 3 次是趋势；与 `_ITERATE_MIN_SAMPLES` 同量级 |
| D3 | 退役面 | `SkillLibrary.deprecate`（镜像 `activate`，复用 `_restore_status`） | 最小面：唯一既有「改 status + 落盘 + 可逆效应」的正路模板 |
| D4 | 开关 | 构造参 `retire_after: int \| None = None` + 配置 `skills.retirement`（缺省 `False`） | 用户裁决④：缺省关 ⇒ 既有路径逐字不变 |
| D5 | 防复活 | `sop.py::observe` 守卫（不改 `SkillLibrary.register`） | `register` 的覆盖语义被 beast/notes/evolution 复用；改它会波及三面 |
| D6 | 归零 | 一次提升**清计数** | 「连续」的字面语义；抖动不累积 |

## D1 计数为什么折叠进 `decide()` 而不新开方法

`decide()`（`iteration.py:122-136`）的退化分支里 `result.winner` 与 `draft` **本就在局部**，
且 `skill` 已入参。新开 `_maybe_retire(skill)` 方法需要把「本次是否退化」再传一遍，或让新方法
重算 A/B——前者是冗余参数、后者是重复计算。折叠进既有分支 = **运行时钩子零改动**
（`runtime.py:628` 的 `skill_iterator.decide(skill)` 调用点逐字不变）。

关时（`retire_after is None`）**不写任何新状态** ⇒ `decide()` 的外部可观察行为逐字不变
（`_degradations` 恒空）。

## D4 守卫写法（关键：逐字等价 + 无 `elif` 嵌套）

```python
if result.winner == draft:
    if self._retire_after is not None:
        self._degradations.pop(skill.skill_id, None)  # 提升 ⇒ 归零
    self._apply(skill, draft, drafts[draft])
else:
    del drafts[draft]  # 退化：只丢草稿，技能本体不动（单次不置 deprecated）
    if self._retire_after is not None:
        n = self._degradations.get(skill.skill_id, 0) + 1
        if n >= self._retire_after:
            self._library.deprecate(skill.skill_id, effect_tracker=self._tracker)
            self._degradations.pop(skill.skill_id, None)
        else:
            self._degradations[skill.skill_id] = n
```

- 缺省关：两个 `if self._retire_after is not None` 均假 ⇒ 与旧 `decide()` **逐字等价**。
- 嵌套深度：`if/else` + 内层 `if` = **2 层**，`for`/`with` 之外不叠加 ⇒
  `test_control_flow_nesting_max_three` 安全（`0203` 教训：`elif` 也记作一层 `If`）。

## D5 为什么防复活守卫放 `observe()` 而不是 `register()`

`SkillLibrary.register`（`library.py:45-56`）的「同名覆盖」语义是**通用契约**：`_load` 恢复、
beast 神通注册、notes 工作流技能、evolution 结晶产物**四处**都依赖它。把「拒绝覆盖 deprecated」
塞进 `register` 会**改变这四处的行为**（超出本 change 范围，且 evolution 结晶产物以 `skills.evolution.`
前缀命名，语义不同）。

守卫放 `observe()`（唯一会「同组键重复提炼 ⇒ 同 `skill_id`」的正路，`_skill_id_for` 由组键
确定性哈希）——**只拦 SOP 重抽这一条路**，语义精确。守卫动作 = 跳过 `register` + 清组（免同批
样本反复触发提炼调用）+ `warnings.warn` **只报组键**（**绝不回显正文**，密钥红线）。

## 接线与配置

- `manager.py`：ConfigSpec `skills.retirement`（**全仓首个 `skills.*` 键**）+ 访问器
  `skill_retirement()`（**逐字复刻** `semantic_forgetting()` 模式，读 `config.extra.get("skills")`；
  `skills` 为非结构化段 ⇒ 集合外取值归一为关，不阻断启动）。
- `runtime.py`：`SkillIterator(..., retire_after=RETIRE_AFTER_DEGRADATIONS if
  config.skill_retirement() else None)` —— `SkillIterator` 已在 `:572` 构造、`:628` 调 `decide`
  ⇒ 退役**其后自动生效**，无新钩子。

## 零回归（为什么没有既有测试转红）

`SkillIterator` 的既有用例全部**走缺省构造**（不传 `retire_after`）⇒ `_retire_after=None` ⇒
退化分支只 `del drafts[draft]`、不碰 `status` ⇒ 逐字不变。已核验：`tests/test_skills.py` 的迭代 /
A-B 用例均缺省构造。⇒ **0205 零既有测试破坏**；反证必须**显式翻转** `retire_after`。

## 局限（写入 ADR-0195）

- **退役不可自动复活**（用户裁决⑤）；复活需显式 `SkillLibrary.activate`（既有面）。
- **连续退化计数是进程内状态**：跨进程重启归零 ⇒ 「连续」为进程内语义（同 `0202` 前序表性质）。
- **可回滚仅当注入 tracker**：`runtime.py:581` 已注入；未注入时仍改状态但不记效应（与 `activate`
  同口径）。
- **三处既有旁路各置 `status` 却不共享本次 trace**（`VersionManager._deprecate` /
  `SkillCrystallizer.dissolve`（死代码） / `EvolutionEngine.dissolve`）——本 change **不动**，登记为已知。
- **`SkillLibrary._index` 既有重复 bug**（`_index` 无条件 append，`library.py:129`）本 change
  **不修**（超范围，仅登记）。
