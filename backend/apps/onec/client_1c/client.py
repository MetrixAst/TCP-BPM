import requests
from requests.auth import HTTPBasicAuth
from typing import List, Optional, Union
from datetime import datetime
from urllib.parse import urljoin

from .models import (
    AuthResponse,
    DataResponse,
    Invoice,
    Payment,
    Balance,
    Counterparty,
    ConfirmResponse
)
from .exceptions import (
    Client1CError,
    AuthenticationError,
    TokenExpiredError,
    APIError,
    ValidationError
)


class Client1C:
    def __init__(
        self,
        base_url: str,
        basic_auth_user: str,
        basic_auth_password: str,
        api_user: str = None,
        api_password: str = None,
        timeout: int = 30,
        verify_ssl: bool = True
    ):
        self._base_url = base_url.rstrip("/")
        self._basic_auth = HTTPBasicAuth(basic_auth_user, basic_auth_password)
        self._api_user = api_user
        self._api_password = api_password
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._access_token: Optional[str] = None
        self._token_expires: Optional[str] = None
        self._sync_token: Optional[str] = None
        self._session = requests.Session()
        self._session.auth = self._basic_auth
        self._session.verify = self._verify_ssl

    @property
    def access_token(self) -> Optional[str]:
        return self._access_token

    @property
    def sync_token(self) -> Optional[str]:
        return self._sync_token

    def _build_url(self, endpoint: str) -> str:
        return f"{self._base_url}/{endpoint.lstrip('/')}"

    def _get_headers(self, with_token: bool = True) -> dict:
        headers = {"Content-Type": "application/json"}
        if with_token and self._access_token:
            headers["X-Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _handle_response(self, response: requests.Response) -> Union[dict, list]:
        if response.status_code == 401:
            raise AuthenticationError(
                "Authentication failed",
                status_code=response.status_code,
                response=self._safe_json(response)
            )
        if response.status_code == 403:
            raise TokenExpiredError(
                "Token expired or invalid",
                status_code=response.status_code,
                response=self._safe_json(response)
            )
        if response.status_code == 400:
            raise ValidationError(
                "Validation error",
                status_code=response.status_code,
                response=self._safe_json(response)
            )
        if response.status_code >= 500:
            raise APIError(
                "Server error",
                status_code=response.status_code,
                response=self._safe_json(response)
            )
        if response.status_code >= 400:
            raise APIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                response=self._safe_json(response)
            )
        return self._safe_json(response)

    def _safe_json(self, response: requests.Response) -> Union[dict, list, None]:
        try:
            return response.json()
        except ValueError:
            return None

    def get_swagger(self) -> dict:
        url = self._build_url("/swagger")
        response = self._session.get(url, timeout=self._timeout)
        return self._handle_response(response)

    def authenticate(self, user: str = None, password: str = None) -> AuthResponse:
        url = self._build_url("/auth")
        payload = {
            "user": user or self._api_user,
            "password": password or self._api_password
        }
        if not payload["user"] or not payload["password"]:
            raise ValidationError("API user and password are required for authentication")
        response = self._session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self._timeout
        )
        data = self._handle_response(response)
        auth_response = AuthResponse.from_dict(data)
        self._access_token = auth_response.token
        self._token_expires = auth_response.expires
        return auth_response

    def _ensure_authenticated(self):
        if not self._access_token:
            if self._api_user and self._api_password:
                self.authenticate()
            else:
                raise AuthenticationError("Not authenticated. Call authenticate() first or provide api_user/api_password")

    def get_data(self, limit: int = 100) -> DataResponse:
        self._ensure_authenticated()
        url = self._build_url("/data")
        params = {"limit": min(limit, 1000)}
        headers = self._get_headers()
        print(f" Sending request to /data with X-Authorization: Bearer {self._access_token[:20] if self._access_token else 'None'}...")
        response = self._session.get(
            url,
            params=params,
            headers=headers,
            timeout=self._timeout
        )
        data = self._handle_response(response)
        data_response = DataResponse.from_dict(data)
        if data_response.sync_token:
            self._sync_token = data_response.sync_token
        return data_response

    def get_all_data(self, batch_size: int = 100) -> List[dict]:
        all_records = []
        while True:
            response = self.get_data(limit=batch_size)
            all_records.extend([r.data for r in response.data])
            if not response.has_more:
                break
        return all_records

    def get_invoices(
        self,
        since: Union[str, datetime] = None,
        limit: int = 100
    ) -> List[Invoice]:
        self._ensure_authenticated()
        url = self._build_url("/invoices")
        params = {}
        if since:
            if isinstance(since, datetime):
                params["since"] = since.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                params["since"] = since
        if limit:
            params["limit"] = limit
        headers = self._get_headers()
        print(f" Sending request to /invoices with X-Authorization: Bearer {self._access_token[:20] if self._access_token else 'None'}...")
        print(f" Request URL: {url}")
        print(f" Request params: {params}")
        print(f" Request headers: {list(headers.keys())}")
        response = self._session.get(
            url,
            params=params,
            headers=headers,
            timeout=self._timeout
        )
        print(f" Response status: {response.status_code}")
        print(f" Response headers: {dict(response.headers)}")
        data = self._handle_response(response)
        print(f" Response data type: {type(data)}, length: {len(data) if isinstance(data, list) else 'not a list'}")
        if isinstance(data, list):
            invoices = []
            for item in data:
                try:
                    invoice = Invoice.from_dict(item)
                    invoices.append(invoice)
                    print(f" Parsed invoice: id={invoice.id}, number={invoice.number}, pdf={invoice.pdf}")
                except Exception as e:
                    print(f" Error parsing invoice item: {e}")
                    print(f" Item data: {item}")
                    import traceback
                    traceback.print_exc()
            print(f" Successfully parsed {len(invoices)} invoices")
            return invoices
        else:
            print(f" Warning: Response is not a list, got: {type(data)}")
            if isinstance(data, dict):
                print(f" Response keys: {list(data.keys())}")
        return []

    def get_payments(
        self,
        since: Union[str, datetime] = None,
        limit: int = None
    ) -> List[Payment]:
        self._ensure_authenticated()
        url = self._build_url("/payments")
        params = {}
        if since:
            if isinstance(since, datetime):
                params["since"] = since.strftime("%Y-%m-%d")
            else:
                params["since"] = since
        if limit:
            params["limit"] = limit
        headers = self._get_headers()
        print(f" Sending request to /payments with X-Authorization: Bearer {self._access_token[:20] if self._access_token else 'None'}...")
        response = self._session.get(
            url,
            params=params,
            headers=headers,
            timeout=self._timeout
        )
        data = self._handle_response(response)
        if isinstance(data, list):
            return [Payment.from_dict(item) for item in data]
        return []

    def get_balance(
        self,
        counterparty_id: str,
        since: Union[str, datetime] = None
    ) -> Balance:
        self._ensure_authenticated()
        url = self._build_url("/balance")
        params = {"counterparty_id": counterparty_id}
        if since:
            if isinstance(since, datetime):
                params["since"] = since.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                params["since"] = since
        headers = self._get_headers()
        print(f" Sending request to /balance with X-Authorization: Bearer {self._access_token[:20] if self._access_token else 'None'}...")
        response = self._session.get(
            url,
            params=params,
            headers=headers,
            timeout=self._timeout
        )
        

        print(f" Response status: {response.status_code}")
        

        try:
            data = self._safe_json(response)
            if data and isinstance(data, dict):
                print(f" Got response data. Keys: {list(data.keys())}")

                if response.status_code >= 500:
                    print(f" Server returned {response.status_code} but has valid data. Processing anyway...")
                return Balance.from_dict(data)
        except Exception as e:
            print(f" Failed to parse response: {e}")

            if response.status_code < 500:
                data = self._handle_response(response)
                return Balance.from_dict(data)
            else:
                raise
        

        data = self._handle_response(response)
        print(f"Parsed balance data. Keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        return Balance.from_dict(data)

    def get_counterparties(self, limit: int = 100) -> List[Counterparty]:
        self._ensure_authenticated()
        url = self._build_url("/counterparties")
        params = {"limit": limit}
        headers = self._get_headers()
        print(f" Sending request to /counterparties with X-Authorization: Bearer {self._access_token[:20] if self._access_token else 'None'}...")
        response = self._session.get(
            url,
            params=params,
            headers=headers,
            timeout=self._timeout
        )
        data = self._handle_response(response)
        if isinstance(data, list):
            return [Counterparty.from_dict(item) for item in data]
        return []

    def confirm(
        self,
        received_ids: List[str],
        status: str = "sent",
        errors: List[str] = None,
        sync_token: str = None
    ) -> ConfirmResponse:
        self._ensure_authenticated()
        url = self._build_url("/confirm")
        payload = {
            "sync_token": sync_token or self._sync_token,
            "received_ids": received_ids,
            "status": status,
            "errors": errors or []
        }
        if not payload["sync_token"]:
            raise ValidationError("sync_token is required. Call get_data() first or provide sync_token")
        headers = self._get_headers()
        print(f"Sending request to /confirm with X-Authorization: Bearer {self._access_token[:20] if self._access_token else 'None'}...")
        response = self._session.post(
            url,
            json=payload,
            headers=headers,
            timeout=self._timeout
        )
        data = self._handle_response(response)
        return ConfirmResponse.from_dict(data)

    def download_invoice_file(
        self,
        invoice_id: str,
        pdf_path: Optional[str] = None,
        save_path: str = None
    ) -> Optional[str]:

        self._ensure_authenticated()
        

        if pdf_path:

            if pdf_path.startswith("/"):
                endpoints = [pdf_path]
            else:
                endpoints = [f"/{pdf_path}"]

            endpoints.extend([
                f"/invoices/{invoice_id}/file",
                f"/invoices/{invoice_id}/download",
                f"/invoices/{invoice_id}/document",
                f"/invoices/{invoice_id}/pdf"
            ])
        else:

            endpoints = [
                f"/getpdf/{invoice_id}",
                f"/invoices/{invoice_id}/file",
                f"/invoices/{invoice_id}/download",
                f"/invoices/{invoice_id}/document",
                f"/invoices/{invoice_id}/pdf"
            ]
        
        print(f" Attempting to download invoice file: {invoice_id}")
        if pdf_path:
            print(f" Using PDF path from invoice: {pdf_path}")
        print(f" Using token: {self._access_token[:20] if self._access_token else 'None'}...")
        
        for endpoint in endpoints:
            try:
                url = self._build_url(endpoint)
                headers = self._get_headers()

                headers.pop("Content-Type", None)
                
                print(f" Trying endpoint: {endpoint}")
                
                response = self._session.get(
                    url,
                    headers=headers,
                    timeout=self._timeout,
                    stream=True
                )
                
                print(f" Response status: {response.status_code}")
                
                if response.status_code == 200:

                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:

                        try:
                            error_data = response.json()
                            print(f" Got JSON response instead of file: {error_data}")
                            continue
                        except:
                            pass
                    

                    if save_path is None:

                        content_disposition = response.headers.get("Content-Disposition", "")
                        filename = None
                        if "filename=" in content_disposition:
                            filename = content_disposition.split("filename=")[1].strip('"\'')
                        
                        if not filename:

                            if "pdf" in content_type.lower():
                                filename = f"invoice_{invoice_id}.pdf"
                            else:
                                filename = f"invoice_{invoice_id}"
                        
                        save_path = filename
                    
                    print(f" Saving file to: {save_path}")
                    

                    with open(save_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    print(f" File downloaded successfully: {save_path}")
                    return save_path
                elif response.status_code == 404:

                    print(f" Endpoint {endpoint} returned 404, trying next...")
                    continue
                elif response.status_code == 401:
                    print(f" Authentication failed (401)")
                    raise AuthenticationError(
                        "Authentication failed",
                        status_code=401,
                        response=self._safe_json(response)
                    )
                elif response.status_code == 403:
                    print(f" Token expired (403)")
                    raise TokenExpiredError(
                        "Token expired or invalid",
                        status_code=403,
                        response=self._safe_json(response)
                    )
                else:

                    print(f"️ Endpoint {endpoint} returned {response.status_code}")
                    try:
                        error_data = self._safe_json(response)
                        if error_data:
                            print(f"   Error details: {error_data}")
                    except:
                        pass
                    continue
            except (AuthenticationError, TokenExpiredError):

                raise
            except APIError as e:

                if e.status_code == 404:
                    continue
                print(f" API Error on {endpoint}: {e.message}")
                continue
            except Exception as e:

                print(f" Error on {endpoint}: {type(e).__name__}: {e}")
                continue
        
        print(f"Failed to download file from all endpoints")
        return None

    def close(self):
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
