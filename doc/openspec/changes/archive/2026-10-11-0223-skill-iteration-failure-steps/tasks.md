# 0223 任务 — 技能迭代注入「失败实况」

- [x] 1. **测试先行（红）**：`tests/test_skills.py` 增 5 例（块在场 / 缺省逐字 / 有界 / 脱敏 /
      `consider` 透传）；`tests/test_phase13.py` 增 1 例（组合根失败轮把本轮 steps 交给改写器）。
      → 实测：`6 failed`（`TypeError: unexpected keyword argument 'failure_steps'`）。
- [x] 2. **实现（绿）**：`src/core/skills/iteration.py`
      - 常量 `_MAX_FAILURE_STEPS = 5` / `_MAX_FAILURE_STEP_CHARS = 200`
      - `_failure_steps_block()`（脱敏 → 截断 → 取末 5 步；空/全空白 ⇒ 空串）
      - `build_iterate_prompt(skill, stats, *, failure_steps=())`
      - `SkillIterator.consider(skill, *, failure_steps=())`
      - `src/core/runtime.py` `on_turn`：`consider(skill, failure_steps=steps)`
      → 实测：目标 6 例 `6 passed`。
- [x] 3. **反证**：摘掉 `runtime.py` 的 `failure_steps=steps` ⇒ 组合根用例红；摘掉
      `build_iterate_prompt` 的块 ⇒ 4 例红；复原 ⇒ md5 相同。
- [x] 4. **四门禁**：ruff check / ruff format --check / pyright 0-0-0 / pytest 全绿。
- [x] 5. **规格**：`skip_specs: true`（规格中性 —— 见 proposal「Impact」）。
- [x] 6. **接口文档**：`doc/03-interfaces/skills-interface.md` §4（`consider` / `build_iterate_prompt`
      签名 + 失败实况一节）。
- [x] 7. **收口**：ADR-0213 ＋ 变更追踪；`known-risk.md` §1/§3；`test-cases.md` §136；
      `Pending-Arbitration.md` PA-02 标 已闭；归档 ＋ 单次提交。
