"""Обновляем список логинов в Auth Gateway, когда пользователи меняются."""

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from account.models import UserAccount


def _schedule_push():
    from account.services.auth_gateway import is_configured

    if is_configured():
        from account.tasks import push_logins_to_gateway

        transaction.on_commit(push_logins_to_gateway.delay)


@receiver(post_save, sender=UserAccount)
def user_saved(sender, instance, created, update_fields=None, **kwargs):
    # last_login обновляется при каждом входе — это не повод пересылать список.
    if update_fields and set(update_fields) <= {'last_login'}:
        return
    _schedule_push()


@receiver(post_delete, sender=UserAccount)
def user_deleted(sender, instance, **kwargs):
    _schedule_push()
