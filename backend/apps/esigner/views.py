import json
import logging

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def esigner_webhook(request):
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return HttpResponseBadRequest("invalid json")

    try:
        services.handle_webhook(payload)
    except Exception:
        logger.exception("esigner webhook processing failed, payload=%s", payload)
    return JsonResponse({"ok": True})