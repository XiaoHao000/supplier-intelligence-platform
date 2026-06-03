"""
智能旅行助手 v2.0 AgentState 定义

对比 v1.0 chat_service.py 状态散落在 self.messages / self.memory / 局部变量中，
v2.0 将所有编排状态集中到一个 TypedDict，由 LangGraph 自动管理。
"""

from typing import TypedDict, Annotated, Sequence, Optional
from operator import add
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer：合并两个字典（后值覆盖前值），用于并行 agent_node 结果收集"""
    return {**a, **b}


def _merge_lists(a: list, b: list) -> list:
    """Reducer：拼接两个列表，用于并行 agent_node 执行顺序收集"""
    return a + b


class AgentState(TypedDict):
    """
    智能旅行助手 编排状态

    字段分组：
    - 对话层：用户输入 + 多轮消息
    - 意图层：识别结果 + 槽位完整性
    - 规划层：是否需要多步计划 + 步骤列表
    - 执行层：各 Agent 返回结果 + 执行顺序
    - 冲突层（v2.0 新增）：冲突列表 + 回退计数
    - 输出层：最终回复 + 完成标记
    """

    # ==================== 对话层 ====================
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # LangGraph 标准消息列表，add_messages 自动合并新消息

    user_input: str
    # 用户最新输入，各节点从这里读取

    conversation_history: str
    # 格式化的对话历史字符串，注入到 LLM prompt 中

    # ==================== 意图层 ====================
    intents: list
    # 识别到的意图列表，如 ["weather", "flight", "guide"]

    user_queries: dict
    # 改写后的查询字典，如 {"weather": "北京明天天气", "flight": "北京到上海机票"}

    follow_up_message: str
    # 追问消息（意图不明或需要确认时）

    slots_complete: bool
    # 槽位是否完整（v2.0 新增：显式槽位检查，替代 v1 的隐式检查）

    missing_slots: list
    # 缺失的槽位列表，如 ["departure_city", "date"]

    # ==================== 规划层 ====================
    need_plan: bool
    # 是否需要多步规划（由 planning_node 或启发式路由决定）

    plan_steps: list
    # 规划步骤列表，如 [{"step": 1, "action": "查攻略", "intent": "guide", "depends_on": 0}, ...]

    # ==================== 执行层 ====================
    agent_results: Annotated[dict, _merge_dicts]
    # 各 Agent 执行结果，如 {"weather": "北京明天晴 25°C", "flight": "CA1401 780元"}
    # 使用 _merge_dicts reducer 确保并行 agent_node 的结果被合并而非覆盖

    execution_order: Annotated[list, _merge_lists]
    # Agent 执行顺序记录，用于调试和 Tracing
    # 使用 _merge_lists reducer 确保并行执行顺序被追加而非覆盖

    # ==================== 冲突层（v2.0 新增） ====================
    conflicts: list
    # 检测到的冲突列表，格式：
    # [{"source_agent": "guide", "target_agent": "ticket",
    #   "description": "攻略推荐5月1日CA1401航班，但票务显示该航班已售罄",
    #   "suggestion": "调整为5月2日出发或换航班", "severity": "high"}]

    retry_count: int
    # 当前回退重试次数（每次冲突后 +1）

    max_retries: int
    # 最大回退次数，默认 3 次

    # ==================== 输出层 ====================
    final_response: str
    # 最终回复（summarize_node 生成）

    done: bool
    # 图是否已完成执行
