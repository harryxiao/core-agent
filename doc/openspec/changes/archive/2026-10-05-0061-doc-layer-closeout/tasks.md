# 任务：doc-layer-closeout（E9）

## 1. 规格判断（先行）

- [x] 1.1 判定为**规格中性**（规格/接口/源码三者本就一致，只补登记层）→ `skip_specs: true`
- [x] 1.2 逐条一手核实 E9 四处：两处真缺口（本变更做）+ 两处改判归属（C 类 / D 类）

## 2. 文档回填

- [x] 2.1 `doc/01-architecture/data-model.md` §4：四实体按源码回填（含权威位置 + 字段）
- [x] 2.2 `doc/01-architecture/data-model.md` §3 第 5 行（Session）指向落地类型
- [x] 2.3 `doc/04-testing/test-cases.md`：TC-RAG-10 / TC-MCP-06 / TC-GIT-11 三条追踪行
- [x] 2.4 `doc/01-architecture/adr.md` ADR-0040 后果行：追加日期补记（不改历史正文）
- [x] 2.5 `doc/00-product/retrospective.md` §六.1：追加日期补记订正 `src = 0` 过时陈述

## 3. 实现 / 测试

- [x] 3.1 **无**（纯文档：`src/` 与 `tests/` 零改动；锚点测试早已存在，不造重复用例）

## 4. 验证与收尾

- [x] 4.1 四门全绿（ruff / format / pyright / pytest —— 无代码改动，应为基线不变）
- [x] 4.2 `openspec validate 0061-doc-layer-closeout` → 手动归档 → `openspec validate --all`
- [x] 4.3 账本 E9 行标已关闭 + §3 E9 段替换为已关闭块（含两处改判归属）+ §9 步骤 9
- [x] 4.4 `coding-plan/README.md` 同步
- [x] 4.5 提交 `docs(architecture): 文档层未闭合项收口（数据模型回填 + 替换性锚点登记，change 0061）`
