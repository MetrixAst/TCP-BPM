from celery import shared_task


@shared_task(name="esigner_poll_pending_signings_task")
def poll_pending_signings():
    from esigner.services import poll_pending_signings
    poll_pending_signings()