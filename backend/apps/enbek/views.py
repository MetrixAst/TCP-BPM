from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

MOCK_USERNAME = "test"
MOCK_PASSWORD = "test"
MOCK_TOKEN = "mock_token_123"


def _json_response(data, status=200, safe=True):
    return JsonResponse(
        data,
        status=status,
        safe=safe,
        json_dumps_params={"ensure_ascii": False}
    )


def _get_bearer_token(request):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "", 1).strip()
    return None


def _is_authorized(request):
    return _get_bearer_token(request) == MOCK_TOKEN


@csrf_exempt
def login(request):
    if request.method != "POST":
        return _json_response(
            {"error": "Method not allowed. Use POST."},
            status=405
        )

    try:
        body = request.body.decode("utf-8") if request.body else "{}"
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_response(
            {"error": "Invalid JSON body."},
            status=400
        )

    username = data.get("username")
    password = data.get("password")

    if username != MOCK_USERNAME or password != MOCK_PASSWORD:
        return _json_response(
            {"error": "Invalid credentials."},
            status=401
        )

    return _json_response({
        "access_token": MOCK_TOKEN,
        "token_type": "Bearer",
        "expires_in": 3600
    })

    return JsonResponse({"detail": "Method not allowed"}, status=405)

def contracts(request):
    if request.method != "GET":
        return _json_response(
            {"error": "Method not allowed. Use GET."},
            status=405
        )

    if not _is_authorized(request):
        return _json_response(
            {"error": "Unauthorized."},
            status=401
        )

    return _json_response([
        {
            "id": 1,
            "employee_name": "Иван Иванов",
            "position": "Frontend Developer",
            "start_date": "2024-01-10",
            "status": "active"
        }
    ], safe=False)


def leaves(request):
    if request.method != "GET":
        return _json_response(
            {"error": "Method not allowed. Use GET."},
            status=405
        )

    if not _is_authorized(request):
        return _json_response(
            {"error": "Unauthorized."},
            status=401
        )

    return _json_response([
        {
            "id": 1,
            "employee_name": "Иван Иванов",
            "type": "annual",
            "start_date": "2024-06-01",
            "end_date": "2024-06-14",
            "status": "approved"
        }
    ], safe=False)


def sick_leaves(request):
    if request.method != "GET":
        return _json_response(
            {"error": "Method not allowed. Use GET."},
            status=405
        )

    if not _is_authorized(request):
        return _json_response(
            {"error": "Unauthorized."},
            status=401
        )

    return _json_response([
        {
            "id": 1,
            "employee_name": "Иван Иванов",
            "start_date": "2024-03-01",
            "end_date": "2024-03-05",
            "status": "closed"
        }
    ], safe=False)