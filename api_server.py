"""
需求：智能旅行助手（Smart Travel）FastAPI后端服务器，提供REST API接口
"""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from contextlib import asynccontextmanager
from typing import Optional
import re

from chat_service import ChatService, GraphChatService
from config import Config
from utils.daily_budget import DailyBudgetMiddleware

# ==================== 延迟初始化（防启动崩溃） ====================
chat_service = None
_startup_ok = False
_startup_error = ""
_service_version = ""

USE_V1 = os.getenv("USE_V1", "").lower() == "true"


def _init_chat_service():
    """初始化 ChatService — 失败不崩溃，记录错误供 /health 暴露"""
    global chat_service, _startup_ok, _startup_error, _service_version
    try:
        if USE_V1:
            chat_service = ChatService()
            _service_version = "v1.0 ChatService (手写编排)"
        else:
            chat_service = GraphChatService()
            _service_version = "v2.0 GraphChatService (LangGraph编排)"
        _startup_ok = True
        print(f"=== SmartTravel 启动: {_service_version} ===")
        print(f"   Agents: {list(chat_service.agent_urls.keys())}")
        print(f"   端口: 8085")
    except Exception as e:
        _startup_error = str(e)
        _startup_ok = False
        print(f"!!! SmartTravel ChatService 初始化失败: {e}")
        print(f"   静态页面和 /health 仍可访问，API 调用将返回 503")


_init_chat_service()


def require_chat_service():
    """API 依赖：ChatService 未就绪时返回 503"""
    if not _startup_ok or chat_service is None:
        raise HTTPException(
            status_code=503,
            detail=f"服务正在启动中，请稍后重试。原因: {_startup_error or '初始化未完成'}"
        )
    return chat_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print(f"   Prometheus: /metrics")
    print(f"   Health: /health")
    yield
    print("=== SmartTravel 关闭中 ===")


app = FastAPI(
    title="Smart Travel API v2.0",
    description="基于 A2A + LangGraph 的智能旅行助手平台 — 支持 Prometheus 监控 + LangSmith 追踪",
    lifespan=lifespan,
)

# 每日演示额度中间件：每 IP 每天最多 30 次查询，防止公开演示 Token 被滥用
_conf = Config()
app.add_middleware(
    DailyBudgetMiddleware,
    redis_url=_conf.redis_url,
    max_queries_per_day=_conf.demo_daily_query_limit,
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")


class ProfileRequest(BaseModel):
    profile: dict


# 闲聊/问候模式（零 LLM 调用，秒回）
GREETING_PATTERNS = [
    (r"^(你好|您好|hi|hello|嗨|嘿|哟)", "你好！我是智能旅行助手，可以帮你查天气、订票、规划行程、推荐攻略，有什么需要？"),
    (r"^(你是谁|你叫什么|who are you)", "我是 Smart Travel Assistant，基于 LangGraph + A2A + MCP 多智能体架构的智能旅行助手。"),
    (r"^(在吗|在不在|有人吗)", "我在！随时为你规划旅程 😊"),
    (r"^(谢谢|感谢|thanks|thank you)", "不客气！旅途中有任何问题随时找我。"),
    (r"^(再见|拜拜|bye|88)", "再见！祝你旅途愉快 ✈️"),
]


def check_greeting(query: str) -> Optional[str]:
    """检测闲聊，返回预设回复（零延迟）"""
    for pattern, response in GREETING_PATTERNS:
        if re.match(pattern, query.strip(), re.IGNORECASE):
            return response
    return None


def validate_and_sanitize(message: str) -> tuple[str, bool]:
    """输入校验 + 清洗，返回 (safe_message, was_flagged)"""
    from utils.security import sanitize_user_input, is_empty_or_noise
    if is_empty_or_noise(message):
        raise HTTPException(status_code=400, detail="输入无效：请提供有意义的查询内容")
    safe, flagged = sanitize_user_input(message)
    return safe, flagged


# ==================== 健康检查 ====================

@app.get("/health")
async def health():
    """健康检查 — 返回各组件状态（不调用 chat_service，避免触发 LLM）"""
    components = {
        "server": "healthy",
        "chat_service": "healthy" if _startup_ok else "unhealthy",
    }
    # 检查 A2A Agent 服务可达性（不阻塞，超时 2s）
    if _startup_ok and chat_service:
        import urllib.request
        for name, url in chat_service.agent_urls.items():
            try:
                # 只做 TCP 连接测试，不做实际 LLM 调用
                urllib.request.urlopen(url, timeout=2)
                components[name] = "healthy"
            except Exception:
                components[name] = "unreachable (Agent 服务可能尚未启动)"

    overall = "ok" if all(v in ("healthy", "reachable") or v.startswith("healthy") for v in components.values()) else "degraded"

    return {
        "status": overall,
        "version": _service_version,
        "components": components,
        "startup_error": _startup_error or None,
    }


# ==================== 静态页面 ====================

@app.get("/")
async def index():
    """返回前端页面"""
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    return FileResponse(os.path.join(static_dir, "index.html"))


# ==================== API 端点 ====================

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """发送消息，获取回复"""
    safe_msg, flagged = validate_and_sanitize(request.message)
    svc = require_chat_service()

    greeting = check_greeting(safe_msg)
    if greeting:
        return {"status": "success", "message": greeting}

    response = await svc.chat(safe_msg)
    return {"status": "success", "message": response}


async def sse_generator(message: str, svc):
    """SSE 生成器，逐字流式返回回复"""
    async for chunk in svc.chat_stream(message):
        yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """发送消息，流式获取回复（SSE）"""
    safe_msg, flagged = validate_and_sanitize(request.message)
    svc = require_chat_service()

    greeting = check_greeting(safe_msg)
    if greeting:
        async def greeting_gen():
            yield f"data: {json.dumps({'chunk': greeting}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(greeting_gen(), media_type="text/event-stream")

    return StreamingResponse(sse_generator(safe_msg, svc), media_type="text/event-stream")


@app.get("/api/memory")
async def get_memory():
    """获取记忆状态"""
    svc = require_chat_service()
    return {"status": "success", "data": svc.get_memory_state()}


@app.post("/api/memory/clear")
async def clear_memory():
    """清空记忆"""
    svc = require_chat_service()
    svc.clear_memory()
    return {"status": "success", "message": "记忆已清空"}


@app.post("/api/memory/profile")
async def update_profile(request: ProfileRequest):
    """更新用户偏好"""
    svc = require_chat_service()
    svc.update_user_profile(request.profile)
    return {"status": "success", "message": "用户偏好已更新"}


@app.get("/api/agents")
async def get_agents():
    """获取代理卡片信息"""
    svc = require_chat_service()
    return {"status": "success", "data": svc.get_agent_cards()}


# ==================== Prometheus 监控 ====================
Instrumentator(
    excluded_handlers=["/metrics", "/health"],
    should_group_status_codes=True,
    should_round_latency_decimals=True,
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

print("Prometheus 指标已暴露: /metrics")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8085, log_level="info")
