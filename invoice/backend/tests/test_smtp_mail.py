from app.services.smtp_mail import check_smtp_connection


def test_smtp_connection_requires_host():
    result = check_smtp_connection(
        host="",
        port=587,
        username="a@b.c",
        password="x",
    )
    assert result["ok"] is False
    assert "host" in (result.get("error") or "").lower()


def test_smtp_connection_requires_credentials():
    result = check_smtp_connection(
        host="smtp.example.com",
        port=587,
        username="",
        password="",
    )
    assert result["ok"] is False
