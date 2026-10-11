# Tasks 0222

- [x] 规格 delta（`loop` MODIFIED：四种→五种形态 ＋ 形态 5 ＋ 改写中间夹带句 ＋ MODIFIED/ADDED Scenario）。
- [x] `src/core/loop/planner.py`：`_UNPARSED_EMBEDDED` ＋ `_embedded_action_payload()` ＋ `_parse` 接线。
- [x] 测试：改写旧 2 条（`..._mid_text_stays_reply` → 可见失败；`..._closed_tail_object_without_tool_id`
      名实不符 → 形态 5 失败）＋ 新增 2 条（夹带动作不执行 / 夹带非动作仍回复）；20 passed。
- [x] 反证：摘形态 5 分支 ⇒ 3 failed, 17 passed；复原 md5 相同。
- [x] ADR-0212（取代 ADR-0156 子情形语义）＋ 变更追踪表。
- [x] `doc/03-interfaces/loop-interface.md`（形态表 ＋ 只认尾部注记）同步。
- [x] `coding-plan/known-risk.md` §1 E159 / §3 ADR-0212；`doc/04-testing/test-cases.md` §135；
      `coding-plan/Pending-Arbitration.md` PA-01 标**已闭**。
- [x] 四门禁 ＋ `openspec validate --all` ＋ 手工归档 ＋ 台账回填 ＋ 单次提交。
