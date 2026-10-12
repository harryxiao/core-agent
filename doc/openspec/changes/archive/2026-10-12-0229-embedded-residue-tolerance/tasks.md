# 0229 tasks — 形态 5 判据收窄

1. **Specification** — `loop` MODIFIED「推理动作解析与失败可见」（形态 2 容残渣 ＋ 形态 5 要求含词元
   ＋ ADDED 2 Scenario，既有 16 Scenario 逐字保留）→ verify: `openspec validate 2026-10-12-0229-embedded-residue-tolerance` 绿。
2. **Tests（红先行）** — `tests/test_loop_output_protocol.py` 增 5 用例：
   - 事故复刻：完整动作 JSON + 一个多余 `}` ⇒ **工具动作**、`failed=False`、无 `raw_output`；
   - 围栏 / 零散标点残渣 ⇒ 同样执行；
   - 「正文 + 动作 JSON + 残渣」⇒ 执行（D3 锚）；
   - 「正文 + 动作 JSON + **纯标点**残渣」⇒ 仍执行（D3 去门槛锚）；
   - 「完整动作 JSON + **含词元**正文」⇒ 仍失败（形态 5 边界锚）。
   → verify: 前四条**全红**（`_has_word` 未实现 / 判据未收窄）、第五条**恒绿**（守护锚）。
3. **Implementation** — `src/core/loop/planner.py`：新 `_has_word`；新 `_leading_object`；
   `_trailing_json_object` 余部改成「无词元」**并去掉「须以 `}` 收尾」前置门槛**；
   `_embedded_action_payload` 余部改成「有词元」；`_parse` `{` 开头分支先试「首个对象 + 残渣」。
   → verify: 五条转绿、`tests/test_loop_output_protocol.py` 全绿（含 0222 / 0227 旧锚）。
4. **Interface Doc** — `doc/03-interfaces/loop-interface.md`「原始产出可诊断」条目补残渣容差一句。
5. **Gates & Archive** — 四门禁（`ruff check` / `ruff format --check` / `pyright` **无参** / `pytest -q`）
   → 反证三组（D1 恒 `True` / D3 只改一半 / 复原 md5 同）→ `openspec validate --all`
   → 手工归档（断言 0 Requirement / 0 Scenario 标题丢失）→ 台账（`known-risk.md` §1 E166 ＋ §3
   ADR-0219 行、`test-cases.md` §142、`adr.md` ADR-0219 ＋ 变更追踪）→ **单次提交**。
