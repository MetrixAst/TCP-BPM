"""Создаёт invoice/backend/.env.local для локального стенда (не коммитится).

Существующий файл не перезаписывается.
"""
import secrets
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "backend" / ".env.local"
if path.exists():
    print(f"{path} уже есть, не трогаю")
else:
    path.write_text(
        "\n".join(
            [
                f"SECRET_KEY={secrets.token_urlsafe(48)}",
                "SUPER_ADMIN_USERNAME=super_metrix",
                f"SUPER_ADMIN_PASSWORD={secrets.token_urlsafe(12)}",
                # Ключи для заглушки Green API: без них сервис считает WhatsApp ненастроенным.
                "GREEN_API_ID_INSTANCE=1100000000",
                "GREEN_API_API_TOKEN=local-mock-token",
                "",
            ]
        )
    )
    path.chmod(0o600)
    print(f"создан {path}")
