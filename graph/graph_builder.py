"""
智能旅行助手 v2.0 StateGraph 构建器

将 v1.0 chat_service.py 的手写编排迁移为声明式 LangGraph StateGraph。

图结构：
  intent_node → slot_check_node → [ask_user_node | planning_node | dispatch_node]
                                                                    ↓
                                                              guide_node（可选）
                                                                    ↓
                                                               dispatch_node
                                                                    ↓
                                                          [Send] agent_node × N
                                                                    ↓
                                                            conflict_check_node
                                                           ↙          ↘
                                              guide_node (回退)    summarize_node (END)
                                              (retry < max)

v1.0 vs v2.0 对比：
  旧架构：手写 if-else + while 循环 + OrderedDict 依赖组 + asyncio.gather
  新架构：声明式 StateGraph + Send API + 条件边 + 回退回路
"""

import os
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import AgentState
from graph.nodes import (
    intent_node,
    slot_check_node,
    ask_user_node,
    planning_node,
    guide_node,
    dispatch_node,
    agent_node,
    conflict_check_node,
    summarize_node,
    inject_dependencies,
)
from config import Config
from create_logger import logger

conf = Config()


# ==================== 条件路由函数 ====================

def route_after_slot_check(state: AgentState) -> Literal["ask_user", "planning", "dispatch"]:
    """
    槽位检查后的路由：
    - 槽位不完整 → 追问用户
    - 槽位完整 + 含 guide/order 意图 → 需要规划
    - 槽位完整 + 简单意图 → 直接分发
    """
    if not state.get("slots_complete", False):
        return "ask_user"

    intents = state.get("intents", [])

    # 含 guide 或超过2个意图 → 需要规划
    needs_plan_intents = {"guide"}
    if any(i in needs_plan_intents for i in intents) or len(intents) > 2:
        return "planning"

    return "dispatch"


def route_after_planning(state: AgentState) -> Literal["guide", "dispatch"]:
    """
    规划后的路由：
    - 需要生成推荐方案 → guide_node 先执行
    - 不需要推荐 → 直接分发
    """
    intents = state.get("intents", [])
    if "guide" in intents:
        return "guide"
    return "dispatch"


def route_after_conflict(state: AgentState) -> Literal["guide", "summarize"]:
    """
    冲突检测后的路由：
    - 有冲突且未超过重试上限 → 回退到 guide_node 重新规划
    - 无冲突或超过重试上限 → 汇总输出
    """
    conflicts = state.get("conflicts", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if conflicts and retry_count < max_retries:
        logger.info(f"[route_after_conflict] 回退重规划: retry={retry_count}/{max_retries}, "
                     f"conflicts={len(conflicts)}")
        return "guide"

    if conflicts:
        logger.warning(f"[route_after_conflict] 超过最大重试次数({max_retries})，妥协汇总")

    return "summarize"


# ==================== Graph 构建 ====================

class SmartTravelGraph:
    """
    智能旅行助手 v2.0 LangGraph 编排器

    使用方式：
        graph_app = SmartTravelGraph(agent_network, memory).compile()
        result = await graph_app.ainvoke({"user_input": "成都的天气和票务情况"})
        # 或流式
        async for event in graph_app.astream({"user_input": "..."}):
            ...
    """

    def __init__(self, agent_network=None, memory=None):
        """
        初始化图构建器

        Args:
            agent_network: python-a2a AgentNetwork 实例
            memory: ConversationMemory 实例
        """
        self.agent_network = agent_network
        self.memory = memory

        # 注入依赖到 nodes 模块
        inject_dependencies(agent_network, memory)

        self._graph = None

    def build(self) -> StateGraph:
        """构建 StateGraph（不含 checkpointer）"""
        builder = StateGraph(AgentState)

        # ========== 注册节点 ==========
        builder.add_node("intent", intent_node)
        builder.add_node("slot_check", slot_check_node)
        builder.add_node("ask_user", ask_user_node)
        builder.add_node("planning", planning_node)
        builder.add_node("guide", guide_node)
        builder.add_node("dispatch", dispatch_node)
        builder.add_node("agent", agent_node)
        builder.add_node("conflict_check", conflict_check_node)
        builder.add_node("summarize", summarize_node)

        # ========== 设置入口 ==========
        builder.set_entry_point("intent")

        # ========== 添加边 ==========

        # intent → slot_check（直接边）
        builder.add_edge("intent", "slot_check")

        # slot_check → 条件路由
        builder.add_conditional_edges(
            "slot_check",
            route_after_slot_check,
            {
                "ask_user": "ask_user",
                "planning": "planning",
                "dispatch": "dispatch",
            }
        )

        # ask_user → END
        builder.add_edge("ask_user", END)

        # planning → 条件路由
        builder.add_conditional_edges(
            "planning",
            route_after_planning,
            {
                "guide": "guide",
                "dispatch": "dispatch",
            }
        )

        # guide → dispatch
        builder.add_edge("guide", "dispatch")

        # dispatch → agent_node（Send API 自动处理 fan-out）
        # dispatch 返回 Send[] 时，LangGraph 自动并行执行 agent_node
        # 所有 agent_node 执行完毕后，自动进入 conflict_check

        # dispatch → conflict_check
        builder.add_edge("dispatch", "conflict_check")

        # conflict_check → 条件路由（含回退边）
        builder.add_conditional_edges(
            "conflict_check",
            route_after_conflict,
            {
                "guide": "guide",      # 回退重规划！
                "summarize": "summarize",
            }
        )

        # summarize → END
        builder.add_edge("summarize", END)

        self._graph = builder
        return builder

    def compile(self, checkpointer=None):
        """
        编译图（可选传入 checkpointer）

        Args:
            checkpointer: LangGraph checkpointer，默认 MemorySaver
        """
        if self._graph is None:
            self.build()

        if checkpointer is None:
            checkpointer = MemorySaver()

        return self._graph.compile(checkpointer=checkpointer)


# ==================== 便捷函数 ====================

def build_graph(agent_network=None, memory=None) -> SmartTravelGraph:
    """
    构建 SmartTravel LangGraph 编排器

    外部调用入口：
        graph = build_graph(agent_network, memory)
        app = graph.compile()
        result = await app.ainvoke({"user_input": "成都的天气怎么样？"})
    """
    return SmartTravelGraph(agent_network, memory)
