"""二十神兽名册（beast-registry，数据层）。

20 个预定义山海经神兽，内置只读（区别于 pet.md 用户自定义角色）：
``agent_id = beast.<拼音>`` 唯一标识，含称号、领域职责、独有神通与能力标签。
注册表无写入口，运行期不可增改。

对应规格：doc/openspec/specs/beast-mode/spec.md（Beast Registry）
"""

from __future__ import annotations

from .models import Beast

# (agent_id, 称号, 领域职责, 独有神通 skill_id, 能力标签关键词[空格分隔])
_BEAST_ROSTER: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "beast.baize",
        "白泽",
        "知识通晓 / 跨域检索与信息整合",
        "beast.baize.omniscience",
        "知识 检索 整合",
    ),
    (
        "beast.qinglong",
        "青龙",
        "架构设计 / 蓝图与骨架生成",
        "beast.qinglong.blueprint",
        "架构 蓝图 骨架",
    ),
    ("beast.baihu", "白虎", "性能攻坚 / 剖析与瓶颈定位", "beast.baihu.profile", "性能 剖析 瓶颈"),
    ("beast.zhuque", "朱雀", "重构 / 涅槃式重写", "beast.zhuque.rebirth", "重构 重写"),
    ("beast.xuanwu", "玄武", "安全防御 / 审计与加固", "beast.xuanwu.audit", "安全 审计 加固"),
    ("beast.qilin", "麒麟", "质量保障 / 测试生成", "beast.qilin.testgen", "质量 测试"),
    (
        "beast.yinglong",
        "应龙",
        "部署运维 / 发布与 CI/CD",
        "beast.yinglong.deploy",
        "部署 运维 发布",
    ),
    (
        "beast.zhulong",
        "烛龙",
        "调度 / 定时与长期驻留任务",
        "beast.zhulong.schedule",
        "调度 定时 驻留",
    ),
    (
        "beast.jiuweihu",
        "九尾狐",
        "前端交互 / UI 生成与体验",
        "beast.jiuweihu.uigen",
        "前端 UI 交互",
    ),
    ("beast.jingwei", "精卫", "长任务 / 执着重试直至完成", "beast.jingwei.persist", "长任务 重试"),
    (
        "beast.xingtian",
        "刑天",
        "故障恢复 / 无畏式故障自愈",
        "beast.xingtian.fearless",
        "故障 恢复 自愈",
    ),
    (
        "beast.taotie",
        "饕餮",
        "大数据 / 批量吞吐与吞噬式处理",
        "beast.taotie.bulk",
        "大数据 批量 吞吐",
    ),
    ("beast.qiongqi", "穷奇", "代码评审 / 善恶判别", "beast.qiongqi.review", "评审 代码"),
    ("beast.taowu", "梼杌", "混沌工程 / 破坏性注入测试", "beast.taowu.chaos", "混沌工程 注入 破坏"),
    ("beast.hundun", "混沌", "模糊测试 / 随机输入探索", "beast.hundun.fuzz", "模糊测试 随机"),
    (
        "beast.yingzhao",
        "英招",
        "项目管理 / 任务编排与统筹",
        "beast.yingzhao.orchestrate",
        "项目管理 编排 统筹",
    ),
    ("beast.luwu", "陆吾", "多模块协调 / 网关与集成", "beast.luwu.gateway", "协调 网关 集成"),
    (
        "beast.tiangou",
        "天狗",
        "依赖迁移 / 版本升级与兼容",
        "beast.tiangou.migrate",
        "迁移 升级 依赖",
    ),
    ("beast.jiufeng", "九凤", "并发 / 并行执行加速", "beast.jiufeng.parallel", "并发 并行"),
    ("beast.pixiu", "貔貅", "资源优化 / 清理与回收", "beast.pixiu.reclaim", "资源 清理 回收"),
)


class BeastRegistry:
    """二十神兽只读注册表：按 agent_id 索引，别名解析，无写入口。"""

    def __init__(self) -> None:
        self._beasts: tuple[Beast, ...] = tuple(
            Beast(
                agent_id=a,
                title=t,
                domain=d,
                innate_skill=s,
                capabilities=(t, *k.split()),
            )
            for a, t, d, s, k in _BEAST_ROSTER
        )
        self._by_id: dict[str, Beast] = {b.agent_id: b for b in self._beasts}

    def lookup(self, agent_id: str) -> Beast | None:
        """按 ``beast.<拼音>`` 精确取兽。"""
        return self._by_id.get(agent_id)

    def resolve(self, name: str) -> Beast | None:
        """按 agent_id / 称号 / 拼音别名解析神兽；未命中返回 None。"""
        if name in self._by_id:
            return self._by_id[name]
        for beast in self._beasts:
            if beast.title == name or beast.agent_id.rsplit(".", 1)[-1] == name:
                return beast
        return None

    def all(self) -> tuple[Beast, ...]:
        """全部内置神兽（只读）。"""
        return self._beasts

    def agent_ids(self) -> tuple[str, ...]:
        """全部 agent_id。"""
        return tuple(b.agent_id for b in self._beasts)
