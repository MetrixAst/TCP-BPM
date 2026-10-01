from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum, UniqueConstraint, LargeBinary
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.database import Base


class OrgType(str, enum.Enum):
    IP = "IP"
    TOO = "TOO"


class TRC(Base):
    __tablename__ = "trcs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(32), nullable=True)
    bin_value = Column(String(12), nullable=True)
    iin_value = Column(String(12), nullable=True)
    message_template = Column(Text, nullable=True)
    green_api_url = Column(String(512), nullable=True)
    green_api_media_url = Column(String(512), nullable=True)
    green_api_id_instance = Column(String(64), nullable=True)
    green_api_api_token = Column(String(255), nullable=True)
    portal_username = Column(String(64), nullable=True, unique=True, index=True)
    portal_password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenants = relationship("Tenant", back_populates="trc", cascade="all, delete-orphan")
    counterparty_phones = relationship(
        "CounterpartyPhone", back_populates="trc", cascade="all, delete-orphan"
    )


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    trc_id = Column(Integer, ForeignKey("trcs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    legal_name = Column(String(255), nullable=False)
    org_type = Column(String(10), nullable=False, default=OrgType.IP.value)
    bin_value = Column(String(12), nullable=True)
    iin_value = Column(String(12), nullable=True)
    phone = Column(String(32), nullable=True)
    message_template = Column(Text, nullable=True)
    green_api_url = Column(String(512), nullable=True)
    green_api_media_url = Column(String(512), nullable=True)
    green_api_id_instance = Column(String(64), nullable=True)
    green_api_api_token = Column(String(255), nullable=True)
    one_c_counterparty_id = Column(String(64), nullable=True)
    one_c_name_match = Column(String(128), nullable=True)
    one_c_login = Column(String(128), nullable=False)
    one_c_password = Column(String(255), nullable=False)
    one_c_base_url = Column(String(512), nullable=True)
    one_c_basic_user = Column(String(128), nullable=True)
    one_c_basic_password = Column(String(255), nullable=True)
    nova_organization_id = Column(Integer, nullable=True)
    nova_mcp_system_type = Column(String(16), nullable=True)
    nova_script_invoices = Column(Integer, nullable=True)
    nova_script_payments = Column(Integer, nullable=True)
    nova_script_counterparties = Column(Integer, nullable=True)
    nova_script_balance = Column(Integer, nullable=True)
    nova_script_invoice_by_id = Column(Integer, nullable=True)
    one_c_connection_mode = Column(String(32), nullable=True)
    # disabled (по умолчанию) / fallback_on_1c_failure / prefer_xlsx — см.
    # app/services/xlsx_import/. Нет отдельного "xlsx_only": tenant_has_1c_credentials()
    # и так вернёт False без one_c_login/password, fallback_on_1c_failure этого
    # достаточно — не нужен третий режим ради того же исхода.
    xlsx_priority = Column(String(32), nullable=False, default="disabled")
    # Ключ в xlsx_import.registry.PARSERS ("maxi_mall" и т.д.) — какой парсер
    # понимает файлы именно этого арендатора. По имени, не по org_id/trc_id:
    # формат файла — свойство того, кто и как его составляет у ТЦ, не самого
    # ТЦ как записи в каталоге. NULL — xlsx для этого арендатора не настроен.
    xlsx_parser_key = Column(String(64), nullable=True)
    portal_username = Column(String(64), nullable=True, unique=True, index=True)
    portal_password_hash = Column(String(255), nullable=True)
    stamp_file_path = Column(String(512), nullable=True)
    signature_file_path = Column(String(512), nullable=True)
    stamp_png = Column(LargeBinary, nullable=True)
    signature_png = Column(LargeBinary, nullable=True)
    invoice_iik = Column(String(34), nullable=True)
    invoice_kbe = Column(String(8), nullable=True)
    invoice_bank_name = Column(String(255), nullable=True)
    invoice_bank_bik = Column(String(16), nullable=True)
    invoice_payment_knp = Column(String(16), nullable=True)
    invoice_supplier_address = Column(Text, nullable=True)
    invoice_executor_name = Column(String(128), nullable=True)
    invoice_contract_text = Column(String(255), nullable=True)
    invoice_due_day = Column(Integer, nullable=True)
    invoice_due_day_utilities = Column(Integer, nullable=True)
    invoice_due_day_operations = Column(Integer, nullable=True)
    # По умолчанию False для всех — глобальная логика в invoice_report.py
    # (_item_name_with_payment_month) выставляет эксплуатацию/маркетинг за
    # ТЕКУЩИЙ месяц счёта (по факту), как для всех остальных ТРЦ. Запрошено
    # 2026-09-02 для Maxi Mall/Astranium: у них эксплуатация и маркетинг
    # выставляются авансом за СЛЕДУЮЩИЙ месяц, как аренда — тот же +1 сдвиг,
    # но только для этих двух категорий и только для тенантов с этим флагом.
    invoice_operations_advance_billing = Column(Boolean, default=False, nullable=False)
    payment_rent_enabled = Column(Boolean, default=True, nullable=False)
    payment_utilities_enabled = Column(Boolean, default=True, nullable=False)
    payment_operations_enabled = Column(Boolean, default=True, nullable=False)
    payment_keywords_rent = Column(Text, nullable=True)
    payment_keywords_utilities = Column(Text, nullable=True)
    payment_keywords_operations = Column(Text, nullable=True)
    # SMTP для email-рассылки контрагентам (пока Maxi Mall)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_use_starttls = Column(Boolean, default=True, nullable=False)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)
    smtp_from_email = Column(String(255), nullable=True)
    # Кнопка «Отключить авто-напоминания для всех» в invoice-client — арендатор
    # ставит на паузу весь почасовой AutoNotificationService для СЕБЯ целиком
    # (все контрагенты), независимо от точечных CounterpartyPhone.auto_notify_paused.
    # Проверяется первым в run_for_tenant, до обращения к 1С.
    auto_notify_paused = Column(Boolean, default=False, nullable=False, server_default="false")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trc = relationship("TRC", back_populates="tenants")


class CounterpartyPhone(Base):
    """Телефон получателя WhatsApp для контрагента из 1С.

    Раньше комментарий утверждал, что 1С OData телефоны не отдаёт — неверно:
    InformationRegister_КонтактнаяИнформация публикуется и содержит их (см.
    odata_1c_client._load_phones_by_counterparty_ref). На COM/Nova-транспорте
    (Maxi Mall и т.п.) аналогичного чтения пока нет — для таких арендаторов
    контрагенты по-прежнему приходят без телефона. В любом случае эта таблица
    остаётся источником истины: значение из 1С — только подсказка при пустой
    записи (см. counterparty_directory в app/api/admin.py), сохранённое здесь
    значение админ может переопределить, и оно не перезаписывается автоматически.
    """
    __tablename__ = "counterparty_phones"
    __table_args__ = (
        UniqueConstraint("trc_id", "one_c_counterparty_id", name="uq_trc_counterparty_phone"),
    )

    id = Column(Integer, primary_key=True, index=True)
    trc_id = Column(Integer, ForeignKey("trcs.id", ondelete="CASCADE"), nullable=False, index=True)
    one_c_counterparty_id = Column(String(64), nullable=False, index=True)
    counterparty_name = Column(String(255), nullable=True)
    contact_name = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=False)
    phone_rent = Column(String(32), nullable=True)
    phone_utilities = Column(String(32), nullable=True)
    phone_operations = Column(String(32), nullable=True)
    # Последняя успешная отправка WhatsApp этому контрагенту — любого рода
    # (ручная /send, массовая /send-debtors, авто-рассылка, /send-file).
    # Проставляется в whatsapp_jobs.deliver_notification/deliver_raw_message.
    last_whatsapp_sent_at = Column(DateTime, nullable=True)
    # Арендатор поставил авто-рассылку на паузу для этого контрагента (кнопка
    # в invoice-client) — AutoNotificationService.run_for_tenant пропускает
    # такого контрагента целиком (все service_type/счета), пока не снимут.
    # Ручную отправку и массовую /send-debtors не затрагивает.
    auto_notify_paused = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trc = relationship("TRC", back_populates="counterparty_phones")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_super = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
