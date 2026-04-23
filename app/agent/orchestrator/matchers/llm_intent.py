"""LLM intent classifier — the only non-zero-cost matcher.

Rule-level ``match_config.category`` is compared against the classifier
output. Categories are defined once per Agent (``orchestrator_config.
classifier.categories``); the classifier runs at most once per cascade
(or zero if an earlier zero-cost rule wins) and its result is cached so
multiple llm_intent rules share one call.

Cache key: ``orch_cls:{agent_id}:{sha1(msg.strip().casefold())}`` —
normalization avoids "网络问题 " and "网络问题" being two entries.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

import structlog

from app.agent.orchestrator.matchers.base import MatchInput, MatchResult
from app.core.cache import CacheService

logger = structlog.get_logger(__name__)


@dataclass
class ClassifierOutput:
    category: str
    confidence: float
    cached: bool


CLASSIFY_PROMPT = """You are an intent classifier. Classify the user's message into exactly ONE of these categories.

Categories:
{categories_block}

Respond with ONLY a JSON object: {{"category": "<name>", "confidence": <float 0..1>}}.
If no category fits, use category="__unknown__" with confidence=0.

User message:
{message}
""".strip()


async def classify(
    agent_id: uuid.UUID,
    message: str,
    classifier_cfg: dict,
    db_factory,
) -> ClassifierOutput | None:
    """Returns None if classifier is not configured."""
    if not classifier_cfg:
        return None

    cache_key = _cache_key(agent_id, message)
    ttl = int(classifier_cfg.get("cache_ttl_seconds", 300))
    cache = CacheService()
    try:
        if ttl > 0:
            raw = await cache.redis.get(cache_key)
            if raw:
                payload = json.loads(raw)
                return ClassifierOutput(
                    category=payload["category"],
                    confidence=float(payload["confidence"]),
                    cached=True,
                )
    except Exception:  # noqa: BLE001
        pass  # cache miss path

    # Cache miss — actually call the LLM
    categories = classifier_cfg.get("categories") or []
    block = "\n".join(
        f"- {c['name']}: {c.get('description') or ''}"
        + (
            f"\n  examples: {', '.join(c.get('examples') or [])}"
            if c.get("examples")
            else ""
        )
        for c in categories
    )
    prompt = CLASSIFY_PROMPT.format(categories_block=block, message=message)
    registry_id = uuid.UUID(str(classifier_cfg["model_registry_id"]))

    from app.model.service import ModelService  # lazy — avoid import cycle

    async with db_factory() as db:
        svc = ModelService(db)
        try:
            resp = await svc.chat_by_registry(
                registry_id,
                [{"role": "user", "content": prompt}],
                max_tokens=80, temperature=0,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("orch_classifier_failed", agent_id=str(agent_id), error=str(e))
            return ClassifierOutput(category="__unknown__", confidence=0.0, cached=False)

    content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    out = _parse_output(content)

    try:
        if ttl > 0:
            await cache.redis.set(
                cache_key,
                json.dumps({"category": out.category, "confidence": out.confidence}),
                ex=ttl,
            )
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            await cache.close()
        except Exception:  # noqa: BLE001
            pass

    return out


def _cache_key(agent_id: uuid.UUID, message: str) -> str:
    h = hashlib.sha1(message.strip().casefold().encode("utf-8")).hexdigest()
    return f"orch_cls:{agent_id}:{h}"


def _parse_output(content: str) -> ClassifierOutput:
    # LLM sometimes wraps JSON in markdown fences; be forgiving.
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`").lstrip("json").strip()
    try:
        obj = json.loads(content)
        return ClassifierOutput(
            category=str(obj.get("category") or "__unknown__"),
            confidence=float(obj.get("confidence") or 0.0),
            cached=False,
        )
    except Exception:  # noqa: BLE001
        return ClassifierOutput(category="__unknown__", confidence=0.0, cached=False)


async def match_llm_intent(rule_match_config: dict, input: MatchInput) -> MatchResult:
    """Pure match path — classification itself is done once per request
    by the engine and its result passed in via ``input.metadata`` under
    a private key. See engine.py.
    """
    expected_category = rule_match_config["category"]
    classifier_result = (input.agent_orchestrator_config or {}).get("_classifier_result")
    if not classifier_result:
        return MatchResult(matched=False, details={"reason": "classifier_not_run"})
    threshold = (
        (input.agent_orchestrator_config or {})
        .get("classifier", {})
        .get("confidence_threshold", 0.6)
    )
    matched = (
        classifier_result["category"] == expected_category
        and classifier_result["confidence"] >= threshold
    )
    return MatchResult(
        matched=matched,
        details={
            "category": classifier_result["category"],
            "confidence": classifier_result["confidence"],
            "threshold": threshold,
            "cached": classifier_result.get("cached", False),
        },
    )
