# design — 0085 `features` 段未知模块名告警

## 决策 1：归属 —— 注入，而非配置层自持（用户裁决 ①）

**问题**：校验 `features` 子键需要一个**已知模块名集合**，该集合今天在组合根
（`runtime.GATABLE_MODULES`，change 0067 / 账本 E10，ADR-0065 明文「**本元组是单一真源，
configuration 层不认识模块名**」）。

**三选一**：

| 方案 | 做法 | 判定 |
|---|---|---|
| ① **注入**（本变更） | `ConfigManager(known_modules=GATABLE_MODULES)`，配置层**代其校验** | ✅ 归属不变（runtime 拥有，注入给校验）；同既有 `specs=` 惯用法；不碰 ADR-0065 |
| ② 配置层声明 | `configuration.KNOWN_FEATURE_MODULES` + `runtime.GATABLE_MODULES = 引用` | ❌ 推翻 ADR-0065「配置层不认识模块名」措辞（虽零调用点改动） |
| ③ 拼写近似 | 只对近似已知名（编辑距离）告警 | ❌ 引入编辑距离 + 阈值常量，与既有「白名单派生」风格不一致 |

**选 ①**：子键 schema 义务归**拥有集合的那层**（组合根），配置层**代其校验**。依赖方向仍合法
（`entry → runtime` 已有 import；`runtime → configuration` 已有 import；传元组无环）。

## 决策 2：仅告警，不阻断

与 E18（未知配置段**仅告警**，change 0064）同口径。理由：
- **模块名是开放集合** —— `is_enabled` 谓词（change 0067）供缺省关的模块自查**二级开关**，
  即 `features.<任意名>` 都可能合法。硬拒会拒绝合法新键（改变既有接受行为，与 E18 拒绝理由同）。
- 拼错的风险是**静默 no-op**，一条**可忽略**的告警足以暴露，无需阻断。

## 决策 3：缺省不校验（向后兼容）

`known_modules=None`（缺省）⇒ `_unknown_feature_warnings` 返回 `[]`，**不告警**。理由：
- 既有 `ConfigManager(...)` 构造面（10 处 CLI + 大量测试）**不破** ——
  测试夹具 `_VALID_YAML` 含 `features: voice_output: false` 等自定义键，注入后不应告警。
- 「谁注入谁负责」：只有组合根/CLI 主路径主动注入，测试与临时构造按需。

## 决策 4：入口单点注入（`_config_manager` helper）

`entry.py` 有 **10 处** `ConfigManager(yaml_path=..., cli=...)` 构造点（形态各异：`args.config` /
自定义 `path` / 预置 `cli`）。逐处加 `known_modules=` 会散落且漏传风险高（漏一处 ⇒ 该入口静默丢失告警）。

**收成单点 helper** `_config_manager(args, *, yaml_path=None)`：唯一注入 `GATABLE_MODULES` 的构造处。
`yaml_path=None` 缺省取 `args.config`（覆盖 `config validate --file` 的自定义路径）。

## 决策 5：告警文案与作用域

告警形如：
```
未知功能开关: features.peet（不在已知模块名 beast, evolution, pet 之内；若为拼写错误请订正 —— 模块名拼错将静默不生效）
```
- 含**键名**（可定位）+ **已知模块名清单**（可对照）+ **后果提示**（静默 no-op）。
- **作用域严格限 `features` 段**：`llm.typo_key` 等其它已知段的未知子键**不告警**（各能力 schema 义务，非本项）。

## 风险与已否决

- **风险**：配置层短暂「知道」了模块名（经注入）。**缓解**：集合不落配置层代码、
  不作创建时默认值；`GATABLE_MODULES` 仍是唯一真源，配置层只是**消费注入**。
- **已否决**：把 `features` 子键校验做成通用「段内子键 schema」机制 —— 无第二消费者（YAGNI），
  且其它段的子键语义确实不归配置层。
