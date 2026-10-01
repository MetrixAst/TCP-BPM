"""Kafka worker reliability fixes from the 2026-08-25 audit:

1. enable_auto_commit=True meant offsets committed on a timer independent of
   whether processing actually finished — a process kill (OOM, pod eviction,
   rolling deploy) between an auto-commit and the end of processing silently
   lost the message. _process_message now commits manually, only after the
   message has been fully handled (success, or failure already requeued).
2. payment_sync/webhook jobs had NO retry at all on exception — only
   whatsapp jobs did. _requeue_job_via_publish extends bounded retry to every
   topic, without dropping _retry_count the way routing through
   enqueue_payment_sync/enqueue_webhook (which build a fixed payload shape
   from named kwargs) would.
"""
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.workers.kafka_worker import (
    MAX_JOB_RETRIES,
    _process_message,
    _requeue_job_via_publish,
)


def _fake_message(topic, value, key=None, partition=0, offset=1):
    return MagicMock(topic=topic, value=value, key=key, partition=partition, offset=offset)


class TestRequeueJobViaPublish:
    def test_gives_up_after_max_retries_without_publishing(self):
        with patch("app.services.job_queue.publish") as publish:
            _requeue_job_via_publish(
                settings.KAFKA_TOPIC_PAYMENTS_SYNC,
                {"job_id": "j1", "_retry_count": MAX_JOB_RETRIES},
                key=None,
            )
            publish.assert_not_called()

    def test_republishes_with_incremented_retry_count_preserving_payload(self):
        with patch("app.services.job_queue.publish", return_value=True) as publish:
            _requeue_job_via_publish(
                settings.KAFKA_TOPIC_PAYMENTS_SYNC,
                {"job_id": "j1", "tenant_id": 5, "period": "2026-08", "_retry_count": 1},
                key=b"5:2026-08",
            )
            publish.assert_called_once()
            topic, sent_payload = publish.call_args[0][:2]
            assert topic == settings.KAFKA_TOPIC_PAYMENTS_SYNC
            assert sent_payload["_retry_count"] == 2
            # Original fields (tenant_id, period, job_id) must survive the
            # requeue — routing this through enqueue_payment_sync instead
            # would have silently dropped _retry_count entirely.
            assert sent_payload["tenant_id"] == 5
            assert sent_payload["period"] == "2026-08"
            assert sent_payload["job_id"] == "j1"
            assert publish.call_args.kwargs.get("key") == "5:2026-08"

    def test_logs_but_does_not_raise_when_publish_fails(self):
        with patch("app.services.job_queue.publish", return_value=False):
            _requeue_job_via_publish(
                settings.KAFKA_TOPIC_WEBHOOK, {"job_id": "j2"}, key=None
            )  # must not raise


class TestProcessMessageCommitsExactlyOnceAfterHandling:
    def test_commits_after_successful_payment_sync(self):
        message = _fake_message(
            settings.KAFKA_TOPIC_PAYMENTS_SYNC, {"tenant_id": 1, "period": "2026-08"}
        )
        consumer = MagicMock()
        with patch(
            "app.workers.kafka_worker.process_payment_sync_job", return_value=None
        ) as process, patch(
            "app.workers.kafka_worker._requeue_job_via_publish"
        ) as requeue:
            _process_message(consumer, message)
        process.assert_called_once()
        requeue.assert_not_called()
        consumer.commit.assert_called_once()

    def test_payment_sync_exception_requeues_and_still_commits(self):
        """Before this fix, an exception on a non-whatsapp topic was only
        logged — no retry at all (see module docstring)."""
        message = _fake_message(
            settings.KAFKA_TOPIC_PAYMENTS_SYNC, {"tenant_id": 1, "period": "2026-08"}
        )
        consumer = MagicMock()
        with patch(
            "app.workers.kafka_worker.process_payment_sync_job",
            side_effect=RuntimeError("1C down"),
        ), patch("app.workers.kafka_worker._requeue_job_via_publish") as requeue:
            _process_message(consumer, message)
        requeue.assert_called_once()
        assert requeue.call_args[0][0] == settings.KAFKA_TOPIC_PAYMENTS_SYNC
        # The offset still commits even though processing failed — we've
        # already requeued the retry as a new message, so it's safe to move
        # past this one.
        consumer.commit.assert_called_once()

    def test_whatsapp_failure_uses_dedicated_requeue_not_generic_one(self):
        message = _fake_message(settings.KAFKA_TOPIC_WHATSAPP, {"notification_id": 1})
        consumer = MagicMock()
        with patch(
            "app.workers.kafka_worker.process_whatsapp_job", return_value=False
        ), patch("app.workers.kafka_worker._requeue_whatsapp_job") as requeue_wa, patch(
            "app.workers.kafka_worker._requeue_job_via_publish"
        ) as requeue_generic:
            _process_message(consumer, message)
        requeue_wa.assert_called_once()
        requeue_generic.assert_not_called()
        consumer.commit.assert_called_once()

    def test_commit_failure_is_swallowed_not_raised(self):
        """A broker hiccup on commit() must not crash the worker loop — the
        message will simply be reprocessed after restart (at-least-once),
        which is the whole point of manual commit."""
        message = _fake_message(settings.KAFKA_TOPIC_WEBHOOK, {"source": "green-api"})
        consumer = MagicMock()
        consumer.commit.side_effect = RuntimeError("broker unreachable")
        with patch("app.workers.kafka_worker.process_webhook_job", return_value=None):
            _process_message(consumer, message)  # must not raise
