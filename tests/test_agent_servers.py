"""
Agent 服务器测试模块

测试内容：
1. AgentCard 定义验证（纯属性检查，零依赖）
2. Agent 服务器集成测试（需要 MCP 服务器运行 + LLM API 可访问）

运行方式：
    cd smart-travel
    python -m tests.test_agent_servers
"""

import unittest
import sys
import os


# ==================== 1. AgentCard 定义测试（纯属性检查，零依赖） ====================

class TestWeatherAgentCard(unittest.TestCase):
    """测试天气 Agent 的代理卡片定义"""

    def test_agent_card_basic(self):
        """验证代理卡片基本信息"""
        from a2a_server.weather_server import agent_card

        self.assertEqual(agent_card.name, "WeatherAgent")
        self.assertIn("天气", agent_card.description)
        self.assertEqual(agent_card.url, "http://127.0.0.1:5005")
        self.assertEqual(len(agent_card.skills), 1)

    def test_weather_skill_examples(self):
        """验证天气技能示例"""
        from a2a_server.weather_server import agent_card

        skill = agent_card.skills[0]
        self.assertIn("weather", skill.name.lower())
        self.assertIsNotNone(skill.description)
        self.assertGreater(len(skill.examples), 0)


class TestTicketAgentCard(unittest.TestCase):
    """测试票务 Agent 的代理卡片定义"""

    def test_agent_card_skills(self):
        """验证票务代理拥有 3 个技能"""
        from a2a_server.ticket_server import agent_card

        self.assertEqual(agent_card.name, "TicketAgent")
        self.assertEqual(agent_card.url, "http://127.0.0.1:5006")
        self.assertEqual(len(agent_card.skills), 3)

    def test_has_query_skills(self):
        """验证包含查询技能"""
        from a2a_server.ticket_server import agent_card

        skill_names = [s.name for s in agent_card.skills]
        query_skills = [n for n in skill_names if 'query' in n.lower()]
        self.assertEqual(len(query_skills), 3, "应该有3个查询技能")


class TestTripAgentCard(unittest.TestCase):
    """测试行程 Agent 的代理卡片定义"""

    def test_agent_card_skills(self):
        """验证行程代理拥有 4 个技能"""
        from a2a_server.trip_server import agent_card

        self.assertEqual(agent_card.name, "TripAgent")
        self.assertEqual(agent_card.url, "http://127.0.0.1:5007")
        self.assertEqual(len(agent_card.skills), 4)

    def test_has_all_trip_skills(self):
        """验证包含新闻、社媒、行程、风险监控技能"""
        from a2a_server.trip_server import agent_card

        skill_names = [s.name.lower() for s in agent_card.skills]
        self.assertTrue(any('news' in n for n in skill_names), "缺少新闻搜索技能")
        self.assertTrue(any('social' in n for n in skill_names), "缺少社媒监控技能")
        self.assertTrue(any('route' in n for n in skill_names), "缺少行程分析技能")
        self.assertTrue(any('risk' in n for n in skill_names), "缺少风险监控技能")


# ==================== 2. Agent 服务器集成测试 ====================
# 前置条件：
# 1. 对应的 MCP 服务器已启动（天气 8002、票务 8001、行程 8003）
# 2. LLM API 可访问（配置了有效的 DASHSCOPE_API_KEY）

class TestWeatherAgentIntegration(unittest.TestCase):
    """集成测试：天气 Agent 服务器"""

    def test_handle_task_weather_query(self):
        """测试天气 Agent 完整查询流程"""
        import asyncio
        from a2a_server.weather_server import WeatherServer, query_weather
        from python_a2a import Task, TaskState

        # 直接调用 query_weather 异步函数，验证 MCP + LLM 完整链路
        result = asyncio.run(query_weather("北京 2026-05-01 天气"))
        print(result)
        self.assertEqual(result["status"], "success")
        # 验证返回内容包含城市名
        self.assertIn("北京", result["message"])

    def test_weather_server_instance(self):
        """验证天气服务器实例化"""
        from a2a_server.weather_server import WeatherServer
        server = WeatherServer()
        self.assertEqual(server.agent_card.name, "WeatherAgent")


class TestTicketAgentIntegration(unittest.TestCase):
    """集成测试：票务 Agent 服务器"""

    def test_handle_task_ticket_query(self):
        """测试票务 Agent 完整查询流程"""
        import asyncio
        from a2a_server.ticket_server import query_ticket

        result = asyncio.run(query_ticket("北京 到 成都 航班 2026-05-01"))
        self.assertEqual(result["status"], "success")
        # 验证返回内容包含出发和到达城市
        self.assertIn("北京", result["message"])
        self.assertIn("成都", result["message"])

    def test_ticket_server_instance(self):
        """验证票务服务器实例化"""
        from a2a_server.ticket_server import TicketServer
        server = TicketServer()
        self.assertEqual(server.agent_card.name, "TicketAgent")


class TestTripAgentIntegration(unittest.TestCase):
    """集成测试：行程 Agent 服务器"""

    def test_handle_task_trip_query(self):
        """测试行程 Agent 完整查询流程"""
        import asyncio
        from a2a_server.trip_server import query_trip

        result = asyncio.run(query_trip("成都 行程 2026-05-01"))
        self.assertEqual(result["status"], "success")
        self.assertIn("成都", result["message"])

    def test_trip_server_instance(self):
        """验证行程服务器实例化"""
        from a2a_server.trip_server import TripServer
        server = TripServer()
        self.assertEqual(server.agent_card.name, "TripAgent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
