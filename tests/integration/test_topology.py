import pytest

from dev_docs_rag.worker.celery_app import DLQ_TTL_MS, celery_app
from dev_docs_rag.worker.topology import declare_topology

pytestmark = pytest.mark.integration


def test_topology_declares_the_dead_letter_queue_with_ttl():
    declare_topology()

    with celery_app.connection_for_read() as connection:
        channel = connection.channel()
        try:
            declared = channel.queue_declare(queue="index_file.dlq", passive=True)
        finally:
            channel.close()

    assert declared.queue == "index_file.dlq"
    assert DLQ_TTL_MS > 0
