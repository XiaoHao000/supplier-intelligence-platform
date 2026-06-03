"""
Smart Travel v2.0 MCP 共享基类

将 ticket/weather/trip/guide 四个 MCP Server 的公共模式提取出来：
- MySQL 连接管理 + 自动重连
- SQL 执行 + JSON 序列化
- 日期/Decimal 类型处理
- FastMCP 工具注册工厂

设计要点：
    v1.0 的三个 MCP Server 各自独立实现 MySQL 连接和查询逻辑，
    存在连接管理、日期序列化等重复代码。v2.0 提取 BaseMCPService 基类，
    统一连接池、SQL 执行、JSON 序列化。新增 Guide MCP Server 时只需
    继承基类并注册工具——开发效率提升、连接泄漏风险降低。"

使用方式：
    from mcp_server.base_mcp_server import BaseMCPService

    class TicketService(BaseMCPService):
        def query_train(self, ...):
            sql = "SELECT ... FROM travel_info WHERE ..."
            return self._execute_query(sql, params)
"""

import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

import mysql.connector
from fastmcp import FastMCP

from config import Config
from create_logger import logger

conf = Config()


def _default_encoder(value):
    """处理特殊类型（日期、Decimal等）转换为字符串"""
    if isinstance(value, (date, datetime, timedelta, Decimal)):
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(value, date):
            return value.strftime('%Y-%m-%d')
        elif isinstance(value, timedelta):
            return str(value)
        elif isinstance(value, Decimal):
            return float(value)
    return value


class DateEncoder(json.JSONEncoder):
    """JSON 编码器：处理日期类型的序列化"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        elif isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class BaseMCPService:
    """
    MCP 工具服务基类

    提取 MySQL 连接管理、SQL 执行、JSON 序列化的公共逻辑。
    子类只需实现具体的业务查询方法。
    """

    def __init__(self, db_config: dict = None):
        """
        Args:
            db_config: 数据库配置字典，默认从 Config 读取
        """
        if db_config is None:
            db_config = {
                "host": conf.host,
                "user": conf.user,
                "password": conf.password,
                "database": conf.database,
                "port": conf.port,
            }

        self._db_config = db_config
        self._conn = None
        self._connect()

    def _connect(self):
        """建立数据库连接"""
        try:
            self._conn = mysql.connector.connect(**self._db_config)
            logger.info(f"数据库连接成功: {self._db_config.get('host')}:{self._db_config.get('port')}/{self._db_config.get('database')}")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            self._conn = None

    def _ensure_connection(self):
        """确保连接有效，断开则自动重连"""
        if self._conn is None:
            self._connect()
            return

        try:
            self._conn.ping(reconnect=True, attempts=3, delay=1)
        except Exception:
            logger.warning("数据库连接断开，尝试重连...")
            self._connect()

    @property
    def conn(self):
        """获取数据库连接（自动重连）"""
        self._ensure_connection()
        return self._conn

    def _execute_query(self, sql: str, params: list = None) -> str:
        """
        执行 SQL 查询，返回 JSON 格式结果

        标准化处理：
        - 参数化查询（防 SQL 注入）
        - 日期/Decimal 类型转换
        - 统一 JSON 响应格式 {"status": "success"/"no_data"/"error", ...}

        Args:
            sql: SQL 语句（使用 %s 占位符）
            params: 参数列表

        Returns:
            str: JSON 字符串
        """
        try:
            cursor = self.conn.cursor(dictionary=True)
            cursor.execute(sql, params or [])
            results = cursor.fetchall()
            cursor.close()

            # 处理特殊类型
            for row in results:
                for key, value in row.items():
                    row[key] = _default_encoder(value)

            if results:
                return json.dumps(
                    {"status": "success", "data": results},
                    cls=DateEncoder,
                    ensure_ascii=False
                )
            else:
                return json.dumps(
                    {"status": "no_data", "message": "未找到数据，请确认查询条件。"},
                    ensure_ascii=False
                )

        except Exception as e:
            logger.error(f"SQL 查询错误: {str(e)} | SQL: {sql[:200]}")
            return json.dumps(
                {"status": "error", "message": str(e)},
                ensure_ascii=False
            )

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# ==================== MCP Server 工厂函数 ====================

def create_mcp_server(name: str, instructions: str, tools: list, port: int = None) -> FastMCP:
    """
    统一创建 MCP Server 的工厂函数

    封装 FastMCP 的创建 + 工具注册流程，减少样板代码。

    Args:
        name: MCP Server 名称
        instructions: 系统指令（描述工具用途和规则）
        tools: 工具注册列表，格式：
            [{"name": "tool_name", "description": "工具描述", "func": callable}, ...]
        port: 运行端口（可选，仅在直接运行时使用）

    Returns:
        FastMCP 实例

    Example:
        service = TicketService()
        tools = [
            {"name": "query_train", "description": "查询火车票",
             "func": service.query_train},
        ]
        mcp = create_mcp_server("TicketTools", "票务查询工具", tools)
    """
    mcp = FastMCP(name=name, instructions=instructions)

    for tool_def in tools:
        mcp.tool(
            name=tool_def["name"],
            description=tool_def["description"]
        )(tool_def["func"])

    logger.info(f"MCP Server 创建完成: {name}, 注册 {len(tools)} 个工具")
    return mcp
