"""Safe Celery task dispatch — swallows broker connection errors."""
import structlog

logger = structlog.get_logger(__name__)


def safe_delay(task, *args):
    """Dispatch a Celery task. If the broker is unreachable, log a warning
    (with stack trace so the dispatch root cause is debuggable) instead of
    crashing the request.

    NOTE: callers SHOULD NOT silently rely on this — a swallowed dispatch
    means the task never runs. Watch for ``celery_dispatch_failed`` events
    in API logs; if seen, the document/agent/etc. that triggered the call
    will appear stuck in pending forever from the user's perspective.
    """
    try:
        task.delay(*args)
    except Exception:
        logger.warning(
            "celery_dispatch_failed",
            task=task.name, args=args, exc_info=True,
        )
