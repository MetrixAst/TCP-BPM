from typing import Optional, Tuple, TYPE_CHECKING
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from app.models.catalog import TRC, Tenant


def _build_retrying_session() -> requests.Session:
    """Сессия с ретраями на транспортном уровне для звонков в Green API.

    Green API сам рекомендует бэкофф на 429 (см. их rate-limiter — до 50
    sendMessage/sec на инстанс) — без этого временный всплеск/сетевой сбой
    молча теряет сообщение (send_message просто вернёт False).

    POST разрешён в allowed_methods: 429/5xx здесь означает, что Green API
    запрос не обработал (лимит/перегрузка), а не что сообщение могло уйти
    дважды — повтор безопаснее, чем потерянный счёт. Риск дубликата остаётся
    только на read-timeout после того, как запрос физически ушёл — это редкий
    случай и того же порядка, что и без ретраев (сейчас на таймаут просто
    падаем в тест-инстанс/сдаёмся).

    connect/read ограничены 1 повтором отдельно от status (3): 429/5xx
    возвращаются быстро, retry там почти бесплатен, а вот настоящий "подвис,
    не отвечает" на read-timeout — это полный таймаут запроса (30/120 сек)
    за каждую попытку; без отдельного лимита total=3 на зависшем Green API
    утроил бы время ожидания вместо того, чтобы защищать от сбоев.
    """
    retry = Retry(
        total=3,
        connect=1,
        read=1,
        status=3,
        backoff_factor=1,  # 1s, 2s, 4s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = _build_retrying_session()


def _resolve_green_api_url(*candidates: Optional[str]) -> Optional[str]:
    for raw in candidates:
        url = (raw or "").strip()
        if url.startswith("http://") or url.startswith("https://"):
            return url.rstrip("/")
    return None


class WhatsAppService:
    """Отправка WhatsApp через Green API (вместо Meta Graph API)."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        media_url: Optional[str] = None,
        id_instance: Optional[str] = None,
        api_token: Optional[str] = None,
        sender_label: str = "",
    ):
        self.api_url = (api_url or settings.GREEN_API_URL).rstrip("/")
        self.media_url = (media_url or settings.GREEN_API_MEDIA_URL).rstrip("/")
        self.id_instance = id_instance or settings.GREEN_API_ID_INSTANCE
        self.api_token = api_token or settings.GREEN_API_API_TOKEN
        self.sender_label = sender_label
        self.test_id_instance = settings.GREEN_API_TEST_ID_INSTANCE
        self.test_api_token = settings.GREEN_API_TEST_API_TOKEN
        self.template_name = getattr(settings, "WHATSAPP_TEMPLATE_NAME", "payment_notification")

        # Алиасы для совместимости с тестовым эндпоинтом
        self.access_token = self.api_token
        self.phone_number_id = self.id_instance
        self.test_phone_number_id = self.test_id_instance
        self.api_version = "green-api"

        # idMessage последней успешной отправки этим инстансом — send_message()
        # остаётся bool ради всех существующих вызывающих (deliver_notification и
        # т.д. проверяют `if success:`), так что чтобы не задеть их всех разом,
        # id кладём сюда и читаем сразу после send_message() там, где он нужен
        # для сопоставления с outgoingMessageStatus вебхуком (см. whatsapp_jobs).
        self.last_id_message: Optional[str] = None

    @classmethod
    def for_trc(cls, trc: Optional["TRC"] = None) -> "WhatsAppService":
        """Green API инстанс ТРЦ или глобальный из .env."""
        if trc and trc.green_api_id_instance and trc.green_api_api_token:
            return cls(
                api_url=trc.green_api_url or settings.GREEN_API_URL,
                media_url=trc.green_api_media_url or settings.GREEN_API_MEDIA_URL,
                id_instance=trc.green_api_id_instance,
                api_token=trc.green_api_api_token,
                sender_label=f"ТРЦ {trc.name}",
            )
        return cls(sender_label="глобальный .env")

    @classmethod
    def for_tenant(
        cls, tenant: Optional["Tenant"] = None, trc: Optional["TRC"] = None
    ) -> "WhatsAppService":
        """
        Сначала Green API арендатора (с его WhatsApp), иначе ТРЦ, иначе .env.
        Поле tenant.phone — только подпись; отправка идёт с idInstance Green API.
        """
        if tenant and tenant.green_api_id_instance and tenant.green_api_api_token:
            label = tenant.name
            if tenant.phone:
                label = f"{tenant.name} ({tenant.phone})"
            api_url = _resolve_green_api_url(
                tenant.green_api_url,
                trc.green_api_url if trc else None,
            )
            media_url = _resolve_green_api_url(
                tenant.green_api_media_url,
                trc.green_api_media_url if trc else None,
                api_url,
            )
            return cls(
                api_url=api_url or settings.GREEN_API_URL,
                media_url=media_url or settings.GREEN_API_MEDIA_URL,
                id_instance=tenant.green_api_id_instance,
                api_token=tenant.green_api_api_token,
                sender_label=f"арендатор {label}",
            )
        if tenant and tenant.phone:
            logger.debug(
                f" WARNING: у арендатора «{tenant.name}» указан телефон {tenant.phone}, "
                "но нет Green API idInstance/apiToken — используется инстанс ТРЦ."
            )
        return cls.for_trc(trc)

    def _credentials(self, use_test_number: bool = False) -> Tuple[Optional[str], Optional[str]]:
        if use_test_number and self.test_id_instance and self.test_api_token:
            return self.test_id_instance, self.test_api_token
        return self.id_instance, self.api_token

    def _is_configured(self, use_test_number: bool = False) -> bool:
        id_instance, api_token = self._credentials(use_test_number)
        return bool(id_instance and api_token)

    def get_state_instance(self, use_test_number: bool = False) -> Optional[str]:
        """Статус инстанса в Green API: authorized/notAuthorized/blocked/
        sleepMode/starting/suspended. Во всех состояниях кроме "authorized"
        sendMessage не дойдёт — используется для диагностики/алертов, не в
        горячем пути отправки (лишний round-trip на каждое сообщение того не
        стоит)."""
        id_instance, api_token = self._credentials(use_test_number)
        if not id_instance or not api_token:
            return None
        url = f"{self.api_url}/waInstance{id_instance}/getStateInstance/{api_token}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json().get("stateInstance")
            logger.warning(
                " getStateInstance %s -> %s %s", id_instance, response.status_code, response.text
            )
            return None
        except Exception as e:
            logger.warning(" getStateInstance %s failed: %s", id_instance, e)
            return None

    def set_send_delay(
        self,
        delay_ms: int,
        webhook_url: Optional[str] = None,
        use_test_number: bool = False,
    ) -> bool:
        """Green API's own server-side pacing (SetSettings.
        delaySendMessagesMilliseconds) — сообщения ставятся в FIFO-очередь на
        стороне Green API и уходят не чаще этого интервала, независимо от
        того, как быстро наш код их шлёт. Green API рекомендует ~1 сообщение/
        мин для массовых рассылок (иначе выглядит как автоматизация и
        банится — см. инцидент 2026-09-09: 111 сообщений за минуту, инстанс
        временно заблокирован, 104 из них не дошли). Работает как второй
        уровень защиты поверх собственной паузы kafka_worker
        (settings.WHATSAPP_SEND_DELAY_SECONDS) — на случай прямой отправки в
        обход воркера. Диапазон 500-600000 мс — ограничение самого Green API.

        webhook_url: обнаружено 2026-09-10 (проверка через getSettings на
        реальном инстансе 720122720226) — webhookUrl был пустой и
        outgoingAPIMessageWebhook="no", то есть Green API вообще не звал наш
        /api/webhooks/green-api ни разу. Без этого весь код на стороне
        _process_green_api_webhook (см. whatsapp_jobs.py) держит статус SENT
        вечно — реальное подтверждение доставки просто никогда не приходит.
        outgoingAPIMessageWebhook (а не outgoingMessageWebhook) — потому что
        наши сообщения всегда уходят через sendMessage/sendFileByUpload
        (API), а не с привязанного телефона."""
        id_instance, api_token = self._credentials(use_test_number)
        if not id_instance or not api_token:
            return False
        url = f"{self.api_url}/waInstance{id_instance}/setSettings/{api_token}"
        payload: dict = {"delaySendMessagesMilliseconds": delay_ms}
        if webhook_url:
            payload["webhookUrl"] = webhook_url
            payload["outgoingAPIMessageWebhook"] = "yes"
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                return True
            logger.warning(
                "SetSettings delay failed instance=%s: %s %s",
                id_instance, response.status_code, response.text,
            )
            return False
        except Exception as e:
            logger.warning("SetSettings delay failed instance=%s: %s", id_instance, e)
            return False

    def get_today_outgoing_count(self, use_test_number: bool = False) -> Optional[int]:
        """Реальное число исходящих сообщений с этого номера СЕГОДНЯ (по
        Astana), через Green API lastOutgoingMessages — включая ручные
        (sendByApi=false). Обнаружено 2026-09-10: менеджер может переписываться
        с этого же номера вручную (живая проверка — 42 из 138 исходящих за
        24ч были sendByApi=false), а WhatsApp/Green API банят по общему
        трафику номера, не по доле нашего приложения. Наш собственный
        дневной счётчик (_daily_send_count_for_tenant в whatsapp_jobs.py)
        считает только свои отправки из БД и этого не видит.

        Возвращает None при сбое запроса — вызывающий код сам решает, на что
        упасть (не блокируем отправку целиком из-за сетевого сбоя стороннего
        API)."""
        from datetime import datetime
        from app.services.auto_notification_service import astana_now, ASTANA_TZ

        id_instance, api_token = self._credentials(use_test_number)
        if not id_instance or not api_token:
            return None

        now = astana_now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        minutes_since_midnight = int((now - midnight).total_seconds() // 60) + 1

        url = f"{self.api_url}/waInstance{id_instance}/lastOutgoingMessages/{api_token}"
        try:
            response = requests.get(url, params={"minutes": minutes_since_midnight}, timeout=15)
            if response.status_code != 200:
                logger.warning(
                    "lastOutgoingMessages instance=%s -> %s %s",
                    id_instance, response.status_code, response.text,
                )
                return None
            items = response.json()
            if not isinstance(items, list):
                return None
            count = 0
            for item in items:
                timestamp = item.get("timestamp")
                if timestamp is None:
                    # нет таймстампа — лучше переоценить лимит, чем пропустить его
                    count += 1
                    continue
                sent_at = datetime.fromtimestamp(timestamp, tz=ASTANA_TZ)
                if sent_at >= midnight:
                    count += 1
            return count
        except Exception as e:
            logger.warning("lastOutgoingMessages failed instance=%s: %s", id_instance, e)
            return None

    def send_message(
        self,
        phone_number: str,
        message: str,
        file_path: Optional[str] = None,
        use_test_number: bool = False,
        use_template: bool = False,
    ) -> bool:
        id_instance, api_token = self._credentials(use_test_number)
        self.last_id_message = None

        if not id_instance or not api_token:
            logger.debug(" Green API not configured. Set GREEN_API_ID_INSTANCE and GREEN_API_API_TOKEN in .env")
            return False

        try:
            phone = self._normalize_phone(phone_number)
            who = f" ({self.sender_label})" if self.sender_label else ""
            logger.debug(f" Using Green API instance {id_instance}{who}")

            if file_path and Path(file_path).exists():
                logger.debug(" Sending file with caption via Green API...")
                success = self._send_template_with_document(
                    phone, message, file_path, id_instance, api_token
                )
                if not success:
                    logger.debug(" File send failed, retrying as document...")
                    success = self._send_with_file(phone, message, file_path, id_instance, api_token)
            else:
                logger.debug(" No file. Sending text via Green API...")
                success = self._send_text(phone, message, id_instance, api_token)

            if not success and not use_test_number and self.test_id_instance and self.test_api_token:
                logger.debug(" Main instance failed, trying test instance...")
                return self.send_message(phone_number, message, file_path, use_test_number=True)

            return success

        except Exception as e:
            logger.debug(f" Error sending WhatsApp message: {e}")
            if not use_test_number and self.test_id_instance and self.test_api_token:
                try:
                    return self.send_message(
                        phone_number, message, file_path, use_test_number=True
                    )
                except Exception:
                    pass
            return False

    def _chat_id(self, phone_number: str) -> str:
        return f"{phone_number}@c.us"

    def _send_text(
        self,
        phone_number: str,
        message: str,
        id_instance: Optional[str] = None,
        api_token: Optional[str] = None,
    ) -> bool:
        try:
            id_instance = id_instance or self.id_instance
            api_token = api_token or self.api_token
            if not id_instance or not api_token:
                return False

            url = f"{self.api_url}/waInstance{id_instance}/sendMessage/{api_token}"
            payload = {
                "chatId": self._chat_id(phone_number),
                "message": message,
            }
            headers = {"Content-Type": "application/json"}

            logger.debug(f" Green API sendMessage to {payload['chatId']}")
            response = _session.post(url, json=payload, headers=headers, timeout=30)

            logger.debug(f" Response status: {response.status_code}")
            logger.debug(f" Response body: {response.text}")

            if response.status_code == 200:
                data = response.json()
                self.last_id_message = data.get("idMessage")
                logger.debug(f" Message sent. idMessage: {data.get('idMessage', 'unknown')}")
                return True

            logger.debug(f" Failed to send text: {response.status_code} {response.text}")
            return False

        except Exception as e:
            logger.debug(f" Error sending text message: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _send_text_with_template(
        self,
        phone_number: str,
        message: str,
        id_instance: Optional[str] = None,
        api_token: Optional[str] = None,
        template_params: Optional[dict] = None,
        use_hello_world: bool = False,
    ) -> bool:
        # Green API не использует шаблоны Meta — отправляем обычный текст
        return self._send_text(phone_number, message, id_instance, api_token)

    def _send_template_with_document(
        self,
        phone_number: str,
        message: str,
        file_path: str,
        id_instance: Optional[str] = None,
        api_token: Optional[str] = None,
    ) -> bool:
        return self._send_with_file(phone_number, message, file_path, id_instance, api_token)

    def _send_with_file(
        self,
        phone_number: str,
        message: str,
        file_path: str,
        id_instance: Optional[str] = None,
        api_token: Optional[str] = None,
    ) -> bool:
        try:
            id_instance = id_instance or self.id_instance
            api_token = api_token or self.api_token
            if not id_instance or not api_token:
                return False

            url = (
                f"{self.media_url}/waInstance{id_instance}"
                f"/sendFileByUpload/{api_token}"
            )
            file_name = Path(file_path).name
            chat_id = self._chat_id(phone_number)

            with open(file_path, "rb") as f:
                files = {"file": (file_name, f, self._get_content_type(Path(file_path).suffix))}
                data = {
                    "chatId": chat_id,
                    "fileName": file_name,
                }
                if message:
                    data["caption"] = message[:1024]

                logger.debug(f" Green API sendFileByUpload to {chat_id}, file: {file_name}")
                response = _session.post(url, data=data, files=files, timeout=120)

            logger.debug(f" Response status: {response.status_code}")
            logger.debug(f" Response body: {response.text}")

            if response.status_code == 200:
                resp_data = response.json()
                self.last_id_message = resp_data.get("idMessage")
                logger.debug(f" File sent. idMessage: {resp_data.get('idMessage', 'unknown')}")
                return True

            logger.debug(f" Failed to send file: {response.status_code} {response.text}")
            return False

        except Exception as e:
            logger.debug(f" Error sending file: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _upload_media(self, file_path: str, phone_number_id: Optional[str] = None) -> Optional[str]:
        # Green API загружает файл в одном запросе sendFileByUpload
        return "green-api-upload-inline"

    def _get_media_type(self, file_ext: str) -> str:
        image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
        video_extensions = [".mp4", ".3gp", ".mov"]
        audio_extensions = [".mp3", ".ogg", ".amr", ".m4a"]

        if file_ext in image_extensions:
            return "image"
        if file_ext in video_extensions:
            return "video"
        if file_ext in audio_extensions:
            return "audio"
        return "document"

    def _get_content_type(self, file_ext: str) -> str:
        content_types = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        return content_types.get(file_ext.lower(), "application/octet-stream")

    def _normalize_phone(self, phone: str) -> str:
        phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")
        digits = "".join(filter(str.isdigit, phone))

        if digits.startswith("7"):
            return digits
        if digits.startswith("8"):
            return f"7{digits[1:]}"
        if len(digits) == 10:
            return f"7{digits}"
        return digits
