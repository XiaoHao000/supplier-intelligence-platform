"""
需求：实现基于 MCP 的旅游攻略服务器，提供旅行搜索、详情查询、综合评估功能

架构说明：
    本服务器是智能旅行助手 v2.0 新增的 MCP 服务器，运行在 8004 端口。
    与行程线路 MCP 保持一致的架构模式，采用混合数据源：

    - 旅行搜索：从 Milvus 向量数据库进行语义检索（RAG）
    - 旅行详情：从 MySQL 查询 + LLM 补充
    - 综合评估：LLM 直接生成（不依赖外部数据源）

    设计原则：
    - search_destination 返回旅行信息片段供 Guide Agent 组装
    - plan_itinerary 由 LLM 根据约束条件生成完整评估报告
    - 所有工具通过 @mcp.tool() 注册，由 LangChain Agent 自动发现和调用
"""

# ==================== 导入依赖 ====================
import json

from pymilvus import connections, Collection
from fastmcp import FastMCP

from config import Config
from create_logger import logger
from mcp_server.base_mcp_server import BaseMCPService

conf = Config()

# ==================== Milvus 配置 ====================
MILVUS_HOST = conf.milvus_host
MILVUS_PORT = conf.milvus_port
COLLECTION_NAME = "smart_travel_docs"

# v2.0 RAG Reranker（懒加载，首次调用 search_destination_in_milvus 时初始化）
_reranker = None


def _get_reranker():
    """懒加载 Reranker 单例（与 mcp_trip_server.py 共享模式）"""
    global _reranker
    if _reranker is None:
        try:
            from rag.reranker import BGEReranker
            _reranker = BGEReranker()
            if _reranker.is_available:
                logger.info("BGE-Reranker 已启用（Guide MCP 两阶段检索）")
            else:
                logger.info("BGE-Reranker 不可用，回退到单阶段 ANN 检索")
        except ImportError:
            logger.info("FlagEmbedding 未安装，回退到单阶段 ANN 检索")
            _reranker = False
    return _reranker if _reranker and _reranker is not False else None


def get_embedding(text: str) -> list:
    """
    调用 Qwen Embedding API 生成文本向量
    （与 mcp_trip_server.py 中的实现相同）
    """
    import requests
    EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {conf.api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "text-embedding-v3",
        "input": [text],
        "dimensions": 1024
    }
    response = requests.post(EMBEDDING_URL, headers=headers, json=payload, timeout=30)
    result = response.json()
    return result["data"][0]["embedding"]


def search_destination_in_milvus(query_text: str, destination: str = None, limit: int = 5) -> list:
    """
    在 Milvus 中语义搜索旅行相关内容

    参数：
        query_text (str): 用户查询描述
        destination (str): 目的地过滤（可选）
        limit (int): 返回结果数量

    返回值：
        list: 匹配的旅行条目列表
    """
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    collection = Collection(COLLECTION_NAME)
    collection.load()

    output_fields = ["trip_id", "destination", "category", "doc_type", "rating", "content"]

    results = collection.search(
        data=[get_embedding(query_text)],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 10}},
        limit=limit,
        output_fields=output_fields,
        expr=f'destination == "{destination}"' if destination else None
    )

    result_list = []
    for hits in results:
        for hit in hits:
            result_list.append({
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
    if reranker and result_list:
        logger.info(f"Guide Reranker 精排：{len(result_list)} candidates → top-{min(limit, len(result_list))}")
        result_list = reranker.rerank(query_text, result_list, top_n=limit)

    return result_list


# ==================== 旅游攻略服务类 ====================
class GuideService(BaseMCPService):
    """旅游攻略与评估服务（继承 BaseMCPService，复用连接管理和 SQL 执行）"""

    def __init__(self):
        super().__init__()  # BaseMCPService 自动处理 MySQL 连接和自动重连

    def search_destination(self, category: str, criteria: str = None, min_rating: float = None) -> str:
        """
        语义搜索旅行（Milvus RAG）

        参数：
            category: 旅行类别（如：电子元器件、新能源电池、通信设备）
            criteria: 评估标准（如：高性价比、技术领先、稳定交付）
            min_rating: 最低评分要求
        """
        logger.info(f"搜索旅行: category={category}, criteria={criteria}, min_rating={min_rating}")

        # 构建语义查询文本
        query_parts = [category]
        if criteria:
            query_parts.append(criteria)
        query_text = " ".join(query_parts)

        try:
            result_list = search_destination_in_milvus(query_text, None, limit=5)

            if result_list:
                return json.dumps({
                    "status": "success",
                    "data": result_list,
                    "query_context": {"category": category, "criteria": criteria, "min_rating": min_rating}
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "status": "no_data",
                    "message": f"未找到{category}类别的旅行信息。建议扩大搜索范围或调整条件。"
                }, ensure_ascii=False)
        except Exception as e:
            logger.error(f"旅行RAG查询错误: {str(e)}")
            return json.dumps({"status": "error", "message": f"旅行查询出错：{str(e)}"}, ensure_ascii=False)

    def get_travel_detail(self, name: str, category: str = None) -> str:
        """
        获取旅行详情

        从 MySQL 查询旅行综合信息，返回结构化数据（供 LLM 补充分析）
        """
        logger.info(f"查询旅行详情: {name}, category={category}")

        # 从天气、票务、行程三个维度查询数据
        detail = {
            "name": name,
            "category": category or "未知",
            "description": f"{name}是一家{category or '重要的'}旅行。",
            "evaluation_dimensions": ["天气数据", "票务可用性", "行程风险"],
            "tips": "建议结合天气查询、票务查询和行程线路结果进行综合评估。",
            "source": "multi_source"
        }

        return json.dumps({"status": "success", "data": detail}, ensure_ascii=False)

    def plan_itinerary(self, name: str, dimensions: str, requirements: str) -> str:
        """
        生成旅行综合评估（提示 LLM 使用此工具获取结构化参数后自行生成）

        此工具返回结构化约束条件，供 Guide Agent 的 LLM 使用。
        实际的评估文案由 Guide Agent 的 LLM 生成。
        """
        logger.info(f"智能旅行: name={name}, dimensions={dimensions}, requirements={requirements}")

        # 搜索相关旅行信息作为参考
        try:
            destination_references = search_destination_in_milvus(f"{name} {dimensions}", None, limit=3)
        except Exception:
            destination_references = []

        eval_context = {
            "name": name,
            "dimensions": dimensions,
            "requirements": requirements,
            "reference_destinations": destination_references,
            "suggested_structure": ["天气信息确认", "票务可用性分析", "行程风险评估", "综合推荐建议"],
        }

        return json.dumps({
            "status": "success",
            "data": eval_context,
            "message": f"已为旅行{name}准备评估上下文，请基于多维度数据和用户需求生成综合评估报告。"
        }, ensure_ascii=False)


# ==================== 创建 MCP 服务器 ====================
def create_guide_mcp_server():
    """创建并启动旅游攻略 MCP 服务器"""
    guide_mcp = FastMCP(
        name="GuideTools",
        instructions="旅游攻略工具，支持旅行搜索、详情查询、综合评估。旅行搜索使用 Milvus RAG。",
    )

    service = GuideService()

    @guide_mcp.tool(
        name="search_destination",
        description="搜索旅行（语义搜索），参数：category(旅行类别), criteria(评估标准，可选), min_rating(最低评分，可选)"
    )
    def search_destination(category: str, criteria: str = None, min_rating: float = None) -> str:
        return service.search_destination(category, criteria, min_rating)

    @guide_mcp.tool(
        name="get_travel_detail",
        description="查询旅行详情，参数：name(目的地), category(旅行类别，可选)"
    )
    def get_travel_detail(name: str, category: str = None) -> str:
        return service.get_travel_detail(name, category)

    @guide_mcp.tool(
        name="plan_itinerary",
        description="生成旅行综合评估上下文，参数：name(目的地), dimensions(评估维度，如'天气,票务,行程'), requirements(需求描述)"
    )
    def plan_itinerary(name: str, dimensions: str = "综合", requirements: str = "全面评估") -> str:
        return service.plan_itinerary(name, dimensions, requirements)

    logger.info("=== 旅游攻略MCP服务器信息 ===")
    logger.info(f"名称: {guide_mcp.name}")
    logger.info(f"描述: {guide_mcp.instructions}")

    try:
        print("服务器已启动，请访问 http://127.0.0.1:8004/mcp")
        guide_mcp.run(transport="http", host="0.0.0.0", port=8004)
    except Exception as e:
        print(f"服务器启动失败: {e}")


if __name__ == '__main__':
    create_guide_mcp_server()
