"""
智能旅行助手 v2.0 LangGraph 节点实现

从 v1.0 chat_service.py 的方法抽取为纯函数节点，每个节点：
- 输入 AgentState
- 输出 AgentState 的部分更新

节点对应关系：
  v1.0 ChatService 方法          → v2.0 节点函数
  ─────────────────────────      ──────────────
  intent_agent()                 → intent_node()
  (隐式，散落在 chat() 中)        → slot_check_node()
  (chat() 中 follow_up 分支)      → ask_user_node()
  planning_agent()               → planning_node()
  (新增)                         → guide_node()
  chat() 中 direct execution     → dispatch_node()  [Send API]
  _call_agent_intent()           → agent_node()      [被 Send 映射]
  (新增)                         → conflict_check_node()
  react_loop() 中 summary        → summarize_node()
"""

import json
import re
import asyncio
import uuid
from datetime import datetime
from typing import Literal

import pytz
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage

from graph.state import AgentState
from graph.prompts import GraphPrompts
from main_prompts import SmartTravelPrompts
from config import Config
from create_logger import logger

# 全局单例（在 graph_builder.py 中被注入）
conf = Config()
llm = ChatOpenAI(**conf.llm_config)

# Agent 网络引用（在 graph_builder.py 初始化时注入）
_agent_network = None
_memory = None


def inject_dependencies(agent_network, memory):
    """由 graph_builder.py 在初始化时调用，注入 Agent 网络和记忆管理器"""
    global _agent_network, _memory
    _agent_network = agent_network
    _memory = memory


# ==================== 工具函数 ====================

def _clean_json(text: str) -> str:
    """清理 LLM 返回的 JSON 文本（去掉代码块标记）"""
    return re.sub(r'^```json\s*|\s*```$', '', text).strip()


def _get_current_date() -> str:
    """获取当前日期字符串"""
    return datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')


# ==================== 节点 1: 意图识别 ====================

async def intent_node(state: AgentState) -> dict:
    """
    意图识别节点 —— 分析用户输入，识别意图并改写查询

    复用 v1.0 的 SmartTravelPrompts.intent_prompt 和意图识别逻辑，
    改为从 AgentState 读取输入，返回状态更新。

    输入：AgentState.user_input, .conversation_history
    输出：AgentState.intents, .user_queries, .follow_up_message
    """
    user_input = state.get("user_input", "")
    conversation_history = state.get("conversation_history", "")

    chain = SmartTravelPrompts.intent_prompt() | llm

    current_date = _get_current_date()

    # 从 memory 获取用户偏好和任务上下文
    profile_text = _memory.get_profile_text() if _memory else "无已知偏好"
    task_context = json.dumps(_memory.current_task, ensure_ascii=False) if _memory else "{}"

    intent_response = chain.invoke({
        "conversation_history": conversation_history,
        "query": user_input,
        "current_date": current_date,
        "user_profile": profile_text,
        "task_context": task_context,
    }).content.strip()

    logger.info(f"[intent_node] 原始响应: {intent_response}")

    intent_response = _clean_json(intent_response)
    logger.info(f"[intent_node] 清理后: {intent_response}")

    try:
        intent_output = json.loads(intent_response)
    except json.JSONDecodeError as e:
        logger.error(f"[intent_node] JSON 解析失败: {e}")
        # 降级：返回追问
        return {
            "intents": ["out_of_scope"],
            "user_queries": {},
            "follow_up_message": "抱歉，我暂时无法理解您的需求，能换种方式描述一下吗？",
            "slots_complete": False,
        }

    intents = intent_output.get("intents", [])
    user_queries = intent_output.get("user_queries", {})
    follow_up_message = intent_output.get("follow_up_message", "")

    logger.info(f"[intent_node] intents={intents}, user_queries={user_queries}, follow_up={follow_up_message}")

    return {
        "intents": intents,
        "user_queries": user_queries,
        "follow_up_message": follow_up_message,
    }


# ==================== 节点 2: 槽位检查 ====================

def _heuristic_slot_check(intents: list, user_input: str) -> dict:
    """
    启发式槽位检查 —— 不调 LLM，纯规则判断

    规则：
    - weather: 需要目的地
    - ticket: 需要目的地
    - trip: 需要目的地
    - guide/travel_detail: 需要目的地或行业类别
    """
    missing_slots = []

    # 常见中国目的地（覆盖主要旅游城市，40+个）
    DESTINATION_PATTERNS = [
        # 一线/新一线
        "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "南京",
        "武汉", "长沙", "西安", "郑州", "济南", "青岛", "天津", "苏州",
        # 旅游热门
        "三亚", "丽江", "大理", "昆明", "拉萨", "桂林", "贵阳", "海口",
        "厦门", "黄山", "哈尔滨", "大连", "沈阳", "长春", "乌鲁木齐",
        "敦煌", "长白山", "呼伦贝尔", "张家界", "九寨沟", "稻城亚丁",
        "凤凰古城", "香格里拉", "西双版纳", "北海", "秦皇岛", "威海",
        # 省会/其他
        "福州", "南昌", "合肥", "太原", "石家庄", "南宁", "兰州",
        "银川", "西宁", "呼和浩特",
    ]
    found_destinations = [s for s in DESTINATION_PATTERNS if s in user_input]

    for intent in intents:
        if intent == "weather":
            if not found_destinations:
                missing_slots.append("destination(天气查询需要目的地)")
        elif intent == "ticket":
            if not found_destinations:
                missing_slots.append("destination(票务查询需要目的地)")
        elif intent == "trip":
            if not found_destinations:
                missing_slots.append("destination(行程线路需要目的地)")
        elif intent == "guide":
            if not found_destinations:
                missing_slots.append("destination(旅游攻略需要目的地)")
        elif intent == "travel_detail":
            if not found_destinations:
                missing_slots.append("destination(旅行详情需要目的地)")

    return {
        "slots_complete": len(missing_slots) == 0,
        "missing_slots": missing_slots,
    }


def slot_check_node(state: AgentState) -> dict:
    """
    槽位完整性检查节点

    先用规则判断（零延迟），如果规则判断不确定再 fallback LLM。
    """
    intents = state.get("intents", [])
    user_input = state.get("user_input", "")

    # 如果意图识别已经给出了追问消息，直接跳过
    follow_up = state.get("follow_up_message", "")
    if follow_up and "out_of_scope" not in intents:
        return {"slots_complete": False, "missing_slots": ["intent_unclear"]}

    if "out_of_scope" in intents:
        return {"slots_complete": False, "missing_slots": ["out_of_scope"]}

    # 启发式检查
    result = _heuristic_slot_check(intents, user_input)
    logger.info(f"[slot_check_node] slots_complete={result['slots_complete']}, missing={result['missing_slots']}")
    return result


# ==================== 节点 3: 追问用户 ====================

def ask_user_node(state: AgentState) -> dict:
    """
    追问用户节点 —— 当槽位不完整时，生成追问消息并终止执行
    """
    missing_slots = state.get("missing_slots", [])
    follow_up = state.get("follow_up_message", "")
    intents = state.get("intents", [])

    if follow_up:
        final_response = follow_up
    elif "out_of_scope" in intents:
        final_response = "抱歉，我只能帮您处理旅行相关的问题，例如查天气、订票务、规划行程等。您想了解什么？"
    elif missing_slots:
        slot_names = [s.split("(")[0] for s in missing_slots]
        final_response = f"为了给您更准确的信息，我还需要了解：{'、'.join(slot_names)}。请补充一下~"
    else:
        final_response = "请提供更多信息，我来帮您查询。"

    logger.info(f"[ask_user_node] 追问: {final_response}")

    return {
        "final_response": final_response,
        "done": True,
    }


# ==================== 节点 4: 策略规划 ====================

def _should_skip_planning(intents: list) -> bool:
    """
    启发式判断是否可以跳过规划（复用 v1.0 的 _should_skip_planning 逻辑）
    """
    if len(intents) <= 1:
        return True

    independent_intents = {"weather", "ticket", "trip", "guide",
                           "travel_detail"}
    for intent in intents:
        if intent not in independent_intents:
            return False
    return True


async def planning_node(state: AgentState) -> dict:
    """
    策略规划节点 —— 判断是否需要多步规划，复杂任务生成执行计划

    先启发式判断，简单任务跳过 LLM 调用。
    """
    intents = state.get("intents", [])
    user_queries = state.get("user_queries", {})

    if _should_skip_planning(intents):
        logger.info(f"[planning_node] 启发式跳过规划: {intents}")
        return {
            "need_plan": False,
            "plan_steps": [],
        }

    # 需要 LLM 规划
    chain = SmartTravelPrompts.planning_prompt() | llm

    messages = state.get("messages", [])
    last_user_msg = ""
    for msg in reversed(messages):
        if hasattr(msg, 'content') and (hasattr(msg, 'type') and msg.type == 'human'):
            last_user_msg = msg.content
            break

    planning_response = chain.invoke({
        "conversation_history": state.get("conversation_history", ""),
        "query": last_user_msg or state.get("user_input", ""),
        "intents": json.dumps(intents, ensure_ascii=False),
        "user_queries": json.dumps(user_queries, ensure_ascii=False),
    }).content.strip()

    logger.info(f"[planning_node] 规划响应: {planning_response}")

    planning_response = _clean_json(planning_response)

    try:
        plan = json.loads(planning_response)
    except json.JSONDecodeError:
        logger.warning("[planning_node] 规划JSON解析失败，降级为简单执行")
        return {"need_plan": False, "plan_steps": []}

    return {
        "need_plan": plan.get("need_plan", False),
        "plan_steps": plan.get("steps", []),
    }


# ==================== 节点 5: 攻略生成 ====================

async def guide_node(state: AgentState) -> dict:
    """
    攻略生成节点 —— 调用 Guide Agent 或直接用 LLM 生成旅行攻略

    输入：
    - user_queries["guide"]: 用户对攻略的需求描述
    - retry_count > 0 时携带冲突上下文（回退重规划）

    输出：
    - agent_results["guide"]: 生成的攻略内容
    """
    user_queries = state.get("user_queries", {})
    guide_query = user_queries.get("guide", state.get("user_input", ""))

    # 检查是否有 Guide Agent 可用
    has_rec_agent = False
    if _agent_network:
        try:
            agent = _agent_network.get_agent("GuideAgent")
            has_rec_agent = agent is not None
        except Exception:
            has_rec_agent = False

    retry_context = ""
    if state.get("retry_count", 0) > 0:
        conflicts = state.get("conflicts", [])
        retry_context = f"前次方案存在以下问题需要调整：\n" + "\n".join(
            [f"- {c.get('description', '')}，建议：{c.get('suggestion', '')}" for c in conflicts]
        )

    if has_rec_agent:
        # 通过 A2A 调用 Guide Agent
        try:
            from python_a2a import Message, TextContent, MessageRole, Task

            agent = _agent_network.get_agent("GuideAgent")
            chat_history = _memory.get_short_term_text() if _memory else ""
            payload = f"{chat_history}\nUser: {guide_query}\n重试上下文: {retry_context}" if retry_context else f"{chat_history}\nUser: {guide_query}"

            msg = Message(content=TextContent(text=payload), role=MessageRole.USER)
            task = Task(id="task-rec-" + str(uuid.uuid4()), message=msg.to_dict())

            raw_response = await agent.send_task_async(task)

            if raw_response.status.state == 'completed' and raw_response.artifacts:
                rec_result = raw_response.artifacts[0]['parts'][0]['text']
            else:
                rec_result = raw_response.status.message.get('content', {}).get('text', '评估生成中...')
        except Exception as e:
            logger.warning(f"[guide_node] Guide Agent 调用失败: {e}，降级为 LLM 直出")
            has_rec_agent = False

    if not has_rec_agent:
        # 降级：直接用 LLM 生成推荐
        chain = GraphPrompts.guide_generation_prompt() | llm
        rec_result = chain.invoke({
            "city": user_queries.get("guide", state.get("user_input", "")),
            "days": 3,  # 默认3天
            "style": "综合",
            "budget": "不限",
            "constraints": "无特殊约束",
            "retry_context": retry_context,
            "current_date": _get_current_date(),
        }).content.strip()

    # 用总结模板格式化
    summary_chain = GraphPrompts.summarize_guide_prompt() | llm
    formatted_rec = summary_chain.invoke({
        "query": guide_query,
        "raw_response": rec_result,
    }).content.strip()

    logger.info(f"[guide_node] 推荐生成完成，长度: {len(formatted_rec)}")

    # 更新结果
    current_results = dict(state.get("agent_results", {}))
    current_results["guide"] = formatted_rec

    return {
        "agent_results": current_results,
    }


# ==================== 节点 6: 任务分发 (并行执行) ====================

async def dispatch_node(state: AgentState) -> dict:
    """
    任务分发节点 —— 并行调用各 A2A Agent 执行用户意图

    v2.1: 去掉 LangGraph Send API（兼容性问题），
    改为直接 asyncio.gather 并发调用 agent_node 内部的 Agent 执行逻辑。

    与 v1.0 手写 asyncio.gather 不同：
    v2.1 仍然保留 LangGraph 状态管理（AgentState reducer 自动合并结果），
    只是将并发控制从 Send API 改为 Python 原生 asyncio。
    """
    intents = state.get("intents", [])
    user_queries = state.get("user_queries", {})
    plan_steps = state.get("plan_steps", [])

    # 确定要执行的意图列表
    if plan_steps:
        step_intents = []
        for step in plan_steps:
            intent = step.get("intent", "")
            if intent and intent not in step_intents:
                step_intents.append(intent)
        target_intents = step_intents
        logger.info(f"[dispatch_node] 按规划步骤执行 {len(target_intents)} 个任务: {target_intents}")
    else:
        target_intents = [i for i in intents if i != "guide"]  # guide 在前序节点处理
        logger.info(f"[dispatch_node] 简单并行执行 {len(target_intents)} 个任务: {target_intents}")

    if not target_intents:
        logger.info("[dispatch_node] 无需执行的任务，直接进入汇总")
        return {"execution_order": []}

    # 并发执行所有 agent_node 实例
    async def _run_one(intent: str):
        query = user_queries.get(intent, "")
        sub_state = dict(state)
        sub_state["current_intent"] = intent
        sub_state["current_query"] = query
        return await agent_node(sub_state)

    logger.info(f"[dispatch_node] 并行执行 {len(target_intents)} 个 Agent 调用")
    all_results = await asyncio.gather(*[_run_one(i) for i in target_intents])

    # 合并结果（agent_results 的 Annotated[_merge_dicts] reducer 会自动合并）
    merged_results = {}
    merged_order = []
    for result in all_results:
        if result.get("agent_results"):
            merged_results.update(result["agent_results"])
        if result.get("execution_order"):
            merged_order.extend(result["execution_order"])

    logger.info(f"[dispatch_node] 完成，结果: {list(merged_results.keys())}")
    return {
        "agent_results": merged_results,
        "execution_order": merged_order,
    }


# ==================== 节点 7: 单个 Agent 执行 ====================

async def agent_node(state: AgentState) -> dict:
    """
    单个 Agent 执行节点 —— 被 Send API 映射调用

    每个 Agent 实例独立执行一个意图的查询：
    1. weather/ticket/trip → 调用 A2A Agent
    2. travel_detail → LLM 直出（不调Agent）
    3. guide → 跳过（已在 guide_node 处理）
    4. 未匹配意图 → LLM 降级回答

    这是 v1.0 _call_agent_intent() 的 v2.0 版本，改为从 AgentState 读取，返回状态更新。
    """
    intent = state.get("current_intent", "")
    query_str = state.get("current_query", "")

    if not intent:
        return {"agent_results": {}}

    logger.info(f"[agent_node] 执行意图={intent}, query={query_str}")

    # 获取 agent 名称
    agent_name = conf.intent.get(intent)

    # 旅行详情 → LLM 直出
    if intent == "travel_detail":
        chain = SmartTravelPrompts.travel_detail_prompt() | llm
        result = chain.invoke({"query": query_str}).content.strip()
        current_results = dict(state.get("agent_results", {}))
        current_results[intent] = result
        current_order = list(state.get("execution_order", [])) + [intent]
        return {
            "agent_results": current_results,
            "execution_order": current_order,
        }

    # 旅游攻略已在 guide_node 处理
    if intent == "guide":
        return {"agent_results": state.get("agent_results", {})}

    # 通过 A2A 调用 Agent
    if agent_name and _agent_network:
        try:
            # 更新 memory
            if _memory and intent in ["weather", "ticket", "trip", "guide"]:
                _memory.extract_entities(intent, query_str)
                _memory.update_task_context({"type": intent, "query": query_str})

            agent = _agent_network.get_agent(agent_name)
            if agent is None:
                result = f"抱歉，{agent_name} 暂时不可用，请稍后重试。"
            else:
                chat_history = _memory.get_short_term_text() if _memory else ""
                payload = f"{chat_history}\nUser: {query_str}"
                from python_a2a import Message, TextContent, MessageRole, Task
                msg = Message(content=TextContent(text=payload), role=MessageRole.USER)
                task = Task(id="task-" + str(uuid.uuid4()), message=msg.to_dict())

                raw_response = await agent.send_task_async(task)

                if raw_response.status.state == 'completed' and raw_response.artifacts:
                    agent_result = raw_response.artifacts[0]['parts'][0]['text']
                elif raw_response.status.message:
                    agent_result = raw_response.status.message.get('content', {}).get(
                        'text', str(raw_response.status.message))
                else:
                    agent_result = f"查询失败：{raw_response.status.message or '未知错误'}"

                # 根据 Agent 类型选择总结模板
                if agent_name == "WeatherAgent":
                    summary_chain = SmartTravelPrompts.summarize_weather_prompt() | llm
                    result = summary_chain.invoke({
                        "query": query_str, "raw_response": agent_result
                    }).content.strip()
                elif agent_name == "TicketAgent":
                    summary_chain = SmartTravelPrompts.summarize_ticket_prompt() | llm
                    result = summary_chain.invoke({
                        "query": query_str, "raw_response": agent_result
                    }).content.strip()
                elif agent_name == "TripAgent":
                    summary_chain = SmartTravelPrompts.summarize_ticket_prompt() | llm
                    result = summary_chain.invoke({
                        "query": query_str, "raw_response": agent_result
                    }).content.strip()
                elif agent_name == "GuideAgent":
                    summary_chain = SmartTravelPrompts.summarize_guide_prompt() | llm
                    result = summary_chain.invoke({
                        "query": query_str, "raw_response": agent_result
                    }).content.strip()
                else:
                    result = agent_result

        except Exception as e:
            logger.error(f"[agent_node] {agent_name} 调用异常: {e}")
            result = f"{agent_name} 服务暂时不可用：{str(e)}"
    else:
        # 未匹配到 Agent：LLM 直接回答
        chain = SmartTravelPrompts.travel_detail_prompt() | llm
        result = chain.invoke({"query": query_str}).content.strip()

    # 更新结果字典
    current_results = dict(state.get("agent_results", {}))
    current_results[intent] = result
    current_order = list(state.get("execution_order", [])) + [intent]

    logger.info(f"[agent_node] {intent} 执行完成，结果长度: {len(result) if result else 0}")

    return {
        "agent_results": current_results,
        "execution_order": current_order,
    }


# ==================== 节点 8: 冲突检测 ====================

async def conflict_check_node(state: AgentState) -> dict:
    """
    冲突检测节点 —— LLM 判断攻略推荐与各 Agent 实际返回之间是否存在冲突

    v2.0 核心新增能力：
    - 攻略推荐的航班 vs 票务实际可用票
    - 攻略的日期安排 vs 天气条件
    - 预算总和 vs 用户预算上限

    无攻略意图时跳过（直接返回无冲突）。
    """
    agent_results = state.get("agent_results", {})
    intents = state.get("intents", [])

    # 没有推荐意图，跳过冲突检测
    if "guide" not in intents and "guide" not in agent_results:
        logger.info("[conflict_check] 无推荐意图，跳过冲突检测")
        return {"conflicts": [], "done": True}

    rec_result = agent_results.get("guide", "")
    if not rec_result:
        return {"conflicts": [], "done": True}

    # 调用 LLM 进行冲突检测
    chain = GraphPrompts.conflict_detection_prompt() | llm

    # 构建 agent_results 的文本表示（排除 guide 本身）
    other_results = {k: v for k, v in agent_results.items() if k != "guide"}
    agent_results_text = json.dumps(other_results, ensure_ascii=False, indent=2)

    response = chain.invoke({
        "guide_plan": rec_result,
        "agent_results": agent_results_text,
        "user_budget": state.get("user_queries", {}).get("budget", "未指定"),
    }).content.strip()

    logger.info(f"[conflict_check] 冲突检测结果: {response}")

    response = _clean_json(response)

    try:
        result = json.loads(response)
    except json.JSONDecodeError:
        logger.warning("[conflict_check] 冲突检测JSON解析失败，默认无冲突")
        return {"conflicts": [], "done": True}

    has_conflict = result.get("has_conflict", False)
    conflicts = result.get("conflicts", [])

    new_retry_count = state.get("retry_count", 0)
    if has_conflict:
        new_retry_count += 1
        logger.info(f"[conflict_check] 发现 {len(conflicts)} 个冲突，重试次数: {new_retry_count}")
    else:
        logger.info("[conflict_check] 无冲突，进入汇总")

    return {
        "conflicts": conflicts,
        "retry_count": new_retry_count,
        "done": not has_conflict,
    }


# ==================== 节点 9: 汇总生成 ====================

async def summarize_node(state: AgentState) -> dict:
    """
    汇总生成节点 —— 将所有 Agent 结果整合为一条连贯的最终回复

    对应 v1.0 react_loop() 中的 summary 部分。
    """
    agent_results = state.get("agent_results", {})
    intents = state.get("intents", [])

    if not agent_results:
        final_response = "抱歉，暂时没有获取到相关信息。请稍后重试。"
        return {"final_response": final_response, "done": True}

    # 单结果：直接返回
    if len(agent_results) == 1:
        final_response = list(agent_results.values())[0]
        return {"final_response": final_response, "done": True}

    # 多结果：LLM 汇总
    # 获取用户输入
    user_input = state.get("user_input", "")
    messages = state.get("messages", [])
    last_user_msg = user_input
    for msg in reversed(messages):
        if hasattr(msg, 'content'):
            if hasattr(msg, 'type') and msg.type == 'human':
                last_user_msg = msg.content
                break

    # 构建汇总输入
    all_obs_lines = []
    for intent, result in agent_results.items():
        all_obs_lines.append(f"[{intent}] 结果: {result}")
    all_obs = "\n".join(all_obs_lines)

    summary_chain = SmartTravelPrompts.react_summary_prompt() | llm
    final_response = summary_chain.invoke({
        "query": last_user_msg,
        "all_observations": all_obs,
    }).content.strip()

    logger.info(f"[summarize_node] 汇总完成，长度: {len(final_response)}")

    return {
        "final_response": final_response,
        "done": True,
    }
