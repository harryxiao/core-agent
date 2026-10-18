"""已知端点 → 默认 embedding 模型表（change 0271 / ADR-0261）。

``llm.embedding_model`` 未配置时，记忆 / RAG 的语义检索此前**恒**不启用 —— 要求用户知道并
手写一个与聊天模型无关的模型名。本模块给出**小而有据**的端点表，供
``LLMConfig.effective_embedding_model`` 在未显式配置时推导，使已知端点开箱获得语义召回。

纪律（规格「LLM 提供商配置（必选）」）：

- 只收录**有据可查**、提供 OpenAI 兼容 ``/embeddings`` 的端点，**不猜测**未收录端点
  （``default_embedding_model`` 返回空 = 不知道）；
- 表**不引入配置键**（无 CLI / env / yaml 面），故**不是**第二真源；
- 显式 ``llm.embedding_model`` 永远**优先**于本表（用户显式声明胜出）。
"""

from __future__ import annotations

from urllib.parse import urlsplit

# 「端点主机 → 默认 embedding 模型」表。按主机名**精确或子域**匹配（大小写不敏感）。
_KNOWN_EMBEDDING_MODELS: tuple[tuple[str, str], ...] = (
    ("api.openai.com", "text-embedding-3-small"),  # OpenAI Embeddings API 公开模型名
    ("open.bigmodel.cn", "embedding-3"),  # 智谱开放平台 Embedding-3
    ("dashscope.aliyuncs.com", "text-embedding-v3"),  # 阿里云百炼文本向量模型
    ("api.siliconflow.cn", "BAAI/bge-m3"),  # SiliconFlow 模型广场
)


def _host(endpoint: str) -> str:
    """从 endpoint 提取小写主机名；无 scheme / 非法 URL ⇒ 尽力解析，失败返回空串。"""
    text = endpoint.strip()
    if not text:
        return ""
    if "://" not in text:
        text = "//" + text  # 允许 `api.openai.com/v1` 这类省略 scheme 的写法
    try:
        return (urlsplit(text).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def default_embedding_model(endpoint: str) -> str:
    """按端点主机推导默认 embedding 模型；未命中 ⇒ ``""``（不猜）。"""
    host = _host(endpoint)
    if not host:
        return ""
    for domain, model in _KNOWN_EMBEDDING_MODELS:
        if host == domain or host.endswith("." + domain):
            return model
    return ""
