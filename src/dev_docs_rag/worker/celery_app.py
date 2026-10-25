"""Celery application: one work queue for files and one dead-letter queue."""

from celery import Celery
from kombu import Exchange, Queue

from ..config import get_settings

_settings = get_settings()

celery_app = Celery(
    "dev_docs_rag",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
)

_work_exchange = Exchange("devdocs", type="direct")
_dead_exchange = Exchange("devdocs.dlx", type="direct")

# Failures older than a week are dropped: reindex from knowledge/ is the recovery path.
DLQ_TTL_MS = 7 * 24 * 60 * 60 * 1000

celery_app.conf.update(
    task_default_queue="index_file",
    task_queues=(
        Queue(
            "index_file",
            _work_exchange,
            routing_key="index_file",
            queue_arguments={
                "x-dead-letter-exchange": "devdocs.dlx",
                "x-dead-letter-routing-key": "index_file.dlq",
            },
        ),
        Queue(
            "index_file.dlq",
            _dead_exchange,
            routing_key="index_file.dlq",
            queue_arguments={"x-message-ttl": DLQ_TTL_MS},
        ),
    ),
    task_routes={"dev_docs_rag.worker.tasks.index_file": {"queue": "index_file"}},
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.imports = ("dev_docs_rag.worker.tasks",)
