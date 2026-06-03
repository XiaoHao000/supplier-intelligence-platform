"""
需求：实现基于MCP的票务查询服务器，提供航班查询、航班状态、服务评分功能
思路步骤：
1. 导入必要的模块和库
2. 初始化配置和日志记录器
3. 创建TicketService类（封装数据库操作逻辑）
4. 实现参数化查询方法（query_flights、query_flight_status、query_service_score）
5. 定义票务相关工具函数
6. 创建create_ticket_mcp_server函数（创建MCP服务器，注册所有工具）
7. 主函数（启动MCP服务器）
"""
import json
from fastmcp import FastMCP
from config import Config
from create_logger import logger
from mcp_server.base_mcp_server import BaseMCPService

conf = Config()


# 票务查询服务类（继承 BaseMCPService，复用连接管理和 SQL 执行）
class TicketService(BaseMCPService):
    def __init__(self):
        super().__init__()  # BaseMCPService 自动处理 MySQL 连接和自动重连

    # 查询航班信息
    def query_flights(self, destination: str, date: str = None, flight_name: str = None) -> str:
        sql = ("SELECT id, destination, flight_number, flight_name, ticket_price, "
               "departure_date, actual_departure_date, available_seats, change_cancel_rate, "
               "service_score, on_time_departure, user_rating "
               "FROM flight_tickets "
               "WHERE destination = %s")
        params = [destination]
        if date:
            sql += " AND departure_date = %s"
            params.append(date)
        if flight_name:
            sql += " AND flight_name LIKE %s"
            params.append(f"%{flight_name}%")
        sql += " ORDER BY departure_date DESC"
        return self._execute_query(sql, params)

    # 查询航班状态
    def query_flight_status(self, destination: str, flight_number: str = None) -> str:
        sql = ("SELECT id, destination, flight_number, flight_name, ticket_price, "
               "departure_date, actual_departure_date, available_seats, change_cancel_rate, "
               "service_score, on_time_departure, user_rating "
               "FROM flight_tickets "
               "WHERE destination = %s")
        params = [destination]
        if flight_number:
            sql += " AND flight_number = %s"
            params.append(flight_number)
        sql += " ORDER BY departure_date DESC"
        return self._execute_query(sql, params)

    # 服务评分查询
    def query_service_score(self, destination: str, min_score: float = None) -> str:
        sql = ("SELECT id, destination, flight_number, flight_name, "
               "service_score, change_cancel_rate, user_rating, departure_date "
               "FROM flight_tickets "
               "WHERE destination = %s")
        params = [destination]
        if min_score is not None:
            sql += " AND service_score >= %s"
            params.append(min_score)
        sql += " ORDER BY service_score DESC"
        return self._execute_query(sql, params)


# 创建票务查询MCP服务器
def create_ticket_mcp_server():
    # 创建FastMCP实例
    ticket_mcp = FastMCP(name="TicketTools",
                         instructions="票务查询工具，支持航班查询、航班状态、服务评分。基于 flight_tickets 表。",
                         )

    # 实例化票务查询服务对象
    service = TicketService()

    @ticket_mcp.tool(
        name="query_flights",
        description="查询旅行航班信息，参数：destination(目的地), date(出发日期，格式YYYY-MM-DD，可选), flight_name(航空公司，可选)"
    )
    def query_flights(destination: str, date: str = None, flight_name: str = None) -> str:
        logger.info(f"查询航班信息: destination={destination}, date={date}, airline={flight_name}")
        return service.query_flights(destination, date, flight_name)

    @ticket_mcp.tool(
        name="query_flight_status",
        description="查询航班状态，参数：destination(目的地), flight_number(航班号，可选)"
    )
    def query_flight_status(destination: str, flight_number: str = None) -> str:
        logger.info(f"查询航班状态: destination={destination}, flight={flight_number}")
        return service.query_flight_status(destination, flight_number)

    @ticket_mcp.tool(
        name="query_service_score",
        description="查询旅行服务评分，参数：destination(目的地), min_score(最低服务评分，可选，1-10)"
    )
    def query_service_score(destination: str, min_score: float = None) -> str:
        logger.info(f"查询服务评分: destination={destination}, min_score={min_score}")
        return service.query_service_score(destination, min_score)

    @ticket_mcp.tool(
        name="book_flight",
        description="预订航班机票"
    )
    def book_flight(destination: str, flight_number: str, flight_name: str, ticket_price: float, departure_date: str) -> str:
        logger.info(f"预订机票: {destination}, {flight_number}, {flight_name}, {ticket_price}, {departure_date}")
        logger.info(f"机票预订成功！")
        return f"机票预订成功！目的地：{destination}，航班号：{flight_number}，航司：{flight_name}，票价：{ticket_price}元，出发日期：{departure_date}。"

    @ticket_mcp.tool(
        name="check_in",
        description="办理值机手续"
    )
    def check_in(flight_number: str, actual_departure_date: str, available_seats: int, service_score: float) -> str:
        logger.info(f"值机: {flight_number}, {actual_departure_date}, seats_left={available_seats}, score={service_score}")
        logger.info(f"值机成功！")
        return f"值机成功！航班号：{flight_number}，实际出发日期：{actual_departure_date}，余票：{available_seats}张，服务评分：{service_score}。"

    @ticket_mcp.tool(
        name="record_feedback",
        description="记录用户服务反馈"
    )
    def record_feedback(flight_number: str, change_cancel_rate: float, user_rating: float, service_result: str) -> str:
        logger.info(f"记录反馈: {flight_number}, change_cancel_rate={change_cancel_rate}, user_rating={user_rating}, result={service_result}")
        logger.info(f"反馈记录成功！")
        return f"反馈记录成功！航班号：{flight_number}，退改签率：{change_cancel_rate}%，用户评分：{user_rating}，反馈：{service_result}。"

    # 打印服务器信息
    logger.info("=== 票务查询MCP服务器信息 ===")
    logger.info(f"名称: {ticket_mcp.name}")
    logger.info(f"描述: {ticket_mcp.instructions}")

    # 运行服务器
    try:
        print("服务器已启动，请访问 http://127.0.0.1:8001/mcp")
        ticket_mcp.run(transport="http", host="0.0.0.0", port=8001)
    except Exception as e:
        print(f"服务器启动失败: {e}")


if __name__ == '__main__':
    create_ticket_mcp_server()
