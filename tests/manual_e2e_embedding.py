"""手工冒烟：记忆语义检索（0040）走**真实端点**——不在 CI（需网络 + 密钥）。

仓库测试全离线，本脚本因此不命名为 `test_*`（pytest 不收集），仅供改动记忆检索 /
embedding 装配后手工复跑。三组对照：

- A `embedder=None`（0039 前的生产形态，纯词法）
- B `--embedding-model <model>`（远端向量 → 语义检索生效）
- C `--embedding-model <不存在的模型>`（真实不可达 → 应降级且不阻断启动）

A/B 顺序应不同（语义改变了排序），B 的首条应为语义最相关条目，C 应与 A 一致且
`_embed_failed` 为 True。

用法::

    .venv/bin/python tests/manual_e2e_embedding.py --config config.yaml
        --embedding-model embedding-3
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.configuration import ConfigManager  # noqa: E402 — 先补 sys.path 再 import src
from core.memory import MemoryEntry  # noqa: E402
from core.memory.relevance import _similarity, tokens  # noqa: E402, PLC2701 — 冒烟直取原始证据
from core.runtime import build_runtime  # noqa: E402

_QUERY = "怎么装第三方包"
_ENTRIES = [
    ("e1", "部署时依赖统一用 uv 管理，跑测试前先 uv sync 同步环境"),
    ("e2", "用户偏好简洁直接的回复，不要冗长铺垫"),
    ("e3", "代码评审关注可逆性与副作用追踪"),
]


def _read_order(config: str, embedding_model: str | None) -> tuple[list[str], bool, list[float]]:
    """装配一次 runtime、写入固定条目、读回；返回（顺序, embed_failed, query 词法相似度）。"""
    os.environ["CORE_STATE_DIR"] = tempfile.mkdtemp(prefix="e2e-state-")
    cli = {"llm.embedding_model": embedding_model} if embedding_model else {}
    runtime = build_runtime(ConfigManager(config, cli=cli))
    for entry_id, content in _ENTRIES:
        runtime.memory.write(
            "L2",
            MemoryEntry(
                id=entry_id,
                layer="L2",
                content=content,
                tags=[],
                source="manual-e2e",
                trace_id=f"manual-e2e:{entry_id}",
            ),
        )
    order = [hit.id for hit in runtime.memory.read(_QUERY, budget=4096)]
    embedder = runtime.memory._embedder
    sims = [
        _similarity(
            MemoryEntry(id=i, layer="L2", content=c, tags=[], source="s", trace_id="t"),
            _QUERY,
            embedder,
        )
        for i, c in _ENTRIES
    ]
    return order, runtime.memory._embed_failed, sims


def main() -> int:
    parser = argparse.ArgumentParser(description="记忆语义检索真端点冒烟（0040）")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--embedding-model", default="embedding-3")
    args = parser.parse_args()

    print(f"query={_QUERY!r}  tokens={sorted(tokens(_QUERY))}")
    order_a, failed_a, sims_a = _read_order(args.config, None)
    print(f"A 无 embedder        : {order_a}  embed_failed={failed_a}")
    order_b, failed_b, sims_b = _read_order(args.config, args.embedding_model)
    print(f"B {args.embedding_model:<18}: {order_b}  embed_failed={failed_b}")
    order_c, failed_c, _ = _read_order(args.config, "no-such-embedding-model")
    print(f"C 不存在的模型       : {order_c}  embed_failed={failed_c}")
    print(f"\nquery 相似度 A={[round(s, 3) for s in sims_a]}  (词法，多为 0)")
    print(f"query 相似度 B={[round(s, 4) for s in sims_b]}  (余弦)")

    ok = (
        order_b[0] == "e1"  # 语义最相关条目居首
        and order_b != order_a  # 语义确实改变了排序（非词法偶然命中）
        and not failed_b  # 远端向量成功
        and order_c == order_a  # 不可达退化为词法，结果与 A 一致
        and failed_c  # 且已短路标记
    )
    print("\nVERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


raise SystemExit(main())
