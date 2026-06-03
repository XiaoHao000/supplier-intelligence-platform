"""
输入安全清洗：防 Prompt 注入、控制字符攻击、超长输入。

OWASP Top 10 for LLM Apps 第一条就是 Prompt Injection，
在 API 入口处做纵深防御的第一层清洗。
"""

import re
import unicodedata
from create_logger import logger

# 常见 Prompt 注入特征（启发式检测）
_INJECTION_PATTERNS = [
    r"忽略\s*(所有|之前|上述|上面)\s*(指令|提示|规则|要求)",
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|directives?)",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)",
    r"你\s*现在\s*(是|扮演|变成)\s*(一个|新的|不同的)",
    r"you\s+are\s+now\s+(a\s+)?(different|new|another)",
    r"忘记\s*(所有|一切|你的)\s*(指令|训练|规则)",
    r"forget\s+(all|everything|your)\s+(instructions?|training|rules?)",
    r"system\s*(prompt|message|instruction)\s*:",
    r"<\|im_start\|>|<\|im_end\|>",
    r"\[system\]|\[/system\]",
    r"输出\s*(你的|系统)\s*(提示词|prompt|指令)",
    r"告诉我\s*(你的|系统)\s*(提示词|prompt)",
    r"DAN\s*mode|jailbreak|越狱",
    r"不要\s*(说|回答).*你是.*AI",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

MAX_QUERY_LENGTH = 2000


def sanitize_user_input(text: str) -> tuple[str, bool]:
    """清洗用户输入，返回 (safe_text, was_flagged)。

    四步清洗：
    1. Unicode 控制字符移除（防 Bidi/RTLO 攻击）
    2. NFKC 规范化（全角/半角统一，防同形字符绕过）
    3. 截断至 MAX_QUERY_LENGTH
    4. Prompt 注入特征检测（告警但不阻断 — 误杀率高）

    Returns:
        (safe_text, was_flagged)
    """
    if not text:
        return "", False

    # Step 1: 移除 Unicode 控制字符
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cf", "Cc"))
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", cleaned)

    # Step 2: NFKC 规范化
    normalized = unicodedata.normalize("NFKC", cleaned)

    # Step 3: 截断
    if len(normalized) > MAX_QUERY_LENGTH:
        normalized = normalized[:MAX_QUERY_LENGTH]
        logger.info(f"用户输入截断至 {MAX_QUERY_LENGTH} 字符")

    # Step 4: 注入特征检测
    was_flagged = False
    if _INJECTION_RE.search(normalized):
        logger.warning(f"检测到疑似 Prompt 注入: {normalized[:100]}...")
        was_flagged = True

    return normalized.strip(), was_flagged


def is_empty_or_noise(text: str) -> bool:
    """检测输入是否为空或纯噪声（如乱码、纯符号）"""
    if not text or not text.strip():
        return True
    # 纯符号/标点/数字（无有效中文或英文）
    stripped = re.sub(r"[\s\d\W_]+", "", text)
    return len(stripped) < 2
