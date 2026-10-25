"""Declare the RabbitMQ topology explicitly.

Celery declares only the queues it consumes, so a worker started with ``-Q index_file``
never creates ``index_file.dlq`` and dead-lettered messages are dropped.
"""

from .celery_app import celery_app


def declare_topology() -> None:
    """Create the exchanges, the work queue and its dead-letter queue."""
    with celery_app.connection_for_write() as connection:
        channel = connection.channel()
        try:
            for queue in celery_app.conf.task_queues:
                queue(channel).declare()
        finally:
            channel.close()


def main() -> None:
    """Entry point for the one-shot compose service."""
    declare_topology()
    print("rabbitmq topology declared")


if __name__ == "__main__":
    main()
