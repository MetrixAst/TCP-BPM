from datetime import date, datetime, timedelta
from calendar import monthrange
import calendar
from typing import List, Dict, Optional
from pathlib import Path
import os
import requests
from app.core.config import settings
from app.client_1c.client import Client1C
from app.client_1c.exceptions import (
    Client1CError,
    AuthenticationError,
    APIError,
    MissingSupplierRequisitesError,
)
from app.services.odata_1c_client import OData1CClient, is_odata_url
from app.services.payment_status_rules import paid_enough
from app.services.invoice_service_type import (
    format_service_types_label,
    resolve_invoice_service_types,
)
import random
import logging

logger = logging.getLogger(__name__)


class Integration1C:

    
    def __init__(self, one_c_config: Optional[Dict] = None):
        self.api_url = settings.ONE_C_API_URL
        self.api_key = settings.ONE_C_API_KEY
        self.client = None
        self.last_error: Optional[str] = None
        self.pdf_tenant = None
        self._uses_odata = False
        self._uses_nova = False
        cfg = one_c_config or {}

        nova_org_id = cfg.get("nova_organization_id")
        nova_script_ids = cfg.get("nova_script_ids")
        if nova_org_id:
            try:
                from app.services.nova_buh_1c_client import NovaBuh1CClient
                from app.services.nova_1c_service import Nova1CServiceError

                self._uses_nova = True
                self.client = NovaBuh1CClient(
                    organization_id=int(nova_org_id),
                    script_ids=nova_script_ids or None,
                )
                logger.debug("1C Nova/MCP client ready for org_id=%s", nova_org_id)
                return
            except Nova1CServiceError as e:
                self.last_error = str(e)
                logger.warning("Nova 1C client initialization failed: %s", e)
                return
            except Exception as e:
                self.last_error = str(e)
                logger.warning("Nova 1C client initialization failed: %s", e)
                return

        base_url = cfg.get("base_url") or settings.ONE_C_BASE_URL
        basic_auth_user = cfg.get("basic_auth_user") or settings.ONE_C_BASIC_AUTH_USER
        basic_auth_password = cfg.get("basic_auth_password") or settings.ONE_C_BASIC_AUTH_PASSWORD
        api_user = (cfg.get("api_user") or settings.ONE_C_API_USER or "").strip()
        api_password = (cfg.get("api_password") or settings.ONE_C_API_PASSWORD or "").strip()

        if not api_user or not api_password:
            self.last_error = (
                "Не заданы учётные данные 1С (логин и пароль). "
                "Заполните их у арендатора в админке."
            )
            return

        def _split_entities(value: str) -> Optional[List[str]]:
            if not value or not value.strip():
                return None
            return [e.strip() for e in value.split(",") if e.strip()]

        try:
            if is_odata_url(base_url):
                self._uses_odata = True
                self.client = OData1CClient(
                    base_url=base_url,
                    basic_auth_user=basic_auth_user,
                    basic_auth_password=basic_auth_password,
                    api_user=api_user,
                    api_password=api_password,
                    counterparty_entities=_split_entities(
                        settings.ONE_C_ODATA_COUNTERPARTY_ENTITIES
                    ),
                    invoice_entities=_split_entities(
                        settings.ONE_C_ODATA_INVOICE_ENTITIES
                    ),
                )
                logger.debug(f"1C OData client ready for {base_url} (user: {api_user})")
            else:
                self.client = Client1C(
                    base_url=base_url,
                    basic_auth_user=basic_auth_user,
                    basic_auth_password=basic_auth_password,
                    api_user=api_user,
                    api_password=api_password
                )
                logger.debug(f"1C REST client ready for {base_url} (user: {api_user})")
        except Exception as e:
            self.last_error = str(e)
            logger.warning("1C client initialization failed: %s", e)
            self.client = None

    def unavailable_message(self) -> str:
        if self.client:
            return ""
        base = self.last_error or "клиент 1С не инициализирован"
        if self._uses_nova:
            return (
                f"1С Nova/COM недоступна ({base}). "
                "Проверьте Nova org_id в админке, NOVA_BACKEND_URL и NOVA_ADMIN_* на сервере."
            )
        return (
            f"1С OData недоступна ({base}). "
            "Проверьте интернет/VPN, доступность сервера 1С и учётные данные арендатора."
        )
    
    def fetch_payments(
        self,
        period: str,
        due_day: int = 5,
        utilities_due_day: Optional[int] = None,
        operations_due_day: Optional[int] = None,
    ) -> List[Dict]:

        if not self.client:
            logger.debug(" 1C client not available, using mock data")
            return self._generate_mock_data(period)
        
        try:

            year, month = map(int, period.split("-"))
            since_date = datetime(year, month, 1)
            last_day = monthrange(year, month)[1]
            until_date = datetime(year, month, last_day)
            util_day = utilities_due_day if utilities_due_day is not None else due_day
            ops_day = operations_due_day if operations_due_day is not None else due_day
            payment_since = f"{year}-{month:02d}-01"
            payment_until = until_date.strftime("%Y-%m-%d")
            if hasattr(self.client, "_period_invoice_fetch_bounds"):
                inv_since, inv_until = self.client._period_invoice_fetch_bounds(period)
                if inv_since:
                    payment_since = inv_since
                if inv_until and hasattr(self.client, "_payment_until_with_grace"):
                    payment_until = self.client._payment_until_with_grace(inv_until) or inv_until

            logger.debug(
                " Fetching invoices from 1C for period %s (%s — %s), enrich_payment_status=True",
                period,
                since_date.date(),
                until_date.date(),
            )
            # Клиенты 1С различаются по сигнатуре (Client1C / OData / Nova).
            # Передаём только поддерживаемые аргументы — иначе TypeError → mock и «счета не обновляются».
            import inspect

            invoice_kwargs = {
                "since": since_date,
                "until": until_date,
                "limit": 10000,
                "due_day": due_day,
                "enrich_payment_status": True,
                "payment_since": payment_since,
                "payment_until": payment_until,
                "utilities_due_day": util_day,
                "operations_due_day": ops_day,
                "period": period,
            }
            try:
                accepted = set(inspect.signature(self.client.get_invoices).parameters)
                invoice_kwargs = {
                    k: v for k, v in invoice_kwargs.items() if k in accepted
                }
            except (TypeError, ValueError):
                pass
            invoices = self.client.get_invoices(**invoice_kwargs)
            logger.debug(f" Received {len(invoices)} invoices from 1C")

            result = []
            belongs_to_period = getattr(self.client, "_invoice_belongs_to_period", None)
            for invoice in invoices:
                if belongs_to_period and not belongs_to_period(
                    invoice.date, invoice.due_date, period
                ):
                    continue
                invoice_date = self._parse_date(invoice.date)
                if invoice.due_date:
                    due_date = self._parse_date(invoice.due_date)
                else:
                    due_date = self._calculate_due_date(invoice_date, due_day)
                paid_at = None
                invoice_paid_at = self._parse_datetime(getattr(invoice, "paid_at", "") or "")
                invoice_paid_amount = float(getattr(invoice, "paid_amount", 0) or 0)
                invoice_amount = float(invoice.amount or 0)
                invoice_payment_status = str(getattr(invoice, "payment_status", "") or "").lower()

                if invoice_payment_status == "paid":
                    paid_at = invoice_paid_at or datetime.combine(invoice_date, datetime.min.time())
                elif paid_enough(invoice_amount, invoice_paid_amount):
                    paid_at = invoice_paid_at or datetime.combine(invoice_date, datetime.min.time())

                # invoice.items приходит бесплатно из bulk get_invoices только у
                # Nova-клиента (nova_buh_1c_client строит lines_by_id за один проход);
                # OData/REST bulk get_invoices строк не отдаёт — там будет "unknown"
                # до отдельного live-запроса (см. invoice_service_type.py docstring).
                # Ни один текущий арендатор не на OData/REST, только Nova (org 118/119/127).
                service_types = resolve_invoice_service_types(getattr(invoice, "items", None) or [])
                result.append({
                    "ip_name": invoice.counterparty_name,
                    "tenant_name": invoice.counterparty_name,
                    "invoice_date": invoice_date,
                    "due_date": due_date,
                    "paid_at": paid_at,
                    "amount": invoice.amount,
                    "paid_amount": invoice_paid_amount,
                    "period": period,
                    "status": invoice.status,
                    "invoice_id": invoice.id,
                    "counterparty_id": invoice.counterparty_id,
                    "payment_status": invoice_payment_status,
                    "bin": getattr(invoice, "bin", None) or "",
                    "service_type": format_service_types_label(service_types),
                })
            
            logger.debug(f" Mapped {len(result)} invoices to payment format")
            return result
            
        except AuthenticationError as e:
            logger.warning("1C authentication failed (period=%s): %s", period, e.message)
            return []
        except (Client1CError, APIError) as e:
            logger.warning("1C API error while fetching payments (period=%s): %s", period, e.message)
            return []
        except TypeError as e:
            # Свой баг сигнатуры — не подменять mock'ом (иначе реестр «не обновляется»).
            logger.exception("get_invoices signature mismatch (period=%s): %s", period, e)
            return []
        except Exception as e:
            logger.exception("Unexpected error in fetch_payments (period=%s): %s", period, e)
            return []
    
    def get_invoice_file_url(self, invoice_id: str) -> Optional[str]:

        if not self.client:
            logger.debug(" 1C client not available")
            return None
        

        return f"{self.client._base_url}/invoices/{invoice_id}/file"
    
    def download_file(self, file_url: str, save_path: Optional[str] = None) -> Optional[str]:

        if "/invoices/" in file_url:
            invoice_id = file_url.split("/invoices/")[1].split("/")[0]
            return self.download_invoice_file(invoice_id, save_path)
        

        if not self.client:
            logger.debug(" 1C client not available")
            return None
            
        try:

            if not self.client.access_token:
                logger.debug(" No access token, authenticating...")
                self.client.authenticate()
            

            if save_path is None:
                downloads_dir = Path("backend/downloads")
                downloads_dir.mkdir(parents=True, exist_ok=True)
                filename = file_url.split("/")[-1] or "invoice.pdf"
                save_path = str(downloads_dir / filename)
            

            headers = self.client._get_headers()
            headers.pop("Content-Type", None)
            
            logger.debug(f" Downloading file from: {file_url}")
            logger.debug(f" Using token: {self.client.access_token[:20] if self.client.access_token else 'None'}...")
            logger.debug(f" Saving to: {save_path}")
            

            response = self.client._session.get(
                file_url,
                headers=headers,
                timeout=self.client._timeout,
                stream=True
            )
            
            logger.debug(f" Response status: {response.status_code}")
            
            if response.status_code == 200:

                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.debug(f" File downloaded successfully: {save_path}")
                return save_path
            else:
                logger.debug(f" Failed to download file: {response.status_code}")
                logger.debug(f"Response text: {response.text[:500] if hasattr(response, 'text') else 'N/A'}")
                return None
                
        except Exception as e:
            logger.debug(f" Error downloading file: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def download_invoice_file(self, invoice_id: str, save_path: Optional[str] = None, tenant=None, force: bool = False) -> Optional[str]:

        if not self.client:
            logger.debug(" 1C client not available")
            return None

        try:

            if not self.client.access_token:
                logger.debug(" No access token, authenticating...")
                self.client.authenticate()

            logger.debug(f" Downloading invoice file: {invoice_id}")

            if tenant is None:
                tenant = getattr(self, "pdf_tenant", None)

            kwargs = {"invoice_id": invoice_id, "save_path": save_path}
            if hasattr(self.client, "download_invoice_file"):
                import inspect

                sig = inspect.signature(self.client.download_invoice_file)
                if "tenant" in sig.parameters:
                    kwargs["tenant"] = tenant
                if "force" in sig.parameters:
                    kwargs["force"] = force
            result = self.client.download_invoice_file(**kwargs)
            
            if result and Path(result).exists():
                logger.debug(f"File downloaded successfully: {result}")
                return result

            invoice_name = f"invoice_{invoice_id}.pdf"
            for base in (
                Path.cwd(),
                Path.cwd() / "backend",
                Path(__file__).resolve().parent.parent.parent,
            ):
                for sub in ("downloads", "backend/downloads"):
                    candidate = base / sub / invoice_name
                    if candidate.exists():
                        logger.debug(f" Found invoice file at: {candidate}")
                        return str(candidate)

            logger.debug(f" Failed to download invoice file")
            return None

        except MissingSupplierRequisitesError:
            # Не проглатываем — вызывающий код (API/авторассылка) должен показать
            # конкретную причину, а не общее "PDF не найден".
            raise
        except Exception as e:
            logger.debug(f" Error downloading invoice file: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_invoice_and_download(self, invoice_id: str, tenant=None) -> Optional[str]:

        return self.download_invoice_file(invoice_id, tenant=tenant)
    
    def _parse_date(self, date_str: str) -> date:

        try:

            for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y"]:
                try:
                    return datetime.strptime(date_str.split("T")[0], fmt).date()
                except ValueError:
                    continue

            return date.today()
        except Exception:
            return date.today()
    
    def _parse_datetime(self, date_str: str) -> Optional[datetime]:

        try:

            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"]:
                try:
                    if "T" in date_str or " " in date_str:
                        return datetime.strptime(date_str, fmt)
                    else:

                        d = datetime.strptime(date_str, fmt)
                        return datetime.combine(d.date(), datetime.min.time())
                except ValueError:
                    continue
            return None
        except Exception:
            return None
    
    def _calculate_due_date(self, invoice_date: date, due_day: int = 5) -> date:
        safe_day = max(1, min(31, int(due_day or 5)))
        if invoice_date.month == 12:
            year, month = invoice_date.year + 1, 1
        else:
            year, month = invoice_date.year, invoice_date.month + 1
        max_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(safe_day, max_day))
    
    def _generate_mock_data(self, period: str) -> List[Dict]:

        year, month = map(int, period.split("-"))
        
        ip_names = [
            "ИП Рога и Копыта",
            "ТОО Аааааааааааавиасейлс",
            "ИП Амир",
            "ИП Бизнес",
            "ТОО Компания"
        ]
        
        tenant_names = [
            "Жанадилова Р. Б.",
            "Балабекова Р. Б.",
            "Дементьев М. В.",
            "Цой И. А.",
            "Меладзе М. В.",
        ]
        

        payments = []
        base_date = date(year, month, 1)
        
        for i in range(35):
            ip_name = random.choice(ip_names)
            tenant_name = random.choice(tenant_names)
            
            try:
                invoice_date = date(year, month, 29)
            except ValueError:
                invoice_date = date(year, month, 28)
            
            if month == 12:
                due_date = date(year + 1, 1, 5)
            else:
                due_date = date(year, month + 1, 5)
            
            is_paid = random.random() > 0.3
            paid_at = None
            if is_paid:
                paid_date = invoice_date + timedelta(days=random.randint(0, 10))
                paid_at = datetime.combine(paid_date, datetime.min.time())
            
            payments.append({
                "ip_name": ip_name,
                "tenant_name": tenant_name,
                "invoice_date": invoice_date,
                "due_date": due_date,
                "paid_at": paid_at,
                "amount": random.randint(50000, 500000),
                "period": period
            })
        
        return payments
    
    def get_client_warning(self) -> Optional[str]:
        if self.client and hasattr(self.client, "last_warning"):
            return getattr(self.client, "last_warning", None)
        return None

    def close(self):

        if self.client:
            self.client.close()