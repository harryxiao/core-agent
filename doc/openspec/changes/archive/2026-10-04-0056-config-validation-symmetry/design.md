# Design — config-validation-symmetry

## 决策 1：E7 的裁决依据是「规格 vs 实现」的层级，不是「谁更新」

`cli-contract-baseline.md` 与规格冲突时，**规格赢**：它是 `doc/openspec/specs/` 下的规范文件，而基线是
Phase 早期 `temp/plan_cli_ops/*` 推演的**中间产出**（文件自附溯源清单）。三点实证支持「5 个名字从未存在」：
① `src/` 零出现；② `doc/openspec/specs/` 零出现；③ 那 5 个名字（`web_scan`/`web_execute_js`/`ask_user`/
`process`/`memory`）是**另一类 agent 框架的工具词表**，与本仓「9 个可逆原子插件」的定位不符。
**已否决**「仍按承诺项补实现」：那等于让一份过时的推演稿反向定义产品范围。

## 决策 2：三处校验缺口同批修，但只修「规格已承诺」的那些

`im.secret` 空值、`judgment.api_key` 不可解析、`permission.mode` 非法取值，三者性质一致：
**规格已经要求、实现没做**（前两者是「配置校验通过才生效」+「密钥分级与安全」的直接推论；
后者是 permission 规格白纸黑字的「映射 `config.permission.mode`」四档）。
「规格已承诺而实现未做」是 E 类缺口的定义，修它们不需要新决策。

## 决策 3：`extra` 的宽松性**不**顺手收紧（用户裁决 B）

`extra: dict[str, Any]`（`models.py:82`）是「除五类结构化段之外的一切」的兜底，`permission.mode` 正寄居其中。
把它改成白名单式校验会**拒绝用户写在配置里的自定义段名**——这是**改变既有接受行为**的一刀，
可能让正在跑的部署无法启动。用户在三档中选定 **B（对称化）**：修「规格已承诺」的三处、
`extra` 的未知键**另立后续行**（需先定夺是否要「未知键仅告警」还是「硬拒」）。**已否决** C（同批收紧）。

## 决策 4：`_PERMISSION_MODES` 落在 configuration 侧，取值口径引用 permission 规格

四档词表的**定义方**是 permission 规格（`doc/openspec/specs/permission/spec.md`「权限模式」），
但**校验点**在 configuration 的 `validate_schema`。故在 `manager.py` 内建一个私有常量并在注释中指明
「口径来源：permission 规格四档」——不 import permission（配置层不应依赖能力层，符合分层红线）。
代价：词表有**两处字面量**（配置校验 + 权限规格文档）。可接受：若将来加第五档，两处都要动，
但这正是「规格定义、配置强制」的正常成本；引入跨层常量反而破坏分层。

## 决策 5：校验用 `elif` 链，避免同一引用报两条错

现有实现里「明文密钥」检查与「可解析」检查若各自独立 `if`，一个明文 `im.secret` 会同时报
「必须为 ${VAR} 引用」与「引用无法解析」两条——后者是前者的噪音。故三处引用统一为
`明文 → 空 → 不可解析` 的 `elif` 链（LLM 分支保持既有形状不动，仅补 IM / judgment）。

## 决策 6：可选段的参与条件写明

IM 段缺失 = 不校验（规格「IM 可选不配置」已如此）；judgment 段**仅在 `provider` 非空**时校验
（规格「未配置 judgment 段或 provider 为空 → 决策能力关闭」）。若不设此条件，一个只写
`judgment: {base_url: ...}` 的惰性段会被误判为缺密钥。

---

## 接受的风险

- **校验变严**：既有「IM 段 + 空 secret」或「非法 permission.mode」的配置会启动失败。已核对仓内
  测试与示例配置**无此形态**（无既有用例依赖宽松行为）；对仓外用户是**行为变更**，故记入 proposal Impact。
- **词表双写**（决策 4）。
- **`extra` 未知键仍静默接受**：转出后续行，非本变更不修。
