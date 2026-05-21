import copy

import pytest
from django.conf import settings
from django.contrib.auth.signals import user_logged_in


@pytest.fixture(autouse=True)
def disable_audit_login_signal():
    """Avoid AuditLog writes and DB noise during unrelated tests."""
    try:
        from audit.signals import audit_user_login
        user_logged_in.disconnect(audit_user_login)
    except Exception:
        pass
    yield
    try:
        from audit.signals import audit_user_login
        user_logged_in.connect(audit_user_login)
    except Exception:
        pass


@pytest.fixture
def enbek_auth_headers():
    return {'HTTP_AUTHORIZATION': 'Bearer mock_token_123'}


def minimal_template_settings():
    templates = copy.deepcopy(settings.TEMPLATES)
    templates[0]['OPTIONS']['context_processors'] = [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]
    return templates
