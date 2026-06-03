"""自定义 Prometheus 业务指标 — 企业级可观测性核心。
监控维度：
- LLM 调用次数、Token 用量（按 model、node 标签拆分）
- Agent 调用次数、成功/失败率
- API 请求延迟
- 冲突检测触发次数
"""
from prometheus_client import Counter, Gauge, Histogram

# ===== LLM 指标 =====
llm_call_total = Counter(
    "smart_travel_llm_calls_total",
    "LLM 总调用次数",
    ["model", "node"]
)

llm_token_usage = Counter(
    "smart_travel_llm_token_usage_total",
    "LLM Token 用量",
    ["model", "node"]
)

llm_call_duration = Histogram(
    "smart_travel_llm_call_duration_seconds",
    "LLM 调用耗时",
    ["model", "node"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
)

# ===== Agent 指标 =====
agent_call_total = Counter(
    "smart_travel_agent_calls_total",
    "Agent 总调用次数",
    ["agent", "status"]  # status: success / failure / timeout
)

agent_call_duration = Histogram(
    "smart_travel_agent_call_duration_seconds",
    "Agent 调用耗时",
    ["agent"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
)

# ===== API 指标 =====
api_request_duration = Histogram(
    "smart_travel_api_request_duration_seconds",
    "API 请求耗时",
    ["endpoint", "method"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
)

api_requests_total = Counter(
    "smart_travel_api_requests_total",
    "API 总请求数",
    ["endpoint", "method", "status"]
)

# ===== 业务指标 =====
conflict_detected_total = Counter(
    "smart_travel_conflict_detected_total",
    "冲突检测触发次数（攻略 vs 票务）"
)

plan_retry_total = Counter(
    "smart_travel_plan_retry_total",
    "规划回退重试次数"
)

active_sessions = Gauge(
    "smart_travel_active_sessions",
    "当前活跃会话数"
)
