import requests
from typing import List, Optional
from django.conf import settings


class EnbekClientError(Exception):
    pass


class AuthenticationError(EnbekClientError):
    pass


class ConnectionError(EnbekClientError):
    pass


class EnbekClient:

    def __init__(self):
        self.base_url = settings.ENBEK_BASE_URL.rstrip("/")
        self.timeout = getattr(settings, "ENBEK_TIMEOUT", 10)
        self.session = requests.Session()
        self.token: Optional[str] = None

    def _build_url(self, endpoint: str) -> str:
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "Host": "localhost",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _handle_response(self, response):
        if response.status_code == 401:
            raise AuthenticationError("Invalid credentials")

        if response.status_code >= 500:
            raise ConnectionError("Server error")

        if response.status_code >= 400:
            raise EnbekClientError(f"API error: {response.status_code}")

        try:
            return response.json()
        except Exception:
            raise EnbekClientError("Invalid JSON response")

    def authenticate(self, username=None, password=None):
        url = self._build_url("/auth/login/")

        payload = {
            "username": username or settings.ENBEK_USERNAME,
            "password": password or settings.ENBEK_PASSWORD,
        }

        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout
            )
        except requests.exceptions.Timeout:
            raise ConnectionError("Timeout while connecting to Enbek API")

        data = self._handle_response(response)

        self.token = data.get("access_token")

        if not self.token:
            raise AuthenticationError("Token not received")

        return self.token

    def _ensure_auth(self):
        if not self.token:
            self.authenticate()

    def get_vacations(self) -> List[dict]:
        self._ensure_auth()

        url = self._build_url("/leaves/")

        response = self.session.get(
            url,
            headers=self._headers(),
            timeout=self.timeout
        )

        return self._handle_response(response)

    def get_sick_leaves(self) -> List[dict]:
        self._ensure_auth()

        url = self._build_url("/sick-leaves/")

        response = self.session.get(
            url,
            headers=self._headers(),
            timeout=self.timeout
        )

        return self._handle_response(response)

    def get_employment_contracts(self) -> List[dict]:
        self._ensure_auth()

        url = self._build_url("/contracts/")

        response = self.session.get(
            url,
            headers=self._headers(),
            timeout=self.timeout
        )

        return self._handle_response(response)