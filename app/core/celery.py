from celery import Celery

from app.core.config import settings

celery_app = Celery("ops_knowledge", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.knowledge.ingestion.tasks.*": {"queue": "document"},
        "app.knowledge.embedding.tasks.*": {"queue": "embedding"},
    },
    task_default_queue="default",
    beat_schedule={
        "consistency-scan-hourly": {
            "task": "app.system.tasks.consistency_scan",
            "schedule": 3600.0,
        },
    },
)
celery_app.autodiscover_tasks(["app.knowledge.ingestion", "app.knowledge.embedding", "app.chat", "app.system"])
