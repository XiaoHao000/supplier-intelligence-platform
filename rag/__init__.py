"""
SmartTravel RAG module

v2.0 新增：BGE-Reranker 两阶段检索增强
"""

from .reranker import BGEReranker

__all__ = ["BGEReranker"]
