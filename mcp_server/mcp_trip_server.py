"""
需求：实现基于MCP的行程线路查询服务器，提供新闻搜索、社媒监控、情感分析功能

架构说明：
    本服务器是智能旅行助手中的行程线路查询 MCP 服务器，运行在 8003 端口。
    与票务查询 MCP 保持一致的架构模式，采用混合数据源：

    - 新闻搜索：从 MySQL travel_news 表查询
    - 社媒监控：从 Milvus 向量数据库进行语义检索（RAG 模式）
    - 情感分析：从 MySQL destination_ratings 表查询
    - 风险预警：从 MySQL travel_advisories 表查询

    RAG 系统说明：
    - 使用 Milvus 本地向量数据库存储旅游攻略文档
    - 文档数据在初始化时通过 Qwen Embedding API 生成 1024 维向量
    - 用户查询时，将查询文本也生成向量，通过 COSINE 相似度匹配最相关的文档
    - 优势：用户可以用自然语言描述需求（如"最近有没有行程体验问题"），系统自动匹配最相关的行程文档
"""

# ==================== 导入依赖 ====================
import json  # JSON 处理
import requests  # HTTP 请求，用于调用 Qwen Embedding API

from pymilvus import connections, Collection  # Milvus 向量数据库客户端
from fastmcp import FastMCP

from config import Config  # 项目配置
from create_logger import logger  # 日志模块
from mcp_server.base_mcp_server import BaseMCPService

conf = Config()  # 全局配置实例


# ==================== Milvus + Embedding 配置 ====================
MILVUS_HOST = conf.milvus_host
MILVUS_PORT = conf.milvus_port
COLLECTION_NAME = "smart_travel_docs"
EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
EMBEDDING_DIM = 1024

# v2.0 RAG Reranker（懒加载，首次调用 search_destination_docs_in_milvus 时初始化）
_reranker = None


def _get_reranker():
    """懒加载 Reranker 单例"""
    global _reranker
    if _reranker is None:
        try:
            from rag.reranker import BGEReranker
            _reranker = BGEReranker()
            if _reranker.is_available:
                logger.info("BGE-Reranker 已启用（两阶段检索：ANN + Cross-Encoder）")
            else:
                logger.info("BGE-Reranker 不可用，回退到单阶段 ANN 检索")
        except ImportError:
            logger.info("FlagEmbedding 未安装，回退到单阶段 ANN 检索")
            _reranker = False  # 标记已尝试
    return _reranker if _reranker and _reranker is not False else None


def get_embedding(text: str) -> list:
    """
    调用 Qwen Embedding API 生成文本向量（1024 维）

    参数：
        text (str): 需要生成向量的文本

    返回值：
        list: 1024 维浮点向量
    """
    headers = {
        "Authorization": f"Bearer {conf.api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "text-embedding-v3",
        "input": [text],
        "dimensions": EMBEDDING_DIM
    }
    response = requests.post(EMBEDDING_URL, headers=headers, json=payload, timeout=30)
    result = response.json()
    return result["data"][0]["embedding"]


def search_destination_docs_in_milvus(query_text: str, destination: str = None, limit: int = 5) -> list:
    """
    在 Milvus 中进行语义搜索，找到最匹配的旅游攻略文档

    工作流程：
    1. 将用户查询文本通过 Qwen API 转换为 1024 维向量
    2. 在 Milvus 中用 COSINE 相似度搜索最相近的文档
    3. 返回匹配结果

    参数：
        query_text (str): 用户查询文本（如"产品行程体验反馈"）
        destination (str, optional): 目的地过滤条件
        limit (int): 返回结果数量，默认 5

    返回值：
        list: 匹配的文档列表
    """
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    collection = Collection(COLLECTION_NAME)
    collection.load()

    # 构建输出字段
    output_fields = ["trip_id", "destination", "category", "doc_type", "rating", "content"]

    # 搜索
    results = collection.search(
        data=[get_embedding(query_text)],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 10}},
        limit=limit,
        output_fields=output_fields,
        expr=f'destination == "{destination}"' if destination else None
    )

    # 将搜索结果转换为字典列表
    doc_list = []
    for hits in results:
        for hit in hits:
            doc_list.append({
                "trip_id": hit.entity.get("trip_id"),
                "destination": hit.entity.get("destination"),
                "category": hit.entity.get("category"),
                "doc_type": hit.entity.get("doc_type"),
                "rating": hit.entity.get("rating"),
                "content": hit.entity.get("content"),
                "similarity": round(hit.distance, 4),
            })

    # v2.0 Reranker：二阶段精排
    reranker = _get_reranker()
    if reranker and doc_list:
        logger.info(f"Reranker 精排：{len(doc_list)} candidates → top-{min(limit, len(doc_list))}")
        doc_list = reranker.rerank(query_text, doc_list, top_n=limit)

    return doc_list


# ==================== 行程线路查询服务类 ====================
class TripService(BaseMCPService):
    """
    行程线路查询服务类（继承 BaseMCPService，复用连接管理和 SQL 执行）

    混合数据源架构：
    - 新闻搜索、情感分析、风险预警：从 MySQL 数据库真实查询
    - 社媒监控：从 Milvus 向量数据库语义检索（RAG）
    """

    def __init__(self):
        super().__init__()  # BaseMCPService 自动处理 MySQL 连接和自动重连

    # ========== 新闻搜索（MySQL） ==========

    def search_news(self, destination: str, date: str = None, trip: str = None) -> str:
        """
        查询旅行相关新闻（从 MySQL travel_news 表查询）
        """
        logger.info(f"搜索新闻: destination={destination}, date={date}, sentiment={trip}")
        sql = ("SELECT id, destination, source, title, content, sentiment, "
               "risk_level, publish_date, url, keywords "
               "FROM travel_news "
               "WHERE destination = %s")
        params = [destination]
        if date:
            sql += " AND publish_date >= %s"
            params.append(date)
        if trip:
            sql += " AND trip = %s"
            params.append(trip)
        sql += " ORDER BY publish_date DESC"
        return self._execute_query(sql, params)

    # ========== 社媒监控（Milvus RAG） ==========

    def search_social_media(self, query_text: str, destination: str = None) -> str:
        """
        社媒监控搜索（从 Milvus 向量数据库进行语义检索）

        参数：
            query_text (str): 用户查询描述，如"最近有没有负面消息"
            destination (str, optional): 目的地过滤

        返回值：
            str: JSON 字符串，包含匹配的文档列表
        """
        logger.info(f"社媒监控: query='{query_text}', destination='{destination}'")
        try:
            doc_list = search_destination_docs_in_milvus(query_text, destination, limit=5)

            if doc_list:
                return json.dumps({"status": "success", "data": doc_list}, ensure_ascii=False)
            else:
                return json.dumps({
                    "status": "no_data",
                    "message": f"未找到匹配的社媒行程数据。{'请确认目的地，' if destination else ''}或尝试其他搜索条件。"
                }, ensure_ascii=False)

        except Exception as e:
            logger.error(f"社媒监控 RAG 查询错误: {str(e)}")
            return json.dumps({"status": "error", "message": f"社媒监控查询出错：{str(e)}"}, ensure_ascii=False)

    # ========== 情感分析（MySQL） ==========

    def search_route(self, destination: str, period: str = None) -> str:
        """
        查询旅行情感分析数据（从 MySQL destination_ratings 表查询）
        """
        logger.info(f"情感分析: destination={destination}, period={period}")
        sql = ("SELECT id, destination, period, positive_ratio, negative_ratio, "
               "neutral_ratio, overall_score, trending, sample_count, update_time "
               "FROM destination_ratings "
               "WHERE destination = %s")
        params = [destination]
        if period:
            sql += " AND period = %s"
            params.append(period)
        sql += " ORDER BY update_time DESC"
        return self._execute_query(sql, params)

    # ========== 风险预警方法 ==========

    def monitor_risk(self, destination: str, alert_level: str = None) -> str:
        """
        查询旅行风险预警信息（从 MySQL travel_advisories 表查询）
        """
        logger.info(f"风险监控: destination={destination}, advisory_level={alert_level}")
        sql = ("SELECT id, destination, advisory_type, advisory_level, description, "
               "trigger_date, status, suggestion "
               "FROM travel_advisories "
               "WHERE destination = %s")
        params = [destination]
        if alert_level:
            sql += " AND alert_level = %s"
            params.append(alert_level)
        sql += " ORDER BY trigger_date DESC"
        return self._execute_query(sql, params)

    def alert_risk(self, destination: str, alert_type: str, alert_level: str, description: str) -> str:
        """创建风险预警"""
        logger.info(f"创建风险预警: {destination}, {alert_type}, {alert_level}")
        return f"风险预警已创建！旅行：{destination}，类型：{alert_type}，等级：{alert_level}。描述：{description}"

    def report_trip(self, destination: str, period: str) -> str:
        """生成行程报告"""
        logger.info(f"生成行程报告: {destination}, {period}")
        return f"行程报告已生成！旅行：{destination}，周期：{period}。"


# ==================== 创建 MCP 服务器 ====================
def create_trip_mcp_server():
    """
    创建并启动行程线路查询 MCP 服务器
    """
    trip_mcp = FastMCP(
        name="TripTools",
        instructions="行程线路查询工具，支持新闻搜索、社媒监控、情感分析。新闻和情感分析通过 MySQL，社媒监控通过 Milvus 语义检索。",
    )

    service = TripService()

    # ========== 注册查询工具 ==========

    @trip_mcp.tool(
        name="search_news",
        description="搜索旅行相关新闻，参数：destination(目的地), date(开始日期，格式YYYY-MM-DD，可选), trip(情感倾向，可选：正面/中性/负面)"
    )
    def search_news(destination: str, date: str = None, trip: str = None) -> str:
        return service.search_news(destination, date, trip)

    @trip_mcp.tool(
        name="search_social_media",
        description="社媒监控搜索（语义搜索），参数：query_text(查询描述，如'行程体验反馈'、'安全隐患')，destination(目的地过滤，可选)"
    )
    def search_social_media(query_text: str, destination: str = None) -> str:
        return service.search_social_media(query_text, destination)

    @trip_mcp.tool(
        name="search_route",
        description="分析旅行情感评分，参数：destination(目的地), period(统计周期，可选，如'2025Q1')"
    )
    def search_route(destination: str, period: str = None) -> str:
        return service.search_route(destination, period)

    # ========== 注册风险预警工具 ==========

    @trip_mcp.tool(
        name="monitor_risk",
        description="监控旅行风险预警信息，参数：destination(目的地), alert_level(预警等级，可选：红/橙/黄)"
    )
    def monitor_risk(destination: str, alert_level: str = None) -> str:
        logger.info(f"风险监控: {destination}, alert_level={alert_level}")
        return service.monitor_risk(destination, alert_level)

    @trip_mcp.tool(
        name="alert_risk",
        description="创建旅行风险预警"
    )
    def alert_risk(destination: str, alert_type: str, alert_level: str, description: str) -> str:
        logger.info(f"创建风险预警: {destination}, {alert_type}, {alert_level}")
        return service.alert_risk(destination, alert_type, alert_level, description)

    @trip_mcp.tool(
        name="report_trip",
        description="生成旅行行程报告"
    )
    def report_trip(destination: str, period: str) -> str:
        logger.info(f"生成行程报告: {destination}, {period}")
        return service.report_trip(destination, period)

    # 打印服务器信息
    logger.info("=== 行程线路查询MCP服务器信息 ===")
    logger.info(f"名称: {trip_mcp.name}")
    logger.info(f"描述: {trip_mcp.instructions}")

    try:
        print("服务器已启动，请访问 http://127.0.0.1:8003/mcp")
        trip_mcp.run(transport="http", host="0.0.0.0", port=8003)
    except Exception as e:
        print(f"服务器启动失败: {e}")


if __name__ == '__main__':
    create_trip_mcp_server()
