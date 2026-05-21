from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import models

from .context import get_request_context
from .models import AuditLog


def _serialize_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, models.Model):
        return str(value.pk)
    return str(value)


def diff_instances(old, new, field_names=None):
    changes = {}
    meta_fields = new._meta.fields
    for field in meta_fields:
        if field.primary_key:
            continue
        name = field.name
        if field_names is not None and name not in field_names:
            continue
        old_val = getattr(old, name, None)
        new_val = getattr(new, name, None)
        if old_val != new_val:
            changes[name] = [_serialize_value(old_val), _serialize_value(new_val)]
    return changes


def log_event(
    action,
    *,
    instance=None,
    object_type=None,
    object_id=None,
    object_repr=None,
    changes=None,
    user=None,
):
    ctx = get_request_context()
    resolved_user = user if user is not None else ctx.get('user')

    if instance is not None:
        object_type = object_type or instance.__class__.__name__
        object_id = object_id or str(instance.pk)
        object_repr = object_repr or str(instance)[:255]

    AuditLog.objects.create(
        user=resolved_user,
        action=action,
        object_type=object_type or '',
        object_id=str(object_id or ''),
        object_repr=(object_repr or '')[:255],
        changes=changes or {},
        ip_address=ctx.get('ip_address'),
        user_agent=ctx.get('user_agent', ''),
    )


# Thread-local cache: id(instance) -> previous row
_instance_cache = {}


def cache_pre_save_instance(instance):
    if not instance.pk:
        return
    model = instance.__class__
    try:
        old = model.objects.get(pk=instance.pk)
        _instance_cache[id(instance)] = old
    except model.DoesNotExist:
        pass


def pop_cached_instance(instance):
    return _instance_cache.pop(id(instance), None)
