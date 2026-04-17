import logging
import re
import sys
from typing import Any

import structlog

from app.core.config import settings

_SENSITIVE_KEYS = re.compile(
    r"(api_key|password|secret|token|hashed_password|access_key|secret_key)",
    re.IGNORECASE,
)


def _sanitize_event_dict(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if isinstance(value, str) and _SENSITIVE_KEYS.search(key):
            event_dict[key] = "***"
        elif isinstance(value, dict):
            for k, v in list(value.items()):
                if isinstance(v, str) and _SENSITIVE_KEYS.search(k):
                    value[k] = "***"
    return event_dict


def setup_logging() -> None:
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        # Render exc_info into 'exception' as a traceback string so
        # logger.exception() actually shows the stack trace in output.
        structlog.processors.format_exc_info,
        _sanitize_event_dict,
    ]

    if settings.DEBUG:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO if not settings.DEBUG else logging.DEBUG)

    for name in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
