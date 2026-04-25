"""Prompt Injection Defense (Plan 33).

输入层守护：在用户 query 进入 RAG pipeline 前做模式 + 启发式检测，
按 Agent.guard_config.mode 决定：

    off   —— 不检查（兼容老 Agent 默认）
    log   —— 检测但放行，仅记录到 message.metadata.guard
    block —— 检测命中阈值时拒答；前端用预设拒答消息回复用户

设计要点：
  - 纯函数检测，无 DB / LLM / HTTP 依赖；可单元测试
  - 规则按维度独立打分（每个维度 0..1）：综合分 = max(per-rule)
  - 规则集合保守（高 precision 优先）；激进规则放在 score < threshold
    的告警层，不直接 block
  - 中英双语模式覆盖，因为知识库场景常见混合语言
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

GuardMode = Literal["off", "log", "block"]
GuardAction = Literal["allow", "log", "block"]

DEFAULT_BLOCK_THRESHOLD = 0.7   # block 模式下命中分数 ≥ 此值才拦截
DEFAULT_LOG_THRESHOLD = 0.4     # log 模式下命中分数 ≥ 此值才记录


@dataclass
class GuardHit:
    rule: str
    score: float
    snippet: str


@dataclass
class GuardResult:
    action: GuardAction
    score: float
    hits: list[GuardHit] = field(default_factory=list)
    refusal_message: str | None = None


# ── 规则定义 ──────────────────────────────────────────────────────

_INSTRUCTION_OVERRIDE = re.compile(
    r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|rules?|prompts?)"
    r"|忽略(?:所有)?(?:之前|前面|上面)的?(?:指令|规则|提示)"
    r"|不要(?:再)?(?:遵守|遵循|理会).{0,5}(?:指令|规则)"
    r"|(?:重新|重置).{0,5}(?:你的)?(?:指令|身份|角色|系统提示)",
    re.IGNORECASE,
)

_ROLE_HIJACK = re.compile(
    r"(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay\s+as)\s+(?:a\s+)?(?:DAN|jailbreak|developer\s+mode|admin|root|unrestricted|无限制|无审查)"
    r"|你(?:现在)?(?:是|扮演|充当)(?:一个)?(?:DAN|越狱|管理员|root|无限制|无审查)模式?"
    r"|进入.{0,5}(?:开发者|developer|debug|jailbreak|越狱)模式",
    re.IGNORECASE,
)

_SYSTEM_PROMPT_LEAK = re.compile(
    r"(?:show|reveal|print|output|repeat|tell|give)\s+(?:me\s+)?(?:your|the)\s+(?:system\s+prompt|instructions|rules|configuration)"
    r"|(?:打印|展示|输出|告诉我).{0,8}(?:系统提示|系统消息|你的指令|你的规则|system\s+prompt)"
    r"|what\s+(?:is|are)\s+your\s+(?:initial|original|hidden)\s+(?:instructions|prompt|rules)",
    re.IGNORECASE,
)

_DELIMITER_INJECTION = re.compile(
    r"(?:^|\n)\s*(?:###|---|```)\s*(?:system|assistant|instruction)\s*[:：]"
    r"|<\|(?:system|im_start|im_end)\|>"
    r"|<<<\s*(?:SYSTEM|ASSISTANT)\s*>>>",
    re.IGNORECASE,
)

_DATA_EXFIL = re.compile(
    r"(?:list|enumerate|dump)\s+all\s+(?:files|knowledge|documents|api\s+keys|secrets)"
    r"|(?:列出|枚举|导出)(?:所有|全部).{0,5}(?:文件|文档|知识|密钥|api[_\s]?key)"
    r"|read\s+(?:the\s+)?(?:database|env|config)\s+file",
    re.IGNORECASE,
)


_RULES: list[tuple[str, re.Pattern[str], float]] = [
    ("instruction_override", _INSTRUCTION_OVERRIDE, 0.9),
    ("role_hijack",          _ROLE_HIJACK,          0.85),
    ("system_prompt_leak",   _SYSTEM_PROMPT_LEAK,   0.8),
    ("delimiter_injection",  _DELIMITER_INJECTION,  0.7),
    ("data_exfiltration",    _DATA_EXFIL,           0.6),
]


REFUSAL_MESSAGE = (
    "抱歉，我无法处理这个请求 —— 检测到可能的提示词注入或越权指令。"
    "如果你确实想了解相关内容，请换一种自然语言的提问方式。"
)


# ── 主入口 ────────────────────────────────────────────────────────


def evaluate(
    text: str,
    *,
    mode: GuardMode = "off",
    block_threshold: float = DEFAULT_BLOCK_THRESHOLD,
    log_threshold: float = DEFAULT_LOG_THRESHOLD,
) -> GuardResult:
    """对单条用户输入做检测；返回行动决策与命中规则列表。"""
    if not text or mode == "off":
        return GuardResult(action="allow", score=0.0)
    hits: list[GuardHit] = []
    text_norm = text.replace("\u200b", "").replace("\u200c", "")  # 零宽字符净化
    for name, pattern, score in _RULES:
        m = pattern.search(text_norm)
        if m:
            snippet = text_norm[max(0, m.start() - 10) : m.end() + 10]
            hits.append(GuardHit(rule=name, score=score, snippet=snippet[:200]))
    composite = max((h.score for h in hits), default=0.0)
    if mode == "block" and composite >= block_threshold:
        return GuardResult(
            action="block",
            score=composite,
            hits=hits,
            refusal_message=REFUSAL_MESSAGE,
        )
    if composite >= log_threshold:
        return GuardResult(action="log", score=composite, hits=hits)
    return GuardResult(action="allow", score=composite, hits=hits)


def parse_guard_config(raw: dict | None) -> tuple[GuardMode, float, float]:
    """从 Agent.guard_config 解析参数，缺失给安全默认值。"""
    cfg = raw or {}
    mode = str(cfg.get("mode", "off")).lower()
    if mode not in ("off", "log", "block"):
        mode = "off"
    block_threshold = float(cfg.get("block_threshold", DEFAULT_BLOCK_THRESHOLD))
    log_threshold = float(cfg.get("log_threshold", DEFAULT_LOG_THRESHOLD))
    block_threshold = max(0.0, min(1.0, block_threshold))
    log_threshold = max(0.0, min(1.0, log_threshold))
    return mode, block_threshold, log_threshold  # type: ignore[return-value]
