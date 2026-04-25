from celery import Celery
from celery.signals import worker_ready

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
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.knowledge.ingestion.tasks.*": {"queue": "document"},
        "app.knowledge.embedding.tasks.*": {"queue": "embedding"},
    },
    task_default_queue="default",
    beat_schedule={
        "consistency-scan": {
            "task": "app.system.tasks.consistency_scan",
            "schedule": 1800.0,  # 30 minutes
        },
        "disk-space-monitor": {
            "task": "app.system.tasks.disk_space_monitor",
            "schedule": 3600.0,  # 1 hour
        },
        "workflow-executions-cleanup": {
            "task": "app.workflow.tasks.cleanup_old_executions",
            "schedule": 3600.0,  # 1 hour; retention itself is days-scale
        },
        "mcp-health-check": {
            "task": "app.mcp.tasks.mcp_health_check",
            "schedule": 300.0,  # 5 min; fast enough to catch offline servers
        },
        "orchestrator-trace-retention": {
            "task": "app.agent.orchestrator.tasks.trace_retention",
            "schedule": 86400.0,  # once per day; retention is days-scale
        },
        "orchestrator-priority-rebalance": {
            "task": "app.agent.orchestrator.tasks.priority_rebalance",
            "schedule": 86400.0,  # daily; rebalance only kicks in on precision collision
        },
        "chunk-score-rebuild": {
            "task": "app.knowledge.governance.tasks.chunk_score_rebuild",
            "schedule": 300.0,  # 5 min — Plan 32 M1.6 near-realtime dynamic score
        },
        "governance-alert-publish": {
            "task": "app.knowledge.governance.tasks.governance_alert_publish_daily",
            "schedule": 86400.0,  # daily — Plan 27 M1 publish alerts to event bus
        },
        "document-lifecycle": {
            "task": "app.knowledge.lifecycle.tasks.document_lifecycle",
            "schedule": 86400.0,  # daily — Plan 32 M3 stale detection + auto-archive
        },
        "redundancy-scan": {
            "task": "app.knowledge.coverage.tasks.redundancy_scan",
            "schedule": 86400.0,  # daily — Plan 26 M1 Layer 5 redundancy detection
        },
        "topic-distribution-scan": {
            "task": "app.knowledge.coverage.tasks.topic_distribution_scan",
            "schedule": 86400.0,  # daily — Plan 26 T2 Layer 5 topic clustering
        },
        "cross-kb-redundancy-scan": {
            "task": "app.knowledge.coverage.tasks.cross_kb_redundancy_scan",
            "schedule": 86400.0,  # daily — Plan 31 cross-KB duplication detection
        },
    },
)
celery_app.autodiscover_tasks(
    [
        "app.knowledge.ingestion", "app.knowledge.embedding",
        "app.knowledge.governance", "app.knowledge.lifecycle",
        "app.knowledge.evaluation", "app.knowledge.chunking",
        "app.knowledge.coverage",
        "app.chat", "app.system",
        "app.workflow", "app.mcp", "app.agent.orchestrator",
    ],
)


@worker_ready.connect
def _start_runtime_config_subscriber(**_kwargs) -> None:
    from app.core.runtime_config import start_sync_subscriber
    start_sync_subscriber()
