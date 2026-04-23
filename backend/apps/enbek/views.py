from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json


@csrf_exempt
def login(request):
    if request.method == 'POST':
        return JsonResponse({
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600
        })

    return JsonResponse({"detail": "Method not allowed"}, status=405)

def contracts(request):
    return JsonResponse([
        {
            "id": 1,
            "employee_name": "Иван Иванов",
            "position": "Frontend Developer",
            "start_date": "2024-01-10",
            "status": "active"
        }
    ], safe=False)


def leaves(request):
    return JsonResponse([
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
    return JsonResponse([
        {
            "id": 1,
            "employee_name": "Иван Иванов",
            "start_date": "2024-03-01",
            "end_date": "2024-03-05",
            "status": "closed"
        }
    ], safe=False)