"""
需求：实现基于A2A的旅游攻略服务器，处理用户的旅行搜索、详情查询、综合评估请求

架构说明：
    本服务器是智能旅行助手 v2.0 新增的子代理，运行在 5008 端口。
    与其他 Agent 保持一致的架构模式：

    - 使用 LangChain Agent + MCP Tools 模式
    - LLM 从自然语言中提取参数（目的地、类别、评估维度等）
    - 调用 Guide MCP Server 的工具（端口 8004）
    - MCP Server 返回结果后，LLM 格式化为友好的中文评估报告

    工作流程：
    1. 主助手通过 A2A 协议向本服务器发送任务
    2. 本服务器收到任务后，提取用户的自然语言查询
    3. 使用 LangChain Agent 处理查询：
       a. LLM 分析用户输入，决定调用哪个 MCP 工具
       b. LangChain 自动调用 MCP Server 的工具（端口 8004）
       c. 工具返回结果后，LLM 将结果格式化为友好的中文评估报告
    4. 将结果返回给主助手
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

llm = ChatOpenAI(**conf.llm_config)

# MCP Client 配置
MCP_URL = os.getenv("GUIDE_MCP_URL", "http://127.0.0.1:8004/mcp")
client = Client(MCP_URL)


# ==================== 旅游攻略函数 ====================
async def query_guide(conversation: str) -> dict:
    """
    通过 LangChain Agent + MCP Tools 执行旅行搜索、详情查询或综合评估

    与 trip_server.py 的 query_trip 使用完全相同的架构模式：
    1. 连接 MCP Server 加载所有可用工具
    2. 创建 LangChain Tool Calling Agent
    3. AgentExecutor 自动选择工具并执行
    """
    try:
        async with client:
            tools = await load_mcp_tools(client.session)

            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个旅游攻略与评估助手，能够调用工具来搜索旅行、查询详情、生成综合评估。

你需要仔细分析用户的问题：
- 搜索旅行时，提取旅行类别、评估标准
- 查询详情时，提取目的地和类别
- 综合评估时，提取目的地、评估维度（如天气、票务、行程）、需求描述

如果用户没有明确指定某个参数，使用合理的默认值：
- 评估维度默认"综合"
- 需求描述默认"全面评估"

查询到结果后，请用清晰的中文格式化输出：
- 旅行搜索：目的地、类别、评分、内容摘要
- 旅行详情：名称、类别、多维度评估要点
- 综合评估：天气信息确认、票务可用性分析、行程风险评估、综合推荐建议

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
        logger.error(f"旅游攻略 MCP 查询出错：{first_exc}")
        return {"status": "error", "message": f"旅游攻略 MCP 查询出错：{first_exc}"}
    except BaseException as e:
        logger.error(f"旅游攻略 MCP 查询出错：{str(e)}")
        return {"status": "error", "message": f"旅游攻略 MCP 查询出错：{str(e)}"}


# ==================== Agent Card ====================
agent_card = AgentCard(
    name="GuideAgent",
    description="基于 LangChain 提供旅游攻略推荐服务的助手",
    url="http://127.0.0.1:5008",
    version="1.0.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="search destination",
            description="搜索旅行，支持指定类别、评估标准和最低评分",
            examples=["新能源电池旅行", "高性价比电子元器件旅行"]
        ),
        AgentSkill(
            name="get attraction detail",
            description="查询旅行详细信息",
            examples=["成都 详情", "三亚公司信息"]
        ),
        AgentSkill(
            name="plan itinerary",
            description="生成旅行综合评估报告，包含多维度分析和推荐建议",
            examples=["评估成都", "对丽江进行综合评估"]
        ),
    ]
)


# ==================== 旅游攻略服务器 ====================
class GuideServer(A2AServer):
    """旅游攻略 A2A 服务器"""

    def __init__(self):
        super().__init__(agent_card=agent_card)

    def handle_task(self, task):
        """处理来自 A2A 客户端的任务"""
        content = (task.message or {}).get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"旅游攻略查询: {conversation}")

        try:
            rec_result = asyncio.run(query_guide(conversation))
            logger.info(f"推荐 MCP 查询返回状态: {rec_result.get('status')}")

            if rec_result.get("status") == "success":
                result_text = rec_result.get("message", "")

                if "请提供" in result_text or "请确认" in result_text:
                    task.status = TaskStatus(
                        state=TaskState.INPUT_REQUIRED,
                        message={"role": "agent", "content": {"text": result_text}}
                    )
                else:
                    task.artifacts = [{"parts": [{"type": "text", "text": result_text}]}]
                    task.status = TaskStatus(state=TaskState.COMPLETED)

            elif rec_result.get("status") == "error":
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": rec_result.get("message", "查询失败，请重试。")}}
                )
            else:
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": "查询失败，请重试或提供更多细节。"}}
                )

            return task

        except Exception as e:
            logger.error(f"旅游攻略查询失败: {str(e)}")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"role": "agent", "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}}
            )
            return task


# ==================== 主函数 ====================
if __name__ == "__main__":
    guide_server = GuideServer()

    print("\n=== 旅游攻略服务器信息 ===")
    print(f"名称: {guide_server.agent_card.name}")
    print(f"描述: {guide_server.agent_card.description}")
    print("\n技能:")
    for skill in guide_server.agent_card.skills:
        print(f"- {skill.name}: {skill.description}")

    run_server(guide_server, host="0.0.0.0", port=5008)
