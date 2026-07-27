import json
import hashlib
import hmac
import logging

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services

logger = logging.getLogger(__name__)


def _has_valid_webhook_signature(request):
    secret = settings.ESIGNER_WEBHOOK_SECRET
    if not secret:
        logger.error("ESIGNER_WEBHOOK_SECRET is not configured")
        return False

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return hmac.compare_digest(authorization[7:], secret)

    supplied = request.headers.get("X-ESigner-Signature", "")
    if supplied.startswith("sha256="):
        supplied = supplied[7:]
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    return bool(supplied) and hmac.compare_digest(supplied, expected)


@csrf_exempt
@require_POST
def esigner_webhook(request):
    if not _has_valid_webhook_signature(request):
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return HttpResponseBadRequest("invalid json")

    try:
        services.handle_webhook(payload)
    except Exception:
        logger.exception(
            "eSigner webhook processing failed for document_id=%s",
            payload.get("document_id"),
        )
        return JsonResponse({"ok": False, "error": "processing failed"}, status=500)
    return JsonResponse({"ok": True})