"""内部核心模块的**归因白名单**（evolution）。

`INTERNAL_PLUGIN_IDS` 是仓内 14 个内部核心模块的 `plugin_id` 集合，供 `Proposer` 判定
「诊断归因到的对象是**架构模块**还是**工具/外部能力**」——命中的候选 SHALL 为架构级
（`kind="plugin"`、`risk_level="high"`，强制人工审批），否则为技能库级。

**这不是 `PluginRegistry` 的成员名单**：此处只声明**归因对象身份**（供进化引擎监控该模块、
定位其缺陷），**不蕴含**该模块已纳入注册表生命周期；模块自身的失败证据经**模块归因遥测通道**
（`TraceEvent.module_id`）承载（规格见 evolution「经验采集」）。

**裁决（change `0107`）：内部核心模块不纳入 `PluginRegistry`、不补 `load`/`unload` 空转形态。**
依据（一手核实）：①全仓仅 `PluginInstaller` 内部默认构造注册表，无消费方 ⇒ 注册进去无代码路径
读取；②14 个模块里仅 8 个有 Plugin 六件套，其 `load`/`unload` 全 `return None`、`check()` 7/8
恒真（真检查仅 `evolution.engine` / `composition.resolver`）⇒ 补全后仍无信号、无行为
（ADR-0094 决策①已否决）。**重开条件**：出现「真的会产出新一代 `Plugin` 对象」的生产者
（模型生成 / 人工提交补丁）—— 届时 `promote(plugin: Plugin)` 才有语义；change `0102` 把架构级
结晶裁决为 `accepted`（待人工实施）= 系统自认短期内没有该生产者。
裁决与重开条件同步记于 `coding-plan/phase-19.md` §5 / `phase-21.md` §1.4。

命名空间说明：`Trace.plugin_id` 是**归因对象 id**，两套命名空间（工具 id `tools.*` 与
内部核心模块 id）**互不相交**。新增内部核心模块（实现 `plugin_id` 的类）须同步登记 ——
有逐元素一致性用例守护（`tests/test_evolution_attribution.py`）。
"""

from __future__ import annotations

CORE_ROOT = "src/core"  # 内部核心模块源码根（与范围守卫的校验形态同一口径）


def module_path(plugin_id: str) -> str:
    """归因目标 id ⇒ 其源码文件（仓内相对路径）：`a.b` → `src/core/a/b.py`。

    归因白名单是「id ↔ 模块」知识的**唯一**居所，故该约定与名单同处一文件。约定不得漂移：
    原生执行的**路径与归因一致**校验与范围守卫都建立在它之上；14 个 id 如实命中真实文件，
    另有派生不变量用例守护（`tests/test_evolution_author.py`）。
    """
    return f"{CORE_ROOT}/{plugin_id.replace('.', '/')}.py"


INTERNAL_PLUGIN_IDS: frozenset[str] = frozenset(
    {
        "composition.engine",
        "composition.packager",
        "composition.resolver",
        "evolution.collector",
        "evolution.diagnoser",
        "evolution.engine",
        "evolution.evaluator",
        "evolution.proposer",
        "evolution.validator",
        "evolution.worker",
        "im.gateway",
        "loop.default",
        "memory.store",
        "notes.store",
    }
)
