"""
智能旅行助手 v2.0 LangGraph 编排层
将 v1.0 chat_service.py 的手写 Planning+ReAct 迁移为声明式 StateGraph。
新增冲突检测→回退重规划回路。
"""

from .graph_builder import build_graph, SmartTravelGraph

__all__ = ["build_graph", "SmartTravelGraph"]
