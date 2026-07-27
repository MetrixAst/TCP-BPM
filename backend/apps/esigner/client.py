import base64
import requests
from django.conf import settings
from django.core.cache import cache

from .exceptions import ESignerAuthError, ESignerAPIError


TOKEN_CACHE_KEY = "esigner:access_token"
TOKEN_TTL = 55 * 60  # обновление за 5 минут до истечения часового токена


class ESignerClient:
    def __init__(self):
        self._base_url = settings.ESIGNER_URL.rstrip("/")
        self._client_id = settings.ESIGNER_CLIENT_ID
        self._secret_key = settings.ESIGNER_SECRET_KEY
        self._timeout = getattr(settings, "ESIGNER_TIMEOUT", 30)
        self._session = requests.Session()


    def _get_token(self) -> str:
        token = cache.get(TOKEN_CACHE_KEY)
        if token:
            return token
        return self._refresh_token()

    def _refresh_token(self) -> str:
        creds = base64.b64encode(
            f"{self._client_id}:{self._secret_key}".encode()
        ).decode()
        resp = self._session.post(
            f"{self._base_url}/auth/integrations/login/",
            headers={"Authorization": f"Basic {creds}"},
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            print("STATUS:", resp.status_code)
            print("HEADERS:", resp.headers)
            print("BODY:", resp.text)

            raise ESignerAuthError(
        f"eSigner auth failed: {resp.text}",
        status_code=resp.status_code,
    )
        token = resp.json()["data"]["access_token"]
        cache.set(TOKEN_CACHE_KEY, token, TOKEN_TTL)
        return token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _safe_json(self, resp):
        try:
            return resp.json()
        except ValueError:
            return None

    def _request(self, method, path, retry=True, **kwargs):
        url = f"{self._base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = self._session.request(method, url, headers=headers, timeout=self._timeout, **kwargs)

        if resp.status_code == 401 and retry:
            cache.delete(TOKEN_CACHE_KEY)
            return self._request(method, path, retry=False, headers=headers, **kwargs)

        if resp.status_code >= 400:
            payload = self._safe_json(resp) or {}
            raise ESignerAPIError(
                f"eSigner API error {resp.status_code}: {payload.get('error_code', '')}",
                status_code=resp.status_code,
                response=payload,
            )
        return resp


    def ensure_folder(self, name: str, company_id: int) -> str:
        resp = self._request(
            "POST", "/folders/",
            data={"name": name, "company_id": company_id},
        )
        return resp.json()["data"]["id"]


    def upload_document(self, folder_id: str, filename: str, file_obj, content_type: str) -> dict:
        resp = self._request(
            "POST", f"/documents/{folder_id}/",
            files={"file": (filename, file_obj, content_type)},
        )
        return resp.json()["data"]

    def add_signer(self, document_id: str, bin_or_iin: str, is_company: bool):
        self._request(
            "POST", f"/documents/{document_id}/signers/",
            headers={"Content-Type": "application/json"},
            json={"bin_or_iin": bin_or_iin, "is_company": is_company},
        )

    def send_for_signing(self, document_id: str) -> dict:
        resp = self._request(
            "PATCH", f"/documents/{document_id}/status/",
            data={"status": "SENT"},
        )
        return resp.json()["data"]

    def get_document(self, document_id: str) -> dict:
        resp = self._request("GET", f"/documents/{document_id}/")
        return resp.json()["data"]

    def set_callback_url(self, company_id: int, callback_url: str):
        self._request(
            "PUT", f"/companies/callback-url/{company_id}/",
            headers={"Content-Type": "application/json"},
            json={"callback_url": callback_url},
        )

    def download_signed_pdf(self, document_id: str) -> bytes:
        resp = self._session.get(
            f"{self._base_url}/documents/{document_id}/file/",
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            raise ESignerAPIError(
                "Failed to download signed pdf",
                status_code=resp.status_code,
                response=self._safe_json(resp),
            )
        if not resp.content.startswith(b"%PDF"):
            raise ESignerAPIError(
                "eSigner returned non-PDF content",
                status_code=resp.status_code,
            )
        return resp.content

    def validate_pdf(self, file_obj) -> list:
        resp = self._session.post(
            f"{self._base_url}/documents/validate/pdf/",
            files={"pdf_file": file_obj},
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            raise ESignerAPIError("Validation failed", status_code=resp.status_code)
        return resp.json()["data"]