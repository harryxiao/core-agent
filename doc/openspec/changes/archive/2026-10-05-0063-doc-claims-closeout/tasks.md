# 任务：doc-claims-closeout（A6 + E13 + E19）

## 1. 规格判断（先行）

- [x] 1.1 逐条一手核实：A6 覆盖语义有意 / E13 规格该 Requirement 由 `LLMPlanner._parse` 实现 /
      E19 规格**无**该承诺（只在模块文档）
- [x] 1.2 判定为**规格中性**（三条都不改规格行为）→ `skip_specs: true`
- [x] 1.3 用户裁决落地：E19 = 订正文档承认现状（不实现环形缓冲 + 异步重试）

## 2. 文档订正

- [x] 2.1 `doc/03-interfaces/evolution-interface.md` §3.1：新增「重发布即重开窗」行（A6）
- [x] 2.2 `doc/03-interfaces/constraints-interface.md` §2：`parse_output` 无调用方 → **有意判定**（E13）
- [x] 2.3 `doc/02-modules/constraints.md` §3.1 + §5：输出解析的生产实现落在 `LLMPlanner._parse`
- [x] 2.4 `doc/04-testing/test-cases.md`：补 `TC-CONS-05`（规格→用例可达，指向既有测试）
- [x] 2.5 `doc/02-modules/durability.md` §5：删「环形缓冲 + 异步重试」承诺，写实际策略（E19）

## 3. 实现 / 测试

- [x] 3.1 **无**（纯文档：`src/` 与 `tests/` 零改动；追踪行只登记既有测试，不造重复用例）

## 4. 验证与收尾

- [x] 4.1 四门全绿（ruff / format / pyright / pytest —— 无代码改动，应为基线不变）
- [x] 4.2 `openspec validate 0063-doc-claims-closeout` → 手动归档 → `openspec validate --all`
- [x] 4.3 账本 A6 / E13 / E19 行标已关闭 + §2（A6）/ §3（E13 新段、E19 段）+ §9 步骤 9
- [x] 4.4 `coding-plan/README.md` 同步
- [x] 4.5 提交 `docs(architecture): 文档承诺订正与已知语义登记（A6/E13/E19，change 0063）`
