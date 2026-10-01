"""Nova backend API client for 1C buh scripts (OData-direct and COM/MCP orgs)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0}


@dataclass
class NovaOrgConfig:
    organization_id: int
    odata_url: Optional[str] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    agent_id: Optional[str] = None
    status: Optional[str] = None


class Nova1CServiceError(Exception):
    pass


class Nova1CService:
    def __init__(
        self,
        base_url: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 120,
    ):
        self._base_url = (base_url or settings.NOVA_BACKEND_URL).rstrip("/")
        self._email = (email or settings.NOVA_ADMIN_EMAIL or "").strip()
        self._password = password or settings.NOVA_ADMIN_PASSWORD or ""
        self._timeout = timeout

    def configured(self) -> bool:
        return bool(self._base_url and self._email and self._password)

    def _login(self) -> str:
        if not self.configured():
            raise Nova1CServiceError(
                "Nova API не настроен: задайте NOVA_BACKEND_URL, NOVA_ADMIN_EMAIL и NOVA_ADMIN_PASSWORD"
            )
        now = time.time()
        cached = _TOKEN_CACHE.get("token")
        if cached and _TOKEN_CACHE.get("expires_at", 0) > now:
            return cached

        url = f"{self._base_url}/api/v1/admin/auth/login"
        credentials = {"password": self._password}
        # Nova backend: login (актуально); email — старый контракт API.
        response = requests.post(
            url,
            json={"login": self._email, **credentials},
            timeout=30,
        )
        if response.status_code == 401:
            response = requests.post(
                url,
                json={"email": self._email, **credentials},
                timeout=30,
            )
        if response.status_code == 401:
            _TOKEN_CACHE["token"] = None
            _TOKEN_CACHE["expires_at"] = 0.0
        if response.status_code >= 400:
            hint = ""
            if response.status_code == 401 and "email" in (self._email or ""):
                hint = " Nova admin API принимает поле login (не email)."
            raise Nova1CServiceError(
                f"Nova login failed ({response.status_code}): {response.text[:300]}{hint}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise Nova1CServiceError("Nova login: access_token not returned")
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expires_at"] = now + 50 * 60
        return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        token = self._login()
        url = f"{self._base_url}{path}"
        for attempt in range(2):
            response = requests.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
                timeout=self._timeout,
            )
            if response.status_code == 401 and attempt == 0:
                _TOKEN_CACHE["token"] = None
                _TOKEN_CACHE["expires_at"] = 0.0
                token = self._login()
                continue
            break
        if response.status_code >= 400:
            raise Nova1CServiceError(
                f"Nova API {method} {path} failed ({response.status_code}): {response.text[:500]}"
            )
        if not response.text:
            return {}
        return response.json()

    def get_org_config(self, organization_id: int) -> NovaOrgConfig:
        payload = self._request("GET", f"/api/v1/onec/config/{organization_id}")
        return NovaOrgConfig(
            organization_id=organization_id,
            odata_url=(payload.get("odata_url") or "").strip() or None,
            database_name=(payload.get("database_name") or "").strip() or None,
            username=(payload.get("username") or "").strip() or None,
            agent_id=(payload.get("agent_id") or "").strip() or None,
            status=(payload.get("status") or "").strip() or None,
        )

    def list_scripts(self, organization_id: int) -> list[dict]:
        payload = self._request(
            "GET",
            "/api/v1/onec/scripts",
            params={"organization_id": organization_id},
        )
        return list(payload.get("scripts") or [])

    @staticmethod
    def _normalize_script_text(value: str) -> str:
        # ё/й variants differ across org script titles (Счёт vs Счет).
        return (value or "").lower().replace("ё", "е")

    @classmethod
    def find_script_id(
        cls,
        scripts: list[dict],
        *needles: str,
        exclude: tuple[str, ...] = (),
    ) -> Optional[int]:
        lowered = [cls._normalize_script_text(n) for n in needles]
        lowered_exclude = [cls._normalize_script_text(item) for item in exclude]
        for script in scripts:
            name = cls._normalize_script_text(script.get("name") or "")
            if any(item in name for item in lowered_exclude):
                continue
            if all(needle in name for needle in lowered):
                return int(script["ID"])
        return None

    def resolve_script_ids(self, organization_id: int) -> dict[str, int]:
        scripts = self.list_scripts(organization_id)
        mapping: dict[str, int] = {}
        # Prefer explicit BUH script names first (live-scripts for COM orgs),
        # then fallback to broad keyword matching per organization.
        exact_name_priority = (
            ("invoices", ("счета на оплату", "шапки+строки")),
            ("payments", ("платежи", "поступления")),
            ("counterparties", ("контрагенты",)),
            ("balance", ("баланс", "взаиморасч")),
            ("invoice_by_id", ("счет по uid",)),
            ("invoice_pdf", ("pdf", "сч", "uid")),
        )
        for key, needles in exact_name_priority:
            script_id = self.find_script_id(scripts, *needles)
            if script_id is not None:
                mapping[key] = script_id

        for key, needles, exclude in (
            ("counterparties", ("контрагент",), ()),
            # Moon-style: "Счета (+Остаток/СтатусОплаты)" — no "оплату" in title.
            ("invoices", ("счета",), ("авр", "акт", "uid", "pdf")),
            ("invoices", ("счета", "оплату"), ()),
            ("payments", ("платеж",), ("касса", "банк", "пко", "рко")),
            # Important: avoid matching AVР scripts (e.g. "АВР по UID")
            # when we need invoice scripts ("Счёт по UID").
            ("invoice_by_id", ("счет по uid",), ("pdf", "авр", "акт")),
            ("invoice_by_id", ("uid",), ("pdf", "авр", "акт")),
            ("invoice_pdf", ("pdf", "uid"), ("авр", "акт")),
            ("balance", ("баланс",), ()),
        ):
            if key in mapping:
                continue
            script_id = self.find_script_id(scripts, *needles, exclude=exclude)
            if script_id is not None:
                mapping[key] = script_id
        return mapping

    def run_script(
        self,
        organization_id: int,
        script_id: int,
        *,
        arguments: Optional[dict] = None,
        vars: Optional[dict] = None,
    ) -> dict:
        body: dict[str, Any] = {}
        if arguments:
            body["arguments"] = arguments
        if vars:
            body["vars"] = vars
        return self._request(
            "POST",
            f"/api/v1/onec/scripts/{script_id}/run",
            params={"organization_id": organization_id},
            json_body=body,
        )

    def create_script(
        self,
        organization_id: int,
        *,
        name: str,
        description: str,
        body: dict,
    ) -> dict:
        return self._request(
            "POST",
            "/api/v1/onec/scripts",
            json_body={
                "organization_id": organization_id,
                "name": name,
                "description": description,
                "body": body,
            },
        )

    def update_script(
        self,
        organization_id: int,
        script_id: int,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        body: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if body is not None:
            payload["body"] = body
        return self._request(
            "PUT",
            f"/api/v1/onec/scripts/{script_id}",
            params={"organization_id": organization_id},
            json_body=payload,
        )

    def upsert_script_by_name(
        self,
        organization_id: int,
        *,
        name: str,
        description: str,
        body: dict,
    ) -> dict:
        scripts = self.list_scripts(organization_id)
        lowered = name.strip().lower()
        for script in scripts:
            if (script.get("name") or "").strip().lower() == lowered:
                return self.update_script(
                    organization_id,
                    int(script["ID"]),
                    name=name,
                    description=description,
                    body=body,
                )
        return self.create_script(
            organization_id,
            name=name,
            description=description,
            body=body,
        )

    def get_organization_name(self, organization_id: int) -> Optional[str]:
        try:
            payload = self._request("GET", f"/api/v1/admin/organizations/{organization_id}")
            return (payload.get("name") or "").strip() or None
        except Nova1CServiceError:
            return None


def get_nova_1c_service() -> Nova1CService:
    return Nova1CService()
