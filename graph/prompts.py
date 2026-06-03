"""
智能旅行助手 v2.0 新增 Prompt 模板

v1.0 的 prompt 保留在 main_prompts.py 中不变（intent/planning/summarize_weather/summarize_ticket/travel_detail/react_summary）。
v2.0 新增的 prompt 定义在此：
- 槽位检查：判断用户输入是否包含足够的查询参数
- 冲突检测：检查推荐方案与各维度实际数据之间的冲突
- 推荐总结：将 Guide Agent 返回结果格式化为友好报告
"""

from langchain_core.prompts import ChatPromptTemplate


class GraphPrompts:
    """
    v2.0 LangGraph 编排层专用 Prompt 模板
    v1.0 的 SmartTravelPrompts 仍然可用，此类只补充新增的
    """

    # ==================== 槽位检查 ====================

    @staticmethod
    def slot_check_prompt():
        """
        槽位完整性检查 —— 规则驱动的快速判断，不调 LLM 时也可用。
        此处提供 LLM 版本供复杂场景 fallback。

        输入变量：
            - query: 用户输入
            - intents: 识别到的意图列表

        输出：JSON {"slots_complete": true/false, "missing_slots": [...], "reason": "..."}
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：你是一位槽位检查专家。判断用户的查询是否包含了足够信息来调用对应的服务。

需要的槽位：
- weather: destination (目的地), weather_type (查询类型，可选)
- ticket: destination (目的地), date (日期，可选)
- trip: destination (目的地), source (来源，可选)
- guide: category (旅行类别), criteria (评估标准，可选)
- travel_detail: destination (目的地)

规则：
- 如果用户问了"评估"、"推荐"、"对比"相关的，且没有目的地或行业类别，追问
- 如果用户问了具体查询（天气/票务/行程），检查必要参数
- 自然语言描述足够丰富的（如"新能源电池旅游攻略"），槽位完整

用户查询：{query}
识别到的意图：{intents}

输出严格为JSON：
{{"slots_complete": true/false, "missing_slots": ["缺失字段"], "reason": "判断原因"}}
绝对不要添加额外文本！
""")

    # ==================== 冲突检测 ====================

    @staticmethod
    def conflict_detection_prompt():
        """
        冲突检测 —— 检查攻略推荐与各 Agent 实际返回结果之间的矛盾

        输入变量：
            - guide_plan: 攻略 Agent 的推荐方案（含航班建议、日期建议等）
            - agent_results: 各 Agent 返回的实际数据（JSON格式）
            - user_budget: 用户预算（可选）

        输出：JSON
        {
            "has_conflict": true/false,
            "conflicts": [
                {
                    "type": "resource_unavailable" | "budget_exceeded" | "schedule_mismatch",
                    "description": "冲突描述",
                    "source": "来源Agent",
                    "suggestion": "建议调整方案"
                }
            ]
        }
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：你是一位智能旅行协调专家。请检查推荐方案与各维度实际数据之间是否存在冲突。

检查维度：
1. 天气数据冲突：推荐方案中声称的天气信息在实际天气查询结果中是否真实有效
2. 票务可用性矛盾：推荐方案中的票务可用性描述与实际票务记录是否一致
3. 行程风险遗漏：实际行程数据中存在负面信息，但推荐方案未提及
4. 逻辑一致性：推荐排名与各维度数据表现是否匹配

攻略方案：
{guide_plan}

各服务实际查询结果：
{agent_results}

用户预算：{user_budget}

输出严格为JSON，不要添加额外文本：
{{
    "has_conflict": true/false,
    "conflicts": [
        {{
            "type": "resource_unavailable",
            "description": "具体冲突描述",
            "source": "来源",
            "severity": "high/medium/low",
            "suggestion": "建议调整方案"
        }}
    ],
    "summary": "无冲突的综合判断 / 有冲突的简要说明"
}}
""")

    # ==================== 推荐总结 ====================

    @staticmethod
    def summarize_guide_prompt():
        """
        推荐结果总结 —— 与 weather/ticket 的总结模板风格一致

        输入变量：
            - query: 用户查询
            - raw_response: Guide Agent 返回的原始数据
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

    # ==================== 推荐生成 ====================

    @staticmethod
    def guide_generation_prompt():
        """
        推荐生成 —— Guide Agent 使用此 prompt 生成旅游攻略方案

        输入变量：
            - city: 目的地或类别
            - days: 评估维度数
            - style: 评估偏好
            - budget: 预算约束
            - constraints: 约束条件（如已有天气信息、票务数据等）
            - retry_context: 重试上下文（前次冲突的描述，用于调整方案）
            - current_date: 当前日期
        """
        return ChatPromptTemplate.from_template(
"""
系统提示：您是一位资深智能旅行专家，请为用户生成一份详细的旅游攻略方案。

要求：
1. 多维度分析：天气数据性、票务可用性、行程风险三个维度综合评估
2. 数据支撑：推荐基于实际查询数据，注明数据来源
3. 风险提示：不隐瞒负面信息，客观呈现风险点
4. 对比分析：横向对比候选旅行的核心指标
5. 最终建议：给出优先级排序和采购建议

约束条件（如有，必须在方案中体现）：
{constraints}

重试上下文（前次方案的问题，本次需要调整）：
{retry_context}

评估对象：{city}
评估维度：{style}
预算约束：{budget}元
当前日期：{current_date}

输出格式要求：
- 使用"## 维度一/二/三"标记各维度
- 每个维度包含：数据概述、关键指标、风险提示
- 最后包含"## 综合推荐"和"## 注意事项"
- 保持中文，结构清晰
""")
