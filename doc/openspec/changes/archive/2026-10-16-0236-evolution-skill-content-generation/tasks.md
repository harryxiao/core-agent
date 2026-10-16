# Tasks 0236: 技能候选内容生成

## 1. Specification
- [x] 1.1 delta ADDED「技能候选内容生成」（DI 工厂 + writer 失败无 content 键 + 未注入逐字不变；
      场景：注入成功 / writer 返回 None / 未注入）。
- [x] 1.2 delta MODIFIED「验证门」：装配 `require_skill_content` 时 skill 无有效 content ⇒
      门未过（fail-closed、fail-fast）+ Scenario。
- [x] 1.3 `GATE_CALIBER` 2 → 3；`models.py` 版本轨迹注释追加
      `3 = 技能内容判据（change 0236）`；`openspec validate` 本 change 全绿。

## 2. Tests（先红）
- [x] 2.1 `content.py`：`validate_skill_content` 对 `SkillContent` 与 dict 四态；
      `build_skill_content_prompt` 含 issue，notes 条数 ≤3、单条 ≤400。
- [x] 2.2 `skill_content_writer_with(llm)`：合法 JSON ⇒ SkillContent；非法 JSON / 结构不符 /
      调用异常 ⇒ None（不抛）。
- [x] 2.3 Proposer：注入 + skill + 非空 content ⇒ delta 含 content（asdict 往返）；
      writer 返回 None 或未注入 ⇒ delta **仅** `{"issue": ...}`（无 content 键）；
      plugin + 注入也不生成。
- [x] 2.4 Validator `require_skill_content=True`：skill 无 content ⇒ passed=False、
      review 含「空壳」、test_results 空、不跑运行时测试；有 content ⇒ 既有 review+tests；
      plugin 不受影响；缺省 False ⇒ 逐字不变。
- [x] 2.5 `_crystallize_skill`：content 存在 ⇒ Skill 落库含各字段（instructions 已脱敏；
      `description` 优先 content 值、空则回退 issue）；content 缺省 ⇒ 空壳回退逐字不变。
- [x] 2.6 GATE_CALIBER=3：caliber 2 已确认 ⇒ `GATE_CALIBER_STALE`；caliber 3 正常投放。
- [x] 2.7 runtime：组合根 `skill_content_writer_with(_llm_text)` + `require_skill_content=True`
      同开同关、装配不抛；既有 evolution 测试全绿。

## 3. Implementation
- [x] 3.1 新建 `content.py`：SkillContent / validate / prompt / `skill_content_writer_with`；
      不 import LLM 抽象。
- [x] 3.2 `proposer.py`：可选 `writer`；按 D3 写 delta。
- [x] 3.3 `validator.py`：`require_skill_content` 判据（缺省 False）。
- [x] 3.4 `engine.py`：`_crystallize_skill` 按 content 结晶；instructions `redact_secrets`；
      `description` 优先 content 值、缺省回退 issue。
- [x] 3.5 `models.py`：`GATE_CALIBER = 3`；版本轨迹注释追加
      `3 = 技能内容判据（change 0236）`。
- [x] 3.6 `runtime.py`：工厂先调用再注入；同开同关。

## 4. Gates & Archive
- [x] 4.1 四门禁相关测试绿。
- [x] 4.2 本 change `openspec validate` 全绿（`--all` 仍受既有 0230 无 delta 拖累）；归档；提交
      `feat(evolution): 技能候选内容生成（change 0236）`。
