"""Кэш структурированных данных счёта (не PDF-байтов) для генерации PDF без
похода в живую 1С на каждый показ — см. app/services/invoice_pdf_cache.py.

JSON, не Postgres-only JSONB (в отличие от CounterpartyCache.data) —
намеренно: эта таблица никогда не фильтруется ПО СОДЕРЖИМОМУ payload'а,
только читается целиком по (tenant_id, invoice_id), так что портируемость
важнее индексируемости — и, что практичнее, это позволяет тестировать
сервис на in-memory SQLite тестовой БД, а не мокать каждый вызов (см.
tests/conftest.py — CounterpartyCache туда специально не включена именно
из-за JSONB)."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.db.database import Base


class InvoicePdfPayload(Base):
    __tablename__ = "invoice_pdf_payloads"

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    # COM invoice_id не гарантированно уникален между 1С-организациями (см.
    # find_cached_invoice_pdf в invoice_access.py про ту же причину) —
    # therefore tenant_id часть первичного ключа, не просто индекс.
    invoice_id = Column(String(64), primary_key=True, nullable=False)
    # 1С-нативные данные ТОЛЬКО — реквизиты поставщика (ИИК/БИК/КБе/банк/
    # адрес/КНП/договор) сюда намеренно не попадают, домешиваются заново из
    # живой записи Tenant при каждом чтении. См. invoice_pdf_cache.py
    # docstring про то, почему кэшировать их было бы риском "неверный счёт
    # для оплаты" после правки реквизитов в админке.
    #
    # NULL — не "закэшировано пустое", а "строка существует только ради
    # троттлинга force-refresh" (см. last_force_refresh_attempt_at): счёт,
    # что ни разу не прошёл гейт валидности, иначе никогда не получил бы
    # строку в этой таблице вообще — и тогда троттлить попытки force-refresh
    # было бы нечем, ровно та дыра, ради которой это поле троттлинга и
    # существует.
    payload = Column(JSON, nullable=True)
    source = Column(String(16), nullable=True)  # "nova" | "odata"; NULL пока payload NULL
    fetched_at = Column(DateTime(timezone=True), nullable=True)  # NULL пока payload NULL
    # Троттлинг force-refresh — не когда данные обновились, а когда в
    # последний раз ХОТЬ КТО-ТО пытался их обновить, успешно или нет.
    # Отдельно от fetched_at: неудачная попытка не должна давать право
    # тут же попробовать ещё раз и снова забить Nova живыми запросами.
    last_force_refresh_attempt_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
