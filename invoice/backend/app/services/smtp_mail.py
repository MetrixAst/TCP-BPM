"""SMTP helpers for tenant email mailings (Maxi Mall и др.)."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger(__name__)


def check_smtp_connection(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    use_starttls: bool = True,
    from_email: Optional[str] = None,
    timeout: float = 20.0,
) -> dict:
    """
    Проверка SMTP: EHLO + AUTH (+ STARTTLS при port 587).
    Не отправляет письмо — только логин.
    """
    host = (host or "").strip()
    username = (username or "").strip()
    password = password or ""
    from_addr = (from_email or username or "").strip()
    if not host:
        return {"ok": False, "error": "Укажите SMTP host"}
    if not port or int(port) < 1:
        return {"ok": False, "error": "Укажите SMTP port"}
    if not username or not password:
        return {"ok": False, "error": "Укажите SMTP логин и пароль"}

    port_i = int(port)
    try:
        if use_starttls or port_i == 587:
            with smtplib.SMTP(host, port_i, timeout=timeout) as smtp:
                smtp.ehlo()
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(username, password)
        elif port_i == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port_i, context=context, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.login(username, password)
        else:
            with smtplib.SMTP(host, port_i, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.login(username, password)
        return {
            "ok": True,
            "message": (
                f"SMTP OK: {host}:{port_i}"
                f"{' STARTTLS' if use_starttls or port_i == 587 else ''}"
                f", user={username}"
                + (f", from={from_addr}" if from_addr else "")
            ),
        }
    except smtplib.SMTPAuthenticationError as exc:
        logger.warning("SMTP auth failed host=%s: %s", host, exc)
        return {"ok": False, "error": f"Ошибка авторизации SMTP: {exc}"}
    except Exception as exc:
        logger.warning("SMTP test failed host=%s: %s", host, exc)
        return {"ok": False, "error": str(exc)}


def send_smtp_test_email(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    to_email: str,
    use_starttls: bool = True,
    from_email: Optional[str] = None,
    timeout: float = 20.0,
) -> dict:
    """Опционально: отправить короткое тестовое письмо на to_email."""
    check = check_smtp_connection(
        host=host,
        port=port,
        username=username,
        password=password,
        use_starttls=use_starttls,
        from_email=from_email,
        timeout=timeout,
    )
    if not check.get("ok"):
        return check

    host = (host or "").strip()
    username = (username or "").strip()
    from_addr = (from_email or username).strip()
    to_addr = (to_email or "").strip()
    if not to_addr:
        return {"ok": False, "error": "Укажите email получателя теста"}

    msg = EmailMessage()
    msg["Subject"] = "Тест SMTP — реестр оплат"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(
        "Это тестовое письмо из админки модуля реестра оплат.\n"
        "SMTP настроен корректно.\n"
    )

    port_i = int(port)
    try:
        if use_starttls or port_i == 587:
            with smtplib.SMTP(host, port_i, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(msg)
        elif port_i == 465:
            with smtplib.SMTP_SSL(
                host, port_i, context=ssl.create_default_context(), timeout=timeout
            ) as smtp:
                smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port_i, timeout=timeout) as smtp:
                smtp.login(username, password)
                smtp.send_message(msg)
        return {"ok": True, "message": f"Тестовое письмо отправлено на {to_addr}"}
    except Exception as exc:
        logger.warning("SMTP send test failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def send_smtp_email_with_attachment(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    to_email: str,
    subject: str,
    body: str,
    attachment_path: str,
    attachment_filename: Optional[str] = None,
    use_starttls: bool = True,
    from_email: Optional[str] = None,
    timeout: float = 60.0,
) -> dict:
    """Отправить письмо с одним вложением (PDF счёта)."""
    host = (host or "").strip()
    username = (username or "").strip()
    password = password or ""
    from_addr = (from_email or username or "").strip()
    to_addr = (to_email or "").strip()
    path = (attachment_path or "").strip()

    if not host:
        return {"ok": False, "error": "Укажите SMTP host в настройках арендатора"}
    if not username or not password:
        return {"ok": False, "error": "Укажите SMTP логин и пароль в настройках арендатора"}
    if not to_addr or "@" not in to_addr:
        return {"ok": False, "error": "Некорректный email получателя"}
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "PDF счёта не найден для отправки"}

    filename = (attachment_filename or os.path.basename(path) or "invoice.pdf").strip()
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"

    msg = EmailMessage()
    msg["Subject"] = (subject or "Счёт на оплату").strip()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body or "Во вложении счёт на оплату.\n")

    try:
        with open(path, "rb") as fh:
            pdf_bytes = fh.read()
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=filename,
        )
    except OSError as exc:
        return {"ok": False, "error": f"Не удалось прочитать PDF: {exc}"}

    port_i = int(port or 587)
    try:
        if use_starttls or port_i == 587:
            with smtplib.SMTP(host, port_i, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(msg)
        elif port_i == 465:
            with smtplib.SMTP_SSL(
                host, port_i, context=ssl.create_default_context(), timeout=timeout
            ) as smtp:
                smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port_i, timeout=timeout) as smtp:
                smtp.login(username, password)
                smtp.send_message(msg)
        return {"ok": True, "message": f"Счёт отправлен на {to_addr}"}
    except smtplib.SMTPAuthenticationError as exc:
        logger.warning("SMTP auth failed host=%s: %s", host, exc)
        return {"ok": False, "error": f"Ошибка авторизации SMTP: {exc}"}
    except Exception as exc:
        logger.warning("SMTP invoice send failed host=%s: %s", host, exc)
        return {"ok": False, "error": str(exc)}
