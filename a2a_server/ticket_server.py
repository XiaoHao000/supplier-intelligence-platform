"""
需求：实现基于A2A的票务查询服务器，处理用户的航班查询、航班状态、服务评分请求

架构说明：
    本服务器是智能旅行助手中的子代理（Sub-Agent），负责处理所有票务查询相关任务。
    它运行在独立的进程中（127.0.0.1:5006），通过 A2A（Agent2Agent）协议与主助手通信。

    工作流程：
    1. 主助手通过 A2A 协议向本服务器发送任务（Task）
    2. 本服务器收到任务后，提取用户的自然语言查询
    3. 使用 LangChain Agent（基于工具调用的 Agent）处理查询：
       a. LLM 分析用户输入，决定调用哪个 MCP 工具
       b. LangChain 自动调用 MCP Server 的工具（端口 8001）
       c. 工具返回结果后，LLM 将结果格式化为友好的中文回复
    4. 将结果返回给主助手

    MCP Server（端口 8001）提供的工具包括：
    - 航班查询工具
    - 航班状态查询工具
    - 服务评分查询工具
    - 机票预订工具
    - 值机手续工具
    - 服务反馈工具
"""

# ==================== 导入依赖 ====================
import os
import json
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_tool_calling_agent, AgentExecutor
from fastmcp import Client
from datetime import datetime
import pytz

from config import Config
from create_logger import logger

conf = Config()

# ==================== 初始化大模型 ====================
llm = ChatOpenAI(
    **conf.llm_config
)

# ==================== MCP 客户端配置 ====================
MCP_URL = os.getenv("TICKET_MCP_URL", "http://127.0.0.1:8001/mcp")

client = Client(MCP_URL)


# ==================== 票务查询函数 ====================
async def query_ticket(conversation: str) -> dict:
    """
    通过 LangChain Agent + MCP Tools 执行票务查询

    参数：
        conversation (str): 用户的查询内容，例如：
            "三亚的航班信息"
            "成都2025年航班状态"

    返回值：
        dict: 查询结果
    """
    try:
        async with client:
            tools = await load_mcp_tools(client.session)

            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个票务查询助手，能够调用工具来查询航班信息、航班状态和服务评分。
你需要仔细分析用户的问题，从问题中提取工具需要的参数，然后调用对应的查询工具。
如果用户提供的信息不足以提取到调用工具所有必要参数，则向用户追问，以获取该信息。不能自己编撰参数。
查询到结果后，请用清晰的中文格式化输出，格式如下：
- 航班信息：目的地成都，航班号CA1401，航空公司国航，出发时间08:00，到达时间11:00，票价780元，余票12张
- 航班状态：目的地成都，航班号CA1401，状态（正常/延误），票价780元
- 服务评分：目的地成都，航班号CA1401，准点率95%，票价780元，用户评分4.8/5
如果未查到数据，请回复"未找到相关票务数据，请确认或修改查询条件。"
当前日期是{current_date}。"""),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ])

            agent = create_tool_calling_agent(llm, tools, prompt)

            agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

            current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')

            response = await agent_executor.ainvoke({
                "input": conversation,
                "current_date": current_date
            })

            return {"status": "success", "message": response["output"]}

    except ExceptionGroup as eg:
        first_exc = eg.exceptions[0] if eg.exceptions else eg
        logger.error(f"票务查询 MCP 查询出错：{first_exc}")
        return {"status": "error", "message": f"票务查询 MCP 查询出错：{first_exc}"}
    except BaseException as e:
        logger.error(f"票务查询 MCP 查询出错：{str(e)}")
        return {"status": "error", "message": f"票务查询 MCP 查询出错：{str(e)}"}


# ==================== Agent Card（代理卡片） ====================
agent_card = AgentCard(
    name="TicketAgent",
    description="基于 LangChain 提供票务查询服务的助手",
    url="http://127.0.0.1:5006",
    version="2.0.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="query flights",
            description="查询旅行航班信息，支持指定目的地、出发日期和航空公司",
            examples=["三亚 航班信息", "成都2025年航班"]
        ),
        AgentSkill(
            name="query flight status",
            description="查询航班状态，支持指定目的地和航班号",
            examples=["查看航班CA1401的状态", "丽江航班状态"]
        ),
        AgentSkill(
            name="query service score",
            description="查询旅行服务评分，支持指定目的地和最低评分",
            examples=["成都的服务评分", "三亚航班服务"]
        ),
    ]
)


# ==================== 票务查询服务器类 ====================
class TicketServer(A2AServer):
    """
    票务查询 A2A 服务器

    负责处理所有票务查询相关的任务。
    """

    def __init__(self):
        super().__init__(agent_card=agent_card)

    def handle_task(self, task):
        """处理来自 A2A 客户端的任务"""
        content = (task.message or {}).get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"票务查询查询: {conversation}")

        try:
            perf_result = asyncio.run(query_ticket(conversation))
            logger.info(f"MCP 查询返回: {perf_result}")

            if perf_result.get("status") == "success":
                result_text = perf_result.get("message", "")
                task.artifacts = [{"parts": [{"type": "text", "text": result_text}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)

            elif perf_result.get("status") == "error":
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": perf_result.get("message", "查询失败，请重试。")}}
                )
            else:
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": "查询失败，请重试或提供更多细节。"}}
                )

            return task

        except Exception as e:
            logger.error(f"查询失败: {str(e)}")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"role": "agent", "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}}
            )
            return task


# ==================== 主函数：启动服务器 ====================
if __name__ == "__main__":
    ticket_server = TicketServer()

    print("\n=== 服务器信息 ===")
    print(f"名称: {ticket_server.agent_card.name}")
    print(f"描述: {ticket_server.agent_card.description}")
    print("\n技能:")
    for skill in ticket_server.agent_card.skills:
        print(f"- {skill.name}: {skill.description}")

    run_server(ticket_server, host="0.0.0.0", port=5006)
