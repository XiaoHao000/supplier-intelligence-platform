"""
需求：实现基于A2A的旅行天气查询服务器，处理用户的天气查询请求并返回结果

v2.1 升级（2026-06-03）：
    - MCP 工具升级：新增 query_realtime_weather（Open-Meteo 全球气象 API）
      原有 query_weather 重命名为 query_destination_info（MySQL 静态信息）
    - Agent prompt 更新：优先使用实时天气工具，静态信息作为补充
    - AgentCard 更新：Skills 描述加入"实时天气""七日预报"等关键词

架构说明：
    本服务器是智能旅行助手中的一个子代理（Sub-Agent），负责处理旅行天气查询任务。
    它运行在独立的进程中（127.0.0.1:5005），通过 A2A（Agent2Agent）协议与主助手通信。

    工作流程（与票务查询 Agent 保持一致的架构模式）：
    1. 主助手通过 A2A 协议向本服务器发送任务（Task）
    2. 本服务器收到任务后，提取用户的自然语言查询
    3. 使用 LangChain Agent（基于工具调用的 Agent）处理查询：
       a. LLM 分析用户输入，判断是实时天气还是目的地信息
       b. 实时天气 → 调用 query_realtime_weather（Open-Meteo API）
       c. 目的地信息 → 调用 query_destination_info（MySQL）
       d. 工具返回结果后，LLM 将结果格式化为友好的中文回复
    4. 将结果返回给主助手

    涉及的关键技术：
    - LangChain Agent: 让 LLM 自主选择和使用工具的框架
    - Tool Calling Agent: LLM 以结构化格式调用工具
    - MCP Tools: MCP Server 提供的参数化工具（实时天气 + 目的地信息）
    - AgentExecutor: 负责运行 Agent 循环（思考→调用工具→处理结果→继续）
"""

# ==================== 导入依赖 ====================
import os
import json
import asyncio
from fastmcp import Client
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_tool_calling_agent, AgentExecutor

from config import Config
from datetime import datetime
import pytz

from create_logger import logger

conf = Config()

# ==================== 初始化大模型 ====================
llm = ChatOpenAI(
    **conf.llm_config
)

# ==================== MCP 客户端配置 ====================
MCP_URL = os.getenv("WEATHER_MCP_URL", "http://127.0.0.1:8002/mcp")

client = Client(MCP_URL)


# ==================== 天气查询函数 ====================
async def query_weather(conversation: str) -> dict:
    """
    通过 LangChain Agent + MCP Tools 执行旅行天气查询

    v2.1: Agent 可选择两个工具：
    - query_realtime_weather: 实时天气（Open-Meteo API）
    - query_destination_info: 目的地静态信息（MySQL）

    参数：
        conversation (str): 用户的查询内容，例如：
            "北京今天天气怎么样？"
            "成都下周天气预报"
            "西安有哪些5A级景区"
            "三亚的最佳旅游季节是什么时候"

    返回值：
        dict: 查询结果
    """
    try:
        async with client:
            tools = await load_mcp_tools(client.session)
            logger.info(f"[WeatherAgent] 已加载 {len(tools)} 个 MCP 工具:")
            for tool in tools:
                logger.info(f"  - {tool.name}: {tool.description[:80]}...")

            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个智能旅行天气查询助手，能够调用工具来查询天气和旅游信息。

你有两个工具可用：

1. **query_realtime_weather**（主力工具）：
   - 用于查询实时天气和天气预报
   - 接入 Open-Meteo 全球气象 API（ECMWF 数据）
   - 参数：city（城市名，中英文均可）、forecast_days（预报天数1-7，默认3）
   - 适用场景：用户问"今天/明天天气"、"热不热"、"会不会下雨"、"下周天气"等

2. **query_destination_info**（辅助工具）：
   - 用于查询目的地静态旅游信息
   - 数据源：MySQL 旅游信息库
   - 参数：destination（目的地）、info_type（信息类型，可选：景区评级AAAAA/
     国家级风景名胜区/最佳旅游季节/世界文化遗产/国家历史文化名城）、date（日期，可选）
   - 适用场景：用户问"有哪些5A景区"、"最佳旅游季节"、"历史文化名城"等

**重要规则**：
- 用户问天气（温度、冷热、下雨、刮风等）→ 用 query_realtime_weather
- 用户问景区评级、文化遗产、旅游季节等静态信息 → 用 query_destination_info
- 如果用户既问天气又问景区，两个工具都用
- 如果用户问题不明确，优先用 query_realtime_weather
- 城市名支持中英文，如"北京"/"Beijing"、"成都"/"chengdu"
- 从用户输入中提取参数，不要编造参数
- 如果缺少必要参数（如城市名），请追问用户

查询到结果后，请用清晰友好的中文格式化输出，包括：
- 实时天气：当前温度、体感温度、湿度、风速、天气状况 + 天气预报
- 目的地信息：目的地、信息类型、编号、来源、有效期、详细信息

当前日期是{current_date}。"""),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ])

            agent = create_tool_calling_agent(llm, tools=tools, prompt=prompt)

            agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

            current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')

            response = await agent_executor.ainvoke({
                "input": conversation,
                "current_date": current_date
            })

            return {"status": "success", "message": response["output"]}

    except Exception as e:
        logger.error(f"天气查询 MCP 查询出错：{str(e)}")
        return {"status": "error", "message": f"天气查询服务暂时不可用：{str(e)}"}


# ==================== Agent Card（代理卡片） v2.1 ====================
agent_card = AgentCard(
    name="WeatherAgent",
    description=(
        "智能旅行天气查询助手 v2.1，接入 Open-Meteo 全球实时气象 API "
        "(ECMWF 数据源)，支持实时天气、体感温度、湿度、风速、多日预报查询，"
        "同时提供目的地景区评级、最佳旅游季节等静态信息查询。"
    ),
    url="http://127.0.0.1:5005",
    version="2.1.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="实时天气查询",
            description=(
                "查询城市实时天气（温度、体感温度、湿度、风速风向、气压）和 "
                "多日天气预报（最高/最低温度、降水概率、天气状况）。"
                "接入 Open-Meteo 全球气象 API，覆盖全球城市。"
            ),
            examples=[
                "北京今天天气怎么样",
                "成都热不热，明天下雨吗",
                "三亚未来一周天气预报",
                "丽江现在多少度",
            ]
        ),
        AgentSkill(
            name="目的地信息查询",
            description=(
                "查询目的地静态旅游信息：景区评级、最佳旅游季节、"
                "世界文化遗产、国家历史文化名城等官方认证信息。"
            ),
            examples=[
                "成都有哪些5A级景区",
                "西安是什么级别的历史文化名城",
                "三亚最佳旅游季节是什么时候",
            ]
        ),
        AgentSkill(
            name="综合旅游咨询",
            description="结合实时天气和目的地信息，提供出行建议和旅游规划参考。",
            examples=[
                "五一去成都旅游合适吗，天气怎么样",
                "冬天去哈尔滨有什么好玩的，冷吗",
            ]
        ),
    ]
)


# ==================== 天气查询服务器类 ====================
class WeatherServer(A2AServer):
    """
    天气查询 A2A 服务器

    这个类继承自 A2AServer，实现了天气查询的完整流程。
    """

    def __init__(self):
        super().__init__(agent_card=agent_card)

    def handle_task(self, task):
        """处理来自 A2A 客户端的任务"""
        content = (task.message or {}).get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"[WeatherAgent] 收到查询: {conversation}")

        try:
            qual_result = asyncio.run(query_weather(conversation))
            logger.info(f"[WeatherAgent] MCP 查询返回: status={qual_result.get('status')}")

            if qual_result.get("status") == "success":
                result_text = qual_result.get("message", "")

                if "请提供" in result_text or "请确认" in result_text or "请问" in result_text:
                    task.status = TaskStatus(
                        state=TaskState.INPUT_REQUIRED,
                        message={"role": "agent", "content": {"text": result_text}}
                    )
                else:
                    task.artifacts = [{"parts": [{"type": "text", "text": result_text}]}]
                    task.status = TaskStatus(state=TaskState.COMPLETED)

            elif qual_result.get("status") == "error":
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": qual_result.get("message", "查询失败，请重试。")}}
                )
            else:
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": "查询失败，请重试或提供更多细节。"}}
                )

            return task

        except Exception as e:
            logger.error(f"[WeatherAgent] 查询失败: {str(e)}")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"role": "agent",
                         "content": {"text": f"查询失败: {str(e)} 请重试或提供更多细节。"}}
            )
            return task


# ==================== 主函数：启动服务器 ====================
if __name__ == "__main__":
    weather_server = WeatherServer()

    print("\n" + "=" * 60)
    print("🌤️  Weather A2A Server v2.1")
    print("=" * 60)
    print(f"  名称: {weather_server.agent_card.name}")
    print(f"  版本: {weather_server.agent_card.version}")
    print(f"  描述: {weather_server.agent_card.description}")
    print(f"  MCP 后端: {MCP_URL}")
    print("\n  技能列表:")
    for skill in weather_server.agent_card.skills:
        print(f"    📌 {skill.name}")
        print(f"       {skill.description}")
        print(f"       示例: {skill.examples[0] if skill.examples else 'N/A'}")
    print("=" * 60)

    run_server(weather_server, host="0.0.0.0", port=5005)
