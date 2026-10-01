from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class TRCBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    bin_value: Optional[str] = Field(None, max_length=12)
    iin_value: Optional[str] = Field(None, max_length=12)
    message_template: Optional[str] = None
    green_api_url: Optional[str] = Field(None, max_length=512)
    green_api_media_url: Optional[str] = Field(None, max_length=512)
    green_api_id_instance: Optional[str] = Field(None, max_length=64)
    green_api_api_token: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class TRCCreate(TRCBase):
    pass


class TRCUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    bin_value: Optional[str] = Field(None, max_length=12)
    iin_value: Optional[str] = Field(None, max_length=12)
    message_template: Optional[str] = None
    green_api_url: Optional[str] = Field(None, max_length=512)
    green_api_media_url: Optional[str] = Field(None, max_length=512)
    green_api_id_instance: Optional[str] = Field(None, max_length=64)
    green_api_api_token: Optional[str] = Field(None, max_length=255)
    portal_username: Optional[str] = Field(None, min_length=1, max_length=64)
    portal_password: Optional[str] = Field(None, max_length=128)
    is_active: Optional[bool] = None


class TRCResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TRCAdminResponse(TRCBase):
    id: int
    portal_username: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    legal_name: str = Field(..., min_length=1, max_length=255)
    org_type: str = Field(..., pattern="^(IP|TOO)$")
    bin_value: Optional[str] = Field(None, max_length=12)
    iin_value: Optional[str] = Field(None, max_length=12)
    phone: Optional[str] = Field(
        None, max_length=32, description="Номер WhatsApp отправителя (для справки)"
    )
    message_template: Optional[str] = Field(
        None, description="Шаблон WhatsApp для рассылки контрагентам этого арендатора"
    )
    green_api_url: Optional[str] = Field(None, max_length=512)
    green_api_media_url: Optional[str] = Field(None, max_length=512)
    green_api_id_instance: Optional[str] = Field(
        None, max_length=64, description="Green API idInstance этого WhatsApp"
    )
    green_api_api_token: Optional[str] = Field(
        None, max_length=255, description="Green API apiTokenInstance"
    )
    one_c_counterparty_id: Optional[str] = Field(
        None, max_length=64, description="GUID контрагента в 1С"
    )
    one_c_name_match: Optional[str] = Field(
        None, max_length=128, description="Фрагмент названия контрагента в 1С (например MOON)"
    )
    one_c_login: str = Field(default="", max_length=128)
    one_c_password: str = Field(default="", max_length=255)
    one_c_base_url: Optional[str] = Field(None, max_length=512)
    one_c_basic_user: Optional[str] = Field(None, max_length=128)
    one_c_basic_password: Optional[str] = Field(None, max_length=255)
    nova_organization_id: Optional[int] = Field(
        None, ge=1, description="Nova organization_id (118 CityMall, 119 Maxi Mall, …)"
    )
    nova_mcp_system_type: Optional[str] = Field(
        default="com",
        pattern="^(odata|com)$",
        description="Тип MCP mynova: odata (11–15) или com (16–20)",
    )
    nova_script_invoices: Optional[int] = Field(None, ge=1)
    nova_script_payments: Optional[int] = Field(None, ge=1)
    nova_script_counterparties: Optional[int] = Field(None, ge=1)
    nova_script_balance: Optional[int] = Field(None, ge=1)
    nova_script_invoice_by_id: Optional[int] = Field(None, ge=1)
    one_c_connection_mode: Optional[str] = Field(
        default="auto",
        pattern="^(auto|odata_direct|nova_org)$",
        description="auto — по URL/org_id; odata_direct — OData; nova_org — Nova/MCP",
    )
    xlsx_priority: Optional[str] = Field(
        default="disabled",
        pattern="^(disabled|fallback_on_1c_failure|prefer_xlsx)$",
        description="disabled — xlsx не используется; fallback_on_1c_failure — только при сбое 1С; prefer_xlsx — xlsx побеждает 1С на показе",
    )
    xlsx_parser_key: Optional[str] = Field(
        None, max_length=64, description='Ключ парсера в xlsx_import.registry (напр. "maxi_mall") — пусто, если парсер под этого арендатора ещё не написан'
    )
    portal_username: Optional[str] = Field(
        None, max_length=64, description="Логин входа арендатора на основной сайт"
    )
    portal_password: Optional[str] = Field(
        None, max_length=128, description="Пароль входа (только при создании/смене)"
    )
    invoice_executor_name: Optional[str] = Field(
        None, max_length=128, description="Подпись исполнителя, напр. /Иванов И.И./"
    )
    invoice_iik: Optional[str] = Field(
        None, max_length=34, description="ИИК поставщика — fallback, если 1С не отдаёт основной банковский счёт"
    )
    invoice_kbe: Optional[str] = Field(None, max_length=8, description="КБЕ поставщика (fallback)")
    invoice_bank_name: Optional[str] = Field(None, max_length=255, description="Банк поставщика (fallback)")
    invoice_bank_bik: Optional[str] = Field(None, max_length=16, description="БИК банка поставщика (fallback)")
    invoice_payment_knp: Optional[str] = Field(None, max_length=16, description="КНП по умолчанию (fallback)")
    invoice_supplier_address: Optional[str] = Field(None, description="Юр. адрес поставщика (fallback)")
    invoice_contract_text: Optional[str] = Field(None, max_length=255, description="Текст основания договора (fallback)")
    invoice_due_day: Optional[int] = Field(
        None, ge=1, le=31, description="Крайний день оплаты по арендатору (1-31)"
    )
    invoice_due_day_utilities: Optional[int] = Field(
        None, ge=1, le=31, description="Крайний день оплаты коммуналки (1-31)"
    )
    invoice_due_day_operations: Optional[int] = Field(
        None, ge=1, le=31, description="Крайний день оплаты эксплуатации и маркетинга (1-31)"
    )
    payment_rent_enabled: bool = Field(
        True, description="Показывать аренду в портале и в авто-рассылке"
    )
    payment_utilities_enabled: bool = Field(
        True, description="Показывать коммуналку в портале и в авто-рассылке"
    )
    payment_operations_enabled: bool = Field(
        True, description="Показывать эксплуатацию и маркетинг в портале и в авто-рассылке"
    )
    invoice_operations_advance_billing: bool = Field(
        False,
        description="Эксплуатация и маркетинг авансом за следующий месяц (как аренда), а не по факту за текущий",
    )
    smtp_host: Optional[str] = Field(
        None, max_length=255, description="SMTP host, напр. smtp.cloud24.kz"
    )
    smtp_port: Optional[int] = Field(
        None, ge=1, le=65535, description="SMTP port (587 STARTTLS / 465 SSL)"
    )
    smtp_use_starttls: bool = Field(
        True, description="STARTTLS (обычно для порта 587)"
    )
    smtp_username: Optional[str] = Field(
        None, max_length=255, description="SMTP login / mailbox"
    )
    smtp_password: Optional[str] = Field(
        None, max_length=255, description="SMTP password (не отдаётся в API)"
    )
    smtp_from_email: Optional[str] = Field(
        None, max_length=255, description="From: адрес отправителя"
    )
    is_active: bool = True


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    legal_name: Optional[str] = Field(None, min_length=1, max_length=255)
    org_type: Optional[str] = Field(None, pattern="^(IP|TOO)$")
    bin_value: Optional[str] = Field(None, max_length=12)
    iin_value: Optional[str] = Field(None, max_length=12)
    phone: Optional[str] = Field(None, max_length=32)
    message_template: Optional[str] = None
    green_api_url: Optional[str] = Field(None, max_length=512)
    green_api_media_url: Optional[str] = Field(None, max_length=512)
    green_api_id_instance: Optional[str] = Field(None, max_length=64)
    green_api_api_token: Optional[str] = Field(None, max_length=255)
    one_c_counterparty_id: Optional[str] = Field(None, max_length=64)
    one_c_name_match: Optional[str] = Field(None, max_length=128)
    one_c_login: Optional[str] = Field(None, max_length=128)
    one_c_password: Optional[str] = Field(None, max_length=255)
    one_c_base_url: Optional[str] = Field(None, max_length=512)
    one_c_basic_user: Optional[str] = Field(None, max_length=128)
    one_c_basic_password: Optional[str] = Field(None, max_length=255)
    nova_organization_id: Optional[int] = Field(None, ge=1)
    nova_mcp_system_type: Optional[str] = Field(None, pattern="^(odata|com)$")
    nova_script_invoices: Optional[int] = Field(None, ge=1)
    nova_script_payments: Optional[int] = Field(None, ge=1)
    nova_script_counterparties: Optional[int] = Field(None, ge=1)
    nova_script_balance: Optional[int] = Field(None, ge=1)
    nova_script_invoice_by_id: Optional[int] = Field(None, ge=1)
    one_c_connection_mode: Optional[str] = Field(
        None, pattern="^(auto|odata_direct|nova_org)$"
    )
    xlsx_priority: Optional[str] = Field(
        None, pattern="^(disabled|fallback_on_1c_failure|prefer_xlsx)$"
    )
    xlsx_parser_key: Optional[str] = Field(None, max_length=64)
    portal_username: Optional[str] = Field(None, min_length=1, max_length=64)
    portal_password: Optional[str] = Field(None, max_length=128)
    invoice_executor_name: Optional[str] = Field(None, max_length=128)
    invoice_iik: Optional[str] = Field(None, max_length=34)
    invoice_kbe: Optional[str] = Field(None, max_length=8)
    invoice_bank_name: Optional[str] = Field(None, max_length=255)
    invoice_bank_bik: Optional[str] = Field(None, max_length=16)
    invoice_payment_knp: Optional[str] = Field(None, max_length=16)
    invoice_supplier_address: Optional[str] = None
    invoice_contract_text: Optional[str] = Field(None, max_length=255)
    invoice_due_day: Optional[int] = Field(None, ge=1, le=31)
    invoice_due_day_utilities: Optional[int] = Field(None, ge=1, le=31)
    invoice_due_day_operations: Optional[int] = Field(None, ge=1, le=31)
    payment_rent_enabled: Optional[bool] = None
    payment_utilities_enabled: Optional[bool] = None
    payment_operations_enabled: Optional[bool] = None
    invoice_operations_advance_billing: Optional[bool] = None
    smtp_host: Optional[str] = Field(None, max_length=255)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_use_starttls: Optional[bool] = None
    smtp_username: Optional[str] = Field(None, max_length=255)
    smtp_password: Optional[str] = Field(None, max_length=255)
    smtp_from_email: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class TenantResponse(BaseModel):
    id: int
    trc_id: int
    name: str
    legal_name: str
    org_type: str
    bin_value: Optional[str] = None
    iin_value: Optional[str] = None
    phone: Optional[str] = None
    message_template: Optional[str] = None
    green_api_url: Optional[str] = None
    green_api_media_url: Optional[str] = None
    green_api_id_instance: Optional[str] = None
    one_c_counterparty_id: Optional[str] = None
    one_c_name_match: Optional[str] = None
    one_c_login: str
    one_c_base_url: Optional[str] = None
    one_c_basic_user: Optional[str] = None
    nova_organization_id: Optional[int] = None
    nova_mcp_system_type: Optional[str] = None
    nova_script_invoices: Optional[int] = None
    nova_script_payments: Optional[int] = None
    nova_script_counterparties: Optional[int] = None
    nova_script_balance: Optional[int] = None
    nova_script_invoice_by_id: Optional[int] = None
    one_c_connection_mode: Optional[str] = None
    xlsx_priority: Optional[str] = None
    xlsx_parser_key: Optional[str] = None
    portal_username: Optional[str] = None
    stamp_file_path: Optional[str] = None
    signature_file_path: Optional[str] = None
    invoice_executor_name: Optional[str] = None
    invoice_iik: Optional[str] = None
    invoice_kbe: Optional[str] = None
    invoice_bank_name: Optional[str] = None
    invoice_bank_bik: Optional[str] = None
    invoice_payment_knp: Optional[str] = None
    invoice_supplier_address: Optional[str] = None
    invoice_contract_text: Optional[str] = None
    invoice_due_day: Optional[int] = None
    invoice_due_day_utilities: Optional[int] = None
    invoice_due_day_operations: Optional[int] = None
    payment_rent_enabled: bool = True
    payment_utilities_enabled: bool = True
    payment_operations_enabled: bool = True
    invoice_operations_advance_billing: bool = False
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_use_starttls: bool = True
    smtp_username: Optional[str] = None
    smtp_from_email: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TenantAdminResponse(TenantResponse):

    has_one_c_password: bool = False
    has_one_c_basic_password: bool = False
    has_green_api_api_token: bool = False
    has_smtp_password: bool = False


class SmtpTestRequest(BaseModel):
    """Проверка SMTP: можно передать черновик из формы или использовать сохранённые поля."""

    smtp_host: Optional[str] = Field(None, max_length=255)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_use_starttls: Optional[bool] = None
    smtp_username: Optional[str] = Field(None, max_length=255)
    smtp_password: Optional[str] = Field(None, max_length=255)
    smtp_from_email: Optional[str] = Field(None, max_length=255)
    send_to: Optional[str] = Field(
        None,
        max_length=255,
        description="Если указан — отправить тестовое письмо на этот адрес",
    )


class SmtpTestResponse(BaseModel):
    ok: bool
    message: Optional[str] = None
    error: Optional[str] = None


class TenantPublicResponse(BaseModel):
    id: int
    trc_id: int
    name: str
    legal_name: str
    org_type: str
    bin_value: Optional[str] = None
    iin_value: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class TRCWithTenantsResponse(TRCResponse):
    tenants: List[TenantPublicResponse] = []


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CounterpartyPhoneBase(BaseModel):
    one_c_counterparty_id: str = Field(..., min_length=1, max_length=64)
    counterparty_name: Optional[str] = Field(None, max_length=255)
    contact_name: Optional[str] = Field(None, max_length=255)
    phone: str = Field(..., min_length=10, max_length=32)
    phone_rent: Optional[str] = Field(None, max_length=32)
    phone_utilities: Optional[str] = Field(None, max_length=32)
    phone_operations: Optional[str] = Field(None, max_length=32)


class CounterpartyPhoneUpsert(CounterpartyPhoneBase):
    pass


class CounterpartyPhoneResponse(CounterpartyPhoneBase):
    id: int
    trc_id: int
    last_whatsapp_sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CounterpartyPhoneBackfillItem(BaseModel):
    one_c_counterparty_id: str
    counterparty_name: Optional[str] = None
    phones: List[str] = []
    status: str
    written: Optional[int] = None
    skipped: Optional[int] = None
    message: Optional[str] = None


class CounterpartyPhoneBackfillResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    dry_run: bool = False
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None
    trc_id: Optional[int] = None
    total: int = 0
    ok_count: int = 0
    fail_count: int = 0
    empty_skip: int = 0
    cache_refreshed: bool = False
    last_processed_id: Optional[int] = None
    items: List[CounterpartyPhoneBackfillItem] = []


class CounterpartyDirectoryItem(BaseModel):
    one_c_counterparty_id: str
    counterparty_name: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    bin_value: Optional[str] = None
    last_whatsapp_sent_at: Optional[datetime] = None


class AgingBuckets(BaseModel):
    current: float = 0
    days30: float = 0
    days60: float = 0
    days90: float = 0
    over120: float = 0
    unknown: float = 0
    total: float = 0


class TenantDebtSummary(BaseModel):
    tenant_id: int
    tenant_name: str
    has_balance_data: bool
    synced_at: Optional[datetime] = None
    debt: float = 0
    advance: float = 0
    aging: AgingBuckets = AgingBuckets()


class TrcDebtSummary(BaseModel):
    trc_id: int
    total_debt: float = 0
    total_advance: float = 0
    aging: AgingBuckets = AgingBuckets()
    tenants_with_data: int = 0
    tenants_without_data: int = 0
    by_tenant: List[TenantDebtSummary] = []


class AdminUserResponse(BaseModel):
    id: int
    username: str
    is_super: bool
    is_active: bool

    class Config:
        from_attributes = True


class NovaOrgResolveResponse(BaseModel):
    organization_id: int
    organization_name: Optional[str] = None
    connection_mode: str
    nova_mcp_system_type: Optional[str] = None
    nova_script_invoices: Optional[int] = None
    nova_script_payments: Optional[int] = None
    nova_script_counterparties: Optional[int] = None
    nova_script_balance: Optional[int] = None
    nova_script_invoice_by_id: Optional[int] = None
    odata_url: Optional[str] = None
    one_c_login: Optional[str] = None
    database_name: Optional[str] = None
    agent_id: Optional[str] = None
    password_required: bool = False
    message: str = ""
    test_ok: bool = False
    counterparties_count: Optional[int] = None
    error: Optional[str] = None
