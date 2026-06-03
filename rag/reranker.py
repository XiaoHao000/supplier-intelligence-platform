"""
SmartTravel v2.0 RAG Reranker

在 Milvus ANN 粗筛后，使用 Cross-Encoder 精排，提升检索精度。
支持两种模式：
1. 本地模式（默认）：BGE-Reranker-v2-M3，首次运行自动下载模型
2. API 模式：通过环境变量 RERANKER_API_URL 配置远程 Reranker

设计要点：
    v1.0 使用单阶段 ANN 检索，精度有限。v2.0 升级为两阶段：
     粗筛（Milvus IVF_FLAT top-K）→ 精排（BGE-Reranker Cross-Encoder）。
     BGE-Reranker 计算 query 和每篇文档的交互分数，比向量余弦相似度
     更准确，因为 Cross-Encoder 同时看到 query 和 document 的完整上下文。

使用方式：
    from rag.reranker import BGEReranker
    reranker = BGEReranker()
    reranked = reranker.rerank("想看雪山的地方", candidates, top_n=5)
"""

import os
import logging

logger = logging.getLogger(__name__)


class BGEReranker:
    """
    BGE-Reranker 重排序器

    使用 BAAI/bge-reranker-v2-m3 进行 Cross-Encoder 精排。
    懒加载模式：首次调用 rerank() 时才加载模型，避免启动延迟。
    """

    def __init__(self, model_name: str = None, use_fp16: bool = True):
        """
        Args:
            model_name: 模型名称，默认 BAAI/bge-reranker-v2-m3
            use_fp16: 是否使用半精度（减少显存占用，CPU模式下自动忽略）
        """
        self.model_name = model_name or os.getenv(
            "RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"
        )
        self.use_fp16 = use_fp16
        self._model = None
        self._model_loaded = False

    def _lazy_load(self):
        """懒加载模型（首次调用时）"""
        if self._model_loaded:
            return

        try:
            from FlagEmbedding import FlagReranker
            logger.info(f"加载 BGE-Reranker 模型: {self.model_name}")

            # FlagReranker 自动检测设备（CUDA/CPU）
            self._model = FlagReranker(
                self.model_name,
                use_fp16=self.use_fp16
            )
            self._model_loaded = True
            logger.info(f"BGE-Reranker 加载完成: {self.model_name}")
        except ImportError:
            logger.warning(
                "FlagEmbedding 未安装，回退到无 Reranker 模式。"
                "安装方法：pip install FlagEmbedding>=1.3.0"
            )
            self._model = None
            self._model_loaded = True  # 标记已尝试加载，不再重试
        except Exception as e:
            logger.warning(f"BGE-Reranker 加载失败: {e}，回退到无 Reranker 模式")
            self._model = None
            self._model_loaded = True

    def rerank(
        self,
        query: str,
        candidates: list,
        top_n: int = 5,
        text_field: str = "highlights"
    ) -> list:
        """
        对候选文档进行 Cross-Encoder 重排序

        Args:
            query: 用户查询文本
            candidates: 候选文档列表，每篇文档为 dict，需包含 text_field 字段
            top_n: 返回 top-N 结果
            text_field: 文档中用于计算相关性分数的字段名

        Returns:
            list: 重排序后的文档列表（保持原有字段，新增 _rerank_score）

        降级策略：如果 Reranker 不可用，直接返回原始 candidates 的前 top_n 条
        """
        # 懒加载
        self._lazy_load()

        if not self._model or not candidates:
            # 降级：无 Reranker 或无候选，直接返回
            return candidates[:top_n]

        if len(candidates) <= top_n:
            # 候选数不超过 top_n，无需重排
            return candidates

        try:
            # 构建 query-document pairs
            pairs = []
            for doc in candidates:
                doc_text = doc.get(text_field, str(doc))
                pairs.append([query, doc_text])

            # Cross-Encoder 打分
            scores = self._model.compute_score(pairs, normalize=True)

            # 如果是单个分数（只有一对），包装为列表
            if isinstance(scores, float):
                scores = [scores]

            # 按分数降序排序
            scored_results = list(zip(candidates, scores))
            scored_results.sort(key=lambda x: x[1], reverse=True)

            # 取 top_n，附加分数
            reranked = []
            for doc, score in scored_results[:top_n]:
                doc["_rerank_score"] = round(float(score), 4)
                reranked.append(doc)

            logger.info(
                f"Reranker: {len(candidates)} candidates → {len(reranked)} results "
                f"(top score: {reranked[0]['_rerank_score'] if reranked else 'N/A'})"
            )

            return reranked

        except Exception as e:
            logger.warning(f"Reranker 重排序失败: {e}，回退到原始排序")
            return candidates[:top_n]

    @property
    def is_available(self) -> bool:
        """检查 Reranker 是否可用"""
        self._lazy_load()
        return self._model is not None
