# 多智能体智能旅行助手 — Multi-Agent Smart Travel Assistant

基于 LangGraph + A2A + MCP 的多智能体协同旅行助手，天气查询、票务预订、行程规划、旅游攻略一站式服务。14 容器微服务编排，Send API 并行派发 4 Agent 独立执行。

## 🚀 快速开始

### 环境要求

- Docker & Docker Compose ≥ 2.0
- Python 3.11+
- 8GB+ 内存

### 一键部署

```bash
git clone https://github.com/XiaoHao000/smart-travel-assistant.git
cd smart-travel-assistant

cp .env.template .env
# 编辑 .env，填入 API_KEY

docker-compose up -d
```

首次启动拉取镜像约 3-5 分钟，14 个容器自动编排：

```
MySQL 8.0 · etcd · MinIO · Milvus 2.4
weather-mcp · ticket-mcp · trip-mcp · guide-mcp
weather-a2a · ticket-a2a · trip-a2a · guide-a2a
api-server（端口 8085）
```

### 初始化数据

```bash
docker exec -it smart-travel-api python data/init_milvus.py
```

MySQL 种子数据通过 `docker-compose` 自动挂载 `data/init_mysql.sql` 初始化。

### 验证

```bash
curl -X POST http://localhost:8085/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "北京明天天气怎么样？帮我查一下去成都的机票"}'
```

---

## 🏗 架构

```
用户 → FastAPI (SSE 流式)
         ↓
    LangGraph StateGraph（9 节点）
         ↓
    Send API 并行派发 → 4× A2A Agent
         ↓
    4× MCP Server（共享基类，零重复代码）
         ↓
    MySQL + Milvus + BGE-Reranker
```

### 核心特性

- **LangGraph StateGraph 编排**：9 节点声明式图，含冲突检测与回退重规划回路
- **Send API 并行派发**：天气/票务/行程/攻略独立 Agent 并行执行，互不阻塞
- **A2A + MCP 双层协议**：A2A Agent 调用 MCP 参数化工具，LLM 自动提取参数
- **Milvus 向量检索 + BGE-Reranker**：语义搜索旅游攻略，Cross-Encoder 精排提升精度
- **流式 SSE 输出**：FastAPI StreamingResponse 逐字推送，打字机效果
- **演示安全**：Redis 每日额度控制 + 输入安全清洗

### 项目结构

```
├── graph/                     # LangGraph 编排
│   ├── state.py               # AgentState 定义
│   ├── nodes.py               # 9 节点实现
│   ├── prompts.py             # 攻略 / 冲突检测提示词
│   └── graph_builder.py       # StateGraph + 条件边
├── mcp_server/                # MCP 工具层
│   ├── base_mcp_server.py     # 共享基类（连接池/SQL/序列化）
│   └── mcp_*_server.py        # 天气/票务/行程/攻略
├── a2a_server/                # A2A Agent 层
├── rag/
│   └── reranker.py            # BGE-Reranker-v2-m3
├── api_server.py              # FastAPI 入口
├── chat_service.py            # GraphChatService
├── docker-compose.yml
└── Dockerfile
```

## 🛠 技术栈

| 层级 | 技术 |
|---|---|
| 编排 | LangGraph StateGraph + Send API |
| 协议 | A2A (python-a2a) + MCP (FastMCP) |
| 检索 | Milvus IVF_FLAT + BGE-Reranker-v2-m3 |
| 数据库 | MySQL 8.0 |
| 后端 | FastAPI + SSE Streaming |
| LLM | Qwen3-Max（OpenAI 兼容接口） |
| 部署 | Docker Compose（14 services） |

## 📄 License

MIT
