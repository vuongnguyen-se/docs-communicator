"""Event-driven ingestion: S3 "object created" -> SQS queue -> worker Lambda, with a dead-letter queue.

S3 reports every new uploads/<sub>/<documentId>.pdf to the ingest queue, so a document is
verified and indexed even if the browser closes right after its upload. The worker Lambda
lives in api.py with the other functions and reads this queue.

- Suffix filter ".pdf": the worker's own <key>.pdf.metadata.json sidecars do not trigger it.
- A message that fails 3 receives moves to the dead-letter queue; monitoring.py alarms on it.
- Both queues: SQS-managed encryption, TLS only, destroyed with the stack (D-002).
"""

from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_sqs as sqs
from constructs import Construct

UPLOADS_PREFIX = "uploads/"
WORKER_TIMEOUT = Duration.seconds(30)
MAX_RECEIVES = 3


class Ingestion(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, documents_bucket: s3.IBucket) -> None:
        super().__init__(scope, construct_id)

        self.dead_letter_queue = sqs.Queue(
            self,
            "IngestDLQ",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl=True,
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.queue = sqs.Queue(
            self,
            "IngestQueue",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl=True,
            # AWS guidance: at least 6x the consumer's timeout, so a slow batch is not redelivered.
            visibility_timeout=Duration.seconds(WORKER_TIMEOUT.to_seconds() * 6),
            dead_letter_queue=sqs.DeadLetterQueue(
                queue=self.dead_letter_queue, max_receive_count=MAX_RECEIVES
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )
        documents_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.SqsDestination(self.queue),
            s3.NotificationKeyFilter(prefix=UPLOADS_PREFIX, suffix=".pdf"),
        )
