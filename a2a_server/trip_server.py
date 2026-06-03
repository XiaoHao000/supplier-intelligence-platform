"""
需求：实现基于A2A的行程线路查询服务器，处理用户的新闻搜索、社媒监控、情感分析请求

架构说明：
    本服务器是智能旅行助手中的子代理（Sub-Agent），负责处理所有行程线路查询相关任务。
    它运行在独立的进程中（127.0.0.1:5007），通过 A2A（Agent2Agent）协议与主助手通信。

    工作流程：
    1. 主助手通过 A2A 协议向本服务器发送任务（Task）
    2. 本服务器收到任务后，提取用户的自然语言查询
    3. 使用 LangChain Agent 处理查询：
       a. LLM 分析用户输入，决定调用哪个 MCP 工具
       b. LangChain 自动调用 MCP Server 的工具（端口 8003）
       c. 工具返回结果后，LLM 将结果格式化为友好的中文回复
    4. 将结果返回给主助手

    MCP Server（端口 8003）提供的工具包括：
    - 新闻搜索工具、社媒监控工具、情感分析工具
    - 风险监控工具、风险预警工具、行程报告工具
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
MCP_URL = os.getenv("TRIP_MCP_URL", "http://127.0.0.1:8003/mcp")
client = Client(MCP_URL)


# ==================== 行程查询函数 ====================
async def query_trip(conversation: str) -> dict:
    """
    通过 LangChain Agent + MCP Tools 执行行程线路查询

    参数：
        conversation (str): 用户的查询内容，例如：
            "三亚最近有没有负面新闻"
            "成都的行程分析报告"

    返回值：
        dict: 查询结果
    """
    try:
        async with client:
            tools = await load_mcp_tools(client.session)

            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个行程线路查询助手，能够调用工具来完成新闻搜索、社媒监控、情感分析。

你需要仔细分析用户的问题，从问题中提取工具需要的参数，然后调用对应的工具。
如果用户提供的信息不足以提取到调用工具所有必要参数，则向用户追问，以获取该信息。不能自己编撰参数。

注意：
- search_social_media 使用语义搜索，query_text 参数是用户的自然语言查询描述（如"行程体验反馈"），destination 参数是可选过滤。
- search_news 需要目的地，可选日期和情感倾向过滤。
- search_route 需要目的地，可选统计周期。

查询到结果后，请用清晰的中文格式化输出，格式如下：
- 新闻：目的地XX，来源XX，标题XX，内容摘要XX，情感XX，风险等级XX，发布日期XX
- 社媒：目的地XX，类别XX，文档类型XX，内容XX，评分XX
- 情感分析：目的地XX，周期XX，正面比例XX%，负面比例XX%，综合评分XX/10，趋势XX
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
        logger.error(f"行程线路 MCP 查询出错：{first_exc}")
        return {"status": "error", "message": f"行程线路 MCP 查询出错：{first_exc}"}
    except BaseException as e:
        logger.error(f"行程线路 MCP 查询出错：{str(e)}")
        return {"status": "error", "message": f"行程线路 MCP 查询出错：{str(e)}"}


# ==================== Agent Card（代理卡片） ====================
agent_card = AgentCard(
    name="TripAgent",
    description="基于 LangChain 提供行程线路查询服务的助手",
    url="http://127.0.0.1:5007",
    version="1.0.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="search news",
            description="搜索旅行相关新闻，支持指定目的地、日期和情感倾向过滤",
            examples=["三亚 负面新闻", "成都最近新闻"]
        ),
        AgentSkill(
            name="search social media",
            description="通过语义搜索查询社媒行程数据，支持自然语言描述需求",
            examples=["有没有关于行程体验的反馈", "安全风险相关信息"]
        ),
        AgentSkill(
            name="search travel route",
            description="分析旅行情感评分趋势，支持指定目的地和统计周期",
            examples=["丽江 行程分析", "西安 2025Q1情感趋势"]
        ),
        AgentSkill(
            name="monitor risk",
            description="监控旅行风险预警信息",
            examples=["查看成都的风险预警", "三亚 红色预警"]
        ),
    ]
)


# ==================== 行程线路服务器类 ====================
class TripServer(A2AServer):
    """
    行程线路查询 A2A 服务器

    负责处理所有行程线路查询相关的任务。
    """

    def __init__(self):
        super().__init__(agent_card=agent_card)

    def handle_task(self, task):
        """处理来自 A2A 客户端的任务"""
        content = (task.message or {}).get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"行程线路查询: {conversation}")

        try:
            sent_result = asyncio.run(query_trip(conversation))
            logger.info(f"MCP 查询返回: {sent_result}")

            if sent_result.get("status") == "success":
                result_text = sent_result.get("message", "")

                if "请提供" in result_text or "请确认" in result_text:
                    task.status = TaskStatus(
                        state=TaskState.INPUT_REQUIRED,
                        message={"role": "agent", "content": {"text": result_text}}
                    )
                else:
                    task.artifacts = [{"parts": [{"type": "text", "text": result_text}]}]
                    task.status = TaskStatus(state=TaskState.COMPLETED)

            elif sent_result.get("status") == "error":
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": sent_result.get("message", "查询失败，请重试。")}}
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
                message={"role": "agent",
                         "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}}
            )
            return task


# ==================== 主函数：启动服务器 ====================
if __name__ == "__main__":
    trip_server = TripServer()

    print("\n=== 服务器信息 ===")
    print(f"名称: {trip_server.agent_card.name}")
    print(f"描述: {trip_server.agent_card.description}")
    print("\n技能:")
    for skill in trip_server.agent_card.skills:
        print(f"- {skill.name}: {skill.description}")

    run_server(trip_server, host="0.0.0.0", port=5007)
