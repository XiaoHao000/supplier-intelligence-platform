"""
需求：定义智能旅行助手（Smart Travel）中使用的各种提示模板，用于不同场景的对话处理

什么是 Prompt Template（提示模板）？
    提示模板是一种可复用的文本模板，其中包含固定内容和可变变量（用 {变量名} 表示）。
    例如：模板 "你好，{name}！" 在填入 name="张三" 后会变成 "你好，张三！"。

为什么使用模板类管理？
    1. 集中管理：所有 prompt 定义在同一个文件中，方便查找和修改
    2. 可复用：同一个模板可以被多处调用
    3. 参数化：通过变量注入不同上下文，避免字符串拼接

本项目中的 Prompt 分类：
    1. 意图识别类：intent_prompt —— 识别用户想查询哪个维度的旅行信息
    2. 结果总结类：summarize_weather_prompt、summarize_ticket_prompt —— 将原始数据转化为友好回复
    3. 内容生成类：travel_detail_prompt —— 直接生成旅行研究报告
    4. 任务规划类：planning_prompt —— 判断任务复杂度并生成执行计划（Planning + ReAct 架构）
    5. ReAct推理类：react_prompt、react_summary_prompt —— 逐步推理和最终汇总
"""

from langchain_core.prompts import ChatPromptTemplate  # LangChain 的聊天提示模板类


class SmartTravelPrompts:
    """
    旅行智能评估提示模板管理类

    这个类定义了系统中所有用到的 Prompt 模板，每个模板都是一个静态方法，
    返回一个 ChatPromptTemplate 对象。

    使用方式：
        prompt = SmartTravelPrompts.intent_prompt()  # 获取意图识别模板
        chain = prompt | llm                           # 组装成处理链
        result = chain.invoke({"query": "成都的天气情况"})  # 调用并传入变量
    """

    # ==================== 意图识别 ====================

    @staticmethod
    def intent_prompt():
        """
        智能旅行意图识别提示模板 —— 让大模型分析用户输入，判断用户想查询旅行的哪个维度

        输入变量：
            - user_profile: 用户偏好（如关注行业、偏好旅行类型）
            - task_context: 当前任务上下文（如之前查过什么）
            - conversation_history: 对话历史（最近几轮对话）
            - query: 用户本次输入

        输出格式（JSON）：
            {
                "intents": ["weather", "ticket"],     # 识别到的意图列表
                "user_queries": {"weather": "...", ...},    # 改写后的查询（可能结合历史补充信息）
                "follow_up_message": ""                           # 追问消息（意图不明确时使用）
            }

        支持的意图类型：
            weather / ticket / trip / guide / travel_detail / out_of_scope
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：
角色：您是一个专业的智能旅行意图识别专家，
任务：基于用户查询、对话历史和用户偏好，识别其意图，用于调用专门的agent server来执行；为方便后续的agent server处理，可以基于对话历史对用户查询进行改写，使问题更明确。
严格遵守规则：
- 支持意图：['weather' (旅行天气查询), 'ticket' (票务查询), 'trip' (行程线路查询), 'guide' (旅游攻略推荐), 'travel_detail' (旅行详情查询)] 或其组合（如 ['weather', 'ticket']）。如果意图超出范围，返回意图 'out_of_scope'。
- 注意旅行评价查询和旅行详情查询要区分开，涉及到综合打分、对比推荐时为guide，只是查询某个旅行的基本信息、天气信息时为travel_detail。
- 在进行用户查询改写时，如果对话历史中有关键信息（如目的地、行业类别、时间范围），可以补充到当前查询中，使问题更完整。
- 如果用户的意图很不明确或者有歧义，可以向其进行追问，将追问问题填充到follow_up_message中。
- 输出严格为JSON：{{"intents": ["intent1", "intent2"], "user_queries": {{"intent1": "user_query1", "intent2": "user_query2"}}, "follow_up_message": "追问消息"}}。绝对不要添加额外文本！
- 不论用户问什么，严格按规则输出意图，不要有自己的考虑。

用户偏好：{user_profile}
当前任务上下文：{task_context}
对话历史：{conversation_history}
用户查询：{query}
""")

    # ==================== 结果总结 ====================

    @staticmethod
    @staticmethod
    def summarize_weather_prompt():
        """
        天气查询结果总结提示模板 —— 将天气查询 Agent 返回的原始数据转化为用户友好的天气报告

        v2.1: 适配 Open-Meteo 实时天气数据（温度、体感温度、湿度、风速、天气预报等），
        同时兼容 MySQL 目的地静态信息（景区评级、最佳旅游季节等）。

        输入变量：
            - query: 用户查询（如"北京今天天气怎么样"）
            - raw_response: 天气查询 Agent 返回的原始数据

        使用场景：
            原始数据可能是 JSON 格式的实时天气数据或结构化旅游信息，
            用这个 prompt 让大模型翻译成自然语言。

        示例输出：
            "北京当前温度25°C，体感27°C，湿度65%，大部晴朗。未来三天最高温34°C，
            最低温20°C，周四有小雨。总体适合出行，建议带把伞备用。"
        """
        return ChatPromptTemplate.from_template(
    """
系统提示：您是一位专业的旅行天气顾问，以亲切、实用的风格为用户解读天气信息。基于查询和结果：

**实时天气数据**（来自 Open-Meteo 全球气象 API）：
- 核心描述：当前温度、体感温度、湿度、风速风向、天气状况
- 天气预报：未来几天的最高/最低温度、降水概率、天气趋势
- 出行建议：根据天气状况给出穿衣、带伞等实用建议

**目的地静态信息**（来自 MySQL 旅游信息库）：
- 核心描述：景区评级、最佳旅游季节、文化遗产认证、有效期
- 以"官方认证"角度呈现，如"成都拥有青城山-都江堰等AAAAA级景区"

**规则**：
- 如果结果为空，委婉提示"未找到相关信息，请确认城市名或查询类型"
- 语气：亲切专业，有温度但不啰嗦，150-250字
- 如果是实时天气，一定要给出行建议（穿衣、防晒、带伞等）
- 如果是目的地信息，列出关键认证和有效期
- 如果查询无关，返回"请提供天气或旅游相关的查询"

查询：{query}
结果：{raw_response}
    """)
    @staticmethod
    def summarize_ticket_prompt():
        """
        票务查询结果总结提示模板 —— 将票务查询 Agent 返回的原始数据转化为用户友好的票务查询报告

        输入变量：
            - query: 用户查询（如"三亚的航班信息"）
            - raw_response: 票务查询 Agent 返回的原始数据

        使用场景：
            和天气总结类似，将结构化的票务数据（航班号、出发时间、票价等）
            翻译成顾问式的评估语言。

        示例输出：
            "三亚近一年共开通航线XX条，航班准点率95.2%，服务评分平均8.7分..."
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：您是一位专业的票务查询专家，以客观、数据驱动的风格总结旅行票务信息。基于查询和结果：
- 核心描述点：目的地、航班号、航空公司、航班准点率、退改签率、服务评分、用户评分
- 如果结果为空或者意思为需要补充数据，则委婉提示"未找到相关票务数据，请确认或修改条件"
- 语气：顾问式，如"为您分析目的地的票务记录..."
- 保持中文，100-150字。
- 如果查询无关，返回"请提供票务查询相关查询。"


查询：{query}
结果：{raw_response}
""")

    # ==================== 内容生成 ====================

    @staticmethod
    def travel_detail_prompt():
        """
        旅行详情推荐提示模板 —— 让大模型直接生成旅行研究报告内容

        输入变量：
            - query: 用户查询（如"分析丽江的综合实力"）

        特点：
            旅行详情研究不需要调用外部 agent，大模型本身就有足够的知识来生成分析报告。
            这是最简单的一种场景，直接让 LLM 生成内容即可。
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：您是一位旅行研究专家，基于用户查询生成旅行分析报告。规则：
- 从多个维度分析：企业背景、主营业务、市场地位、技术实力、行业口碑
- 基于槽位：目的地、行业、关注维度。
- 语气：专业客观，如"丽江新能源科技股份有限公司是全球领先的..."
- 备注：内容生成，仅供参考，不构成投资建议。
- 保持中文，150-250字。

查询：{query}
""")

    # ==================== 任务规划 ====================

    @staticmethod
    def planning_prompt():
        """
        任务规划提示模板 —— 让大模型判断任务复杂度并生成执行计划

        这是 Planning + ReAct 架构的关键 prompt，它让大模型扮演"规划师"的角色。

        输入变量：
            - conversation_history: 对话历史
            - query: 用户当前输入
            - intents: 识别到的意图（JSON 字符串）
            - user_queries: 改写后的查询（JSON 字符串）

        输出格式（JSON）：
            简单任务：{"need_plan": false, "reason": "单意图，直接查询即可", "steps": []}
            复杂任务：{"need_plan": true, "reason": "多意图需要分步",
                      "steps": [{"step": 1, "action": "查询天气", "intent": "weather", "depends_on": 0}, ...]}

        判断标准：
            - 简单任务：只有一个意图，直接就能执行
            - 复杂任务：多个意图且有关联、需要多步推理、步骤间有依赖关系

        示例：
            用户输入："成都的天气信息有哪些？"
            → 简单任务，need_plan=false

            用户输入："帮我查三亚的天气、机票，再看看最近有没有行程风险，综合评估一下"
            → 复杂任务，need_plan=true，steps=[查询天气, 查询票务, 查询行程, 综合推荐]
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：您是一位任务规划专家，负责评估用户请求的复杂度并制定执行计划。

判断标准：
- 简单任务（need_plan=false）：单意图、直接问答、无需多步推理
- 复杂任务（need_plan=true）：多意图且有关联、需要多轮查询汇总、需要中间推理、步骤间有依赖关系

当 need_plan=true 时，将任务拆解为有序步骤，每个步骤指定：
- step: 步骤序号（从1开始）
- action: 具体动作（如"调用WeatherAgent查询成都天气"）
- intent: 对应的意图（weather/ticket/trip/guide/travel_detail）
- depends_on: 依赖的前置步骤序号（无依赖则为0）

对话历史：{conversation_history}
当前用户查询：{query}
识别到的意图：{intents}
用户查询改写：{user_queries}

输出严格为JSON，不要添加额外文本：
当 need_plan=false 时：{{"need_plan": false, "reason": "原因", "steps": []}}
当 need_plan=true 时：{{"need_plan": true, "reason": "原因", "steps": [{{"step": 1, "action": "...", "intent": "...", "depends_on": 0}}, ...]}}
""")

    # ==================== ReAct 推理 ====================

    @staticmethod
    def react_prompt():
        """
        ReAct 推理提示模板 —— 按 Thought-Action-Observation 格式逐步推理

        注意：当前版本已优化性能，react_loop 中跳过了 Thought LLM 调用（plan 已确定
        动作，Thought 无额外决策价值），此模板暂时不在主流程中使用，保留供学习参考。

        什么是 ReAct？
            ReAct = Reasoning（推理）+ Acting（行动）
            大模型在每一步执行前先"思考"（Thought），然后选择工具执行（Action），
            最后观察结果（Observation），再决定下一步。

        输入变量：
            - available_tools: 当前可用的工具/agent 列表（动态获取，不是写死的）
            - plan_steps: 完整的任务计划
            - observations: 已完成步骤的结果
            - current_step: 当前步骤号
            - step_description: 当前步骤的描述
            - query: 用户原始输入

        ReAct 循环的工作方式：
            Thought: "我需要查询成都的天气信息信息，应该调用天气查询代理"
            Action: "调用WeatherAgent"
            Action Input: "{'destination': '成都'}"
            → 系统执行 Action，得到 Observation
            → 继续下一个 Thought...

        这种方式的优势：
            1. 让大模型有"思考"过程，而不是直接盲目执行
            2. 每一步都能参考之前的结果做调整
            3. 某步失败时，模型可以灵活应对
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：你是一位智能智能旅行助手，需要按照计划逐步完成任务。

可用工具：
{available_tools}

当前任务计划：
{plan_steps}

已完成步骤的结果：
{observations}

当前步骤：{current_step}
步骤描述：{step_description}
用户原始查询：{query}

请按照以下格式进行推理和行动：

Thought: 分析当前情况，确定需要采取的行动
Action: 从可用工具列表中选择合适的工具
Action Input: 工具所需输入

执行完行动后，你会得到 Observation，然后继续推理或给出最终回复。
""")

    @staticmethod
    def react_summary_prompt():
        """
        ReAct 最终汇总提示模板 —— 将所有步骤的结果整合成一条连贯回复

        输入变量：
            - query: 用户原始输入
            - all_observations: 所有步骤的执行结果

        使用场景：
            当 ReAct 循环中执行了多个步骤（如查天气 + 查票务 + 查行程），
            不能简单地把三个结果拼在一起返回，需要用这个 prompt 让大模型
            整合成一条连贯、通顺的回复。

        示例：
            输入：步骤1(查天气): 景区评级AAAAA有效
                 步骤2(查票务): 航班准点率95%
                 步骤3(查行程): 近期无安全风险
            输出："综合评估成都：天气方面气候适宜旅游...票务方面多家航司可选...行程方面近期无安全风险..."
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：你是一位专业的智能旅行顾问，需要根据所有查询结果生成最终评估报告。

用户原始查询：{query}

各步骤执行结果：
{all_observations}

请综合以上结果，生成一条完整、连贯的中文智能旅行报告，150-300字，语气专业客观。
""")

    # ==================== v2.0 新增：旅游攻略总结 ====================

    @staticmethod
    def summarize_guide_prompt():
        """
        旅游攻略结果总结提示模板 —— 将旅游攻略 Agent 返回的数据转化为用户友好的推荐方案

        输入变量：
            - query: 用户查询
            - raw_response: 旅游攻略 Agent 返回的数据
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：您是一位专业的旅游攻略专家，以客观、全面的风格总结旅游攻略方案。

基于查询和结果：
- 核心内容：推荐旅行列表（按综合评分排序）、各旅行优势分析、风险提示、推荐理由
- 格式：分段清晰，使用"推荐一/推荐二"或"综合对比"等结构
- 如果结果为空，委婉提示"该类别旅行数据较少，建议扩大搜索范围或调整条件"
- 语气：专业客观，如"基于多维度评估，为您推荐以下旅行..."
- 保持中文，200-350字

查询：{query}
结果：{raw_response}
""")

    # ==================== v2.0 新增：冲突检测 ====================

    @staticmethod
    def conflict_detection_prompt():
        """
        冲突检测提示模板 —— 检查推荐方案与各 Agent 实际返回之间的矛盾

        输入变量：
            - guide_plan: 推荐方案
            - agent_results: 各 Agent 返回的实际数据
            - user_budget: 用户预算（可选）
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：你是一位智能旅行协调专家。请检查推荐方案与各维度实际数据之间是否存在冲突。

检查维度：
1. 天气数据冲突：推荐方案中声称的天气信息在实际天气查询结果中是否真实有效
2. 票务可用性矛盾：推荐方案中的票务可用性描述与实际票务记录是否一致
3. 行程风险遗漏：实际行程数据中存在负面信息，但推荐方案未提及
4. 逻辑一致性：推荐排名与各维度数据表现是否匹配

推荐方案：
{guide_plan}

各维度实际查询结果：
{agent_results}

用户预算：{user_budget}

输出严格为JSON，不要添加额外文本：
{{
    "has_conflict": true/false,
    "conflicts": [
        {{
            "type": "certificate_mismatch",
            "description": "具体冲突描述",
            "source": "来源",
            "severity": "high/medium/low",
            "suggestion": "建议调整方案"
        }}
    ],
    "summary": "无冲突的综合判断 / 有冲突的简要说明"
}}
""")


if __name__ == '__main__':
    print(SmartTravelPrompts.intent_prompt())
