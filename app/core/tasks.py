"""Safe Celery task dispatch — swallows broker connection errors."""
import structlog

logger = structlog.get_logger(__name__)


def safe_delay(task, *args):
    """Dispatch a Celery task. If the broker is unreachable, log a warning instead of crashing."""
    try:
        task.delay(*args)
    except Exception:
        logger.warning("celery_dispatch_failed", task=task.name, args=args)
