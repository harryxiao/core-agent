# Design 0216 — 关键事实抽取门控

## 1. 缺口定位（P3）

`runtime.py:578` 的 `key_fact_extractor=extract_with(_llm_text)` **无条件**；同族 `relation_extract`
（`:581`）、`importance_gate`（`:584`）皆门控 ⇒ **不对称**。关键事实抽取每次压实跑一次模型，
却无关闭手段。

## 2. 设计

### 2.1 缺省 True（kill-switch 而非 opt-in）

| 选择 | 后果 | 判定 |
|---|---|---|
| 缺省 **True**（本设计） | 缺省恒走原分支 ⇒ **与今日逐字等价**；显式 false 才关 | ✅ |
| 缺省 False | `0155` 以来**无条件在用**的能力**默认消失** ⇒ 静默能力删除 | ❌ 非缺陷修复，违反纪律初衷 |

「缺省关 ⇒ 逐字不变」纪律保护的是**既有行为不被新特性改变**；一个既有能力的**开关**若默认关，
等于让能力**默认消失**，方向相反。故本键缺省 **True**。

### 2.2 非法取值回落 **True**（与同段其余键相反）

`memory` 段**非结构化**（`_STRUCTURED_SECTIONS` 不含 `memory`）⇒ 非法取值**不阻断启动**，
只被归一。同段 `relation_extract`/`importance_gate` 归一方向是**关闭**（方向恒为「不做那件事」，
安全侧）；本键方向**恒为「保持能力」**⇒ 归一为**开启**（`not in _FEATURE_FALSE`）——
**一个拼写错误不得静默停用在用能力**。

### 2.3 规格：MODIFIED 末句 ＋ ADD Scenario ×2

- 末句：「未注入抽取器（缺省）⇒ SHALL NOT 抽取 …」⇒
  「未注入抽取器**或配置关闭**（`memory.key_fact_extract` = false）⇒ SHALL NOT 抽取 …」＋
  新键 SHALL 为**组合根接线闸**、缺省 **true**、只决定**是否接线**、SHALL NOT 改本条其余判据。
- ADD `#### Scenario: 配置关闭 ⇒ 不接线、压实逐字不变` / `#### Scenario: 门控缺省开 ⇒ 保留既有抽取`。
- **既有 15 Scenario 逐字保留**（MODIFIED = 整段替换，须原样带上）⇒ 归档断言 0 Scenario-title 丢失。

## 3. 测试（`tests/test_key_fact_gate.py`，8 用例）

三面声明 / 缺省 on / yaml 关（＋ 非「未知段」）/ env 关 / 非法值回落 on / 组合根两态接线 /
**逐字锚**（门只切抽取：关与开的**摘要产物逐字相同**，差只在有无 `keyfact.*`）。

## 4. 反证（实测）

| # | 回退手法 | 实测 |
|---|---|---|
| A | `runtime.py:578` 恢复无条件接线 | **1 红**（`test_build_runtime_omits_extractor_when_disabled`） |
| B | ConfigSpec `default` ＋ 访问器缺省 ＋ `raw.get` 缺省 一并翻 False | **3 红**（`test_spec_declares_key_fact_extract` / `test_default_is_on` / `test_build_runtime_default_wires_extractor`） |

两次复原 ⇒ `src/core/configuration/manager.py` / `src/core/runtime.py` **`diff -q` 逐字节相同**，复测 8 绿。

## 5. 规格落点

`doc/openspec/specs/memory/spec.md`：**MODIFIED**「结构化实体抽取（关键事实）」（整段替换，含 15 既有
Scenario 逐字 ＋ 末句扩写）＋ 2 新 Scenario ⇒ canonical memory **16 req 不变** / scen **+2**。
