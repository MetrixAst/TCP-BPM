import json
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Any, Dict
from pydantic import Field, model_validator

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

_INSECURE_SECRET_KEYS = {"dev-secret-key-change-in-production", "change-me-long-random-string"}


def resolve_env_file() -> str:
    """Файл окружения: APP_ENV_FILE из Docker/CI, иначе .env / development / production / test."""
    explicit = (os.getenv("APP_ENV_FILE") or "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        if path.is_file():
            return str(path)
    # Локально чаще всего есть backend/.env с DATABASE_URL.
    # .env.production раньше имел приоритет и ломал `python run.py` без APP_ENV_FILE.
    for name in (".env", ".env.development", ".env.production", ".env.test"):
        candidate = BACKEND_ROOT / name
        if candidate.is_file():
            return str(candidate)
    return str(BACKEND_ROOT / ".env")


def bootstrap_env_from_file() -> None:
    path = resolve_env_file()
    if Path(path).is_file():
        load_dotenv(path, override=False)


def _build_database_url_from_parts() -> str:
    host = os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST")
    user = os.getenv("POSTGRES_USER") or os.getenv("DB_USER")
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD")
    db = os.getenv("POSTGRES_DB") or os.getenv("DB_NAME")
    port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or "5432"
    if host and user and password is not None and db:
        return (
            f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{db}"
        )
    return ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_ignore_empty=True,
    )

    DATABASE_URL: str = Field(default="", description="PostgreSQL connection URL")
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ENVIRONMENT: str = "development"
    SENTRY_DSN: str = ""
    # Читаются через os.getenv (tenant_stamp, whatsapp_jobs); объявлены, чтобы
    # env-файл с ними проходил валидацию (extra="forbid").
    TENANT_UPLOADS_DIR: str = ""
    WHATSAPP_OUTBOX_DIR: str = ""
    CORS_ORIGINS: List[str] = [
        "http://localhost:3003",
        "http://localhost:3004",
        "http://localhost:5173",
        "http://127.0.0.1:3003",
        "http://127.0.0.1:3004",
        "http://127.0.0.1:5173",
    ]
    JWT_ALGORITHM: str = "HS256"
    ADMIN_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    SUPER_ADMIN_USERNAME: str = "super_metrix"
    SUPER_ADMIN_PASSWORD: str = ""
    ONE_C_API_URL: str = "http://localhost:8005"
    ONE_C_API_KEY: str = "stub-key"
    

    ONE_C_BASE_URL: str = "https://supersecret.irm.kz/tgb/hs/api/v1"
    ONE_C_BASIC_AUTH_USER: str = "Admin"
    ONE_C_BASIC_AUTH_PASSWORD: str = ""
    ONE_C_API_USER: str = "admin"
    ONE_C_API_PASSWORD: str = ""
    # Comma-separated OData entity names (if 1C publishes non-standard names)
    ONE_C_ODATA_COUNTERPARTY_ENTITIES: str = ""
    ONE_C_ODATA_INVOICE_ENTITIES: str = ""

    # Nova backend (MCP/COM + OData org resolve)
    NOVA_BACKEND_URL: str = "https://backend.mynova.kz"
    NOVA_ADMIN_EMAIL: str = ""
    NOVA_ADMIN_PASSWORD: str = ""
    NOVA_MCP_RELAY_URL: str = "https://rk.mcp.uzun.kz"
    NOVA_MCP_RELAY_API_KEY: str = ""
    # Fallback agent_id по nova_organization_id, если Nova admin API недоступен (401 на worker).
    # Сверять с актуальным BUH-API-reference (window.BUH_ORG) — agent_id меняется при
    # пересоздании агента на стороне Nova, этот словарь сам не обновляется.
    NOVA_MCP_AGENT_BY_ORG: Dict[str, str] = Field(
        default_factory=lambda: {
            "119": "agent-2418e2fa-9687-4c6e-a86e-5bf29fdf295d",
        }
    )
    # COM: portal PDF only when getpdf/script PDF unavailable (default off)
    NOVA_COM_PORTAL_PDF_FALLBACK: bool = False

    GREEN_API_URL: str = "https://api.greenapi.com"
    GREEN_API_MEDIA_URL: str = "https://media.greenapi.com"
    GREEN_API_ID_INSTANCE: str = ""
    GREEN_API_API_TOKEN: str = ""
    GREEN_API_TEST_ID_INSTANCE: str = ""
    GREEN_API_TEST_API_TOKEN: str = ""

    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_TEST_PHONE_NUMBER_ID: str = ""
    WHATSAPP_API_VERSION: str = "v22.0"
    META_APP_SECRET: str = ""
    META_APP_ID: str = ""
    WHATSAPP_PHONE_CERTIFICATE: str = ""
    WHATSAPP_CERTIFICATE: str = ""
    ID_WhatsApp_Business: str = ""
    WHATSAPP_TEMPLATE_NAME: str = "payment_notification"

    # Kafka — все параметры из ENV (локально PLAINTEXT, в кластере SASL_PLAINTEXT)
    KAFKA_ENABLED: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"
    KAFKA_SASL_MECHANISM: str = "PLAIN"
    KAFKA_SASL_USERNAME: str = ""
    KAFKA_SASL_PASSWORD: str = ""
    KAFKA_TOPIC_WHATSAPP: str = "invoice.whatsapp.send"
    KAFKA_TOPIC_WEBHOOK: str = "invoice.webhooks.incoming"
    KAFKA_TOPIC_PAYMENTS_SYNC: str = "invoice.payments.sync"
    KAFKA_CONSUMER_GROUP: str = "invoice-registry-workers"

    # Реальный инцидент 2026-09-09: 111 WhatsApp-счетов должникам (Maxi Mall,
    # "Astranium") ушли в очередь и были отправлены Green API в течение одной
    # минуты — инстанс словил временную блокировку от WhatsApp меньше чем на
    # десятке сообщений, и 104 из 111 застряли на статусе "sent" (доставлены
    # ни разу, хотя Green API принял запрос успешно). Ни kafka_worker, ни
    # массовая рассылка раньше не делали ПАУЗУ между сообщениями вообще — см.
    # памятку GREEN API по массовым рассылкам (~1 сообщение/мин, не более
    # ~200/сутки на инстанс, иначе выглядит как автоматизация и банится).
    WHATSAPP_SEND_DELAY_SECONDS: int = 45
    WHATSAPP_DAILY_SEND_CAP: int = 200

    @model_validator(mode="after")
    def require_postgresql(self) -> "Settings":
        url = (self.DATABASE_URL or "").strip().lower()
        if not url.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be set to a PostgreSQL connection string")
        return self

    @model_validator(mode="after")
    def require_secret_key_in_production(self) -> "Settings":
        # SECRET_KEY подписывает admin/portal JWT: с дефолтным значением любой
        # может выпустить себе токен super_metrix.
        if self.ENVIRONMENT == "production" and (
            self.SECRET_KEY in _INSECURE_SECRET_KEYS or len(self.SECRET_KEY) < 32
        ):
            raise ValueError("SECRET_KEY must be set to a random string of 32+ chars in production")
        return self

    @model_validator(mode="before")
    @classmethod
    def resolve_database_url(cls, data: Any) -> Any:
        if isinstance(data, dict):
            url = (data.get("DATABASE_URL") or data.get("database_url") or "").strip()
            if not url:
                built = _build_database_url_from_parts()
                if built:
                    data["DATABASE_URL"] = built
        return data

    @model_validator(mode='before')
    @classmethod
    def parse_cors_origins(cls, data: Any) -> Any:

        if isinstance(data, dict):
            cors_origins = data.get('CORS_ORIGINS') or data.get('cors_origins')
            if cors_origins and isinstance(cors_origins, str):
                raw = cors_origins.strip()
                if raw.startswith('['):
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, list):
                            data['CORS_ORIGINS'] = [str(o).strip() for o in parsed if str(o).strip()]
                    except json.JSONDecodeError:
                        pass
                else:
                    data['CORS_ORIGINS'] = [
                        origin.strip() for origin in raw.split(',') if origin.strip()
                    ]

            agents = data.get('NOVA_MCP_AGENT_BY_ORG')
            if agents and isinstance(agents, str):
                raw_agents = agents.strip()
                if raw_agents:
                    try:
                        parsed = json.loads(raw_agents)
                        if isinstance(parsed, dict):
                            data['NOVA_MCP_AGENT_BY_ORG'] = {
                                str(k): str(v).strip()
                                for k, v in parsed.items()
                                if str(v).strip()
                            }
                    except json.JSONDecodeError:
                        pass

            if 'WHATSAPP_CERTIFICATE' in data and not data.get('WHATSAPP_PHONE_CERTIFICATE'):
                data['WHATSAPP_PHONE_CERTIFICATE'] = data.pop('WHATSAPP_CERTIFICATE')
            

            if 'ID_WhatsApp_Business' in data and not data.get('META_APP_ID'):
                data['META_APP_ID'] = data.pop('ID_WhatsApp_Business')
        
        return data


bootstrap_env_from_file()
settings = Settings()
