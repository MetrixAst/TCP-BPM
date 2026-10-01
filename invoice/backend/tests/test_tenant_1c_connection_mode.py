"""Regression coverage for app/services/tenant_1c.py connection-mode resolution.

Incident 2026-08-11: tenant_id=4 (ИП MOON, nova_organization_id=127) had
one_c_connection_mode='odata_direct' with an empty one_c_base_url. The code
silently fell back to the global settings.ONE_C_BASE_URL — a stub address
belonging to no real tenant — and "successfully" synced 0 records for days
with no error anywhere. tenant_uses_nova_org() and build_integration_for_tenant()
are the two functions that decide which 1C backend a tenant talks to; these
tests pin down that exact decision for every mode/field combination in play.
"""

from unittest.mock import patch

import pytest

from app.models.catalog import Tenant
from app.services.tenant_1c import (
    CONNECTION_MODE_AUTO,
    CONNECTION_MODE_NOVA,
    CONNECTION_MODE_ODATA,
    build_integration_for_tenant,
    tenant_uses_nova_org,
)


@pytest.fixture(autouse=True)
def no_network_odata_client():
    """Routing decisions under test don't need a real OData connection —
    only whether Integration1C picked the odata branch at all."""
    with patch("app.services.integration_1c.OData1CClient") as mock_client:
        mock_client.return_value = object()
        yield mock_client


def make_tenant(**overrides) -> Tenant:
    defaults = dict(
        id=1,
        trc_id=1,
        name="Test Tenant",
        legal_name="Test Tenant LLP",
        one_c_login="",
        one_c_password="",
        one_c_base_url=None,
        one_c_basic_user=None,
        one_c_basic_password=None,
        one_c_connection_mode=None,
        nova_organization_id=None,
    )
    defaults.update(overrides)
    return Tenant(**defaults)


def test_moon_incident_regression_odata_direct_with_empty_base_url_errors():
    """The exact tenant_id=4 config from 2026-08-11: must fail loudly, not silently
    fall back to the shared global ONE_C_BASE_URL stub."""
    tenant = make_tenant(
        id=4,
        one_c_connection_mode=CONNECTION_MODE_ODATA,
        one_c_base_url="",
        nova_organization_id=127,
        one_c_login="odata.user",
        one_c_password="secret",
    )

    assert tenant_uses_nova_org(tenant) is False  # explicit odata_direct always wins

    integration = build_integration_for_tenant(tenant)

    assert integration.client is None
    assert integration.last_error
    assert "base_url" in integration.last_error


def test_odata_direct_with_real_base_url_is_unaffected():
    tenant = make_tenant(
        one_c_connection_mode=CONNECTION_MODE_ODATA,
        one_c_base_url="https://1cstart.example.kz/odata/standard.odata/",
        one_c_login="odata.user",
        one_c_password="secret",
    )

    integration = build_integration_for_tenant(tenant)

    assert integration.last_error is None
    assert integration._uses_nova is False


def test_nova_org_mode_uses_nova_client():
    tenant = make_tenant(
        one_c_connection_mode=CONNECTION_MODE_NOVA,
        nova_organization_id=127,
    )

    assert tenant_uses_nova_org(tenant) is True

    integration = build_integration_for_tenant(tenant)

    assert integration.last_error is None
    assert integration._uses_nova is True


def test_auto_mode_prefers_nova_when_no_real_odata_url_configured():
    """Matches CityMall/Maxi Mall's actual local config: mode=auto (or unset),
    base_url empty, login set — must resolve to nova_org, not the global stub."""
    tenant = make_tenant(
        one_c_connection_mode=CONNECTION_MODE_AUTO,
        nova_organization_id=118,
        one_c_base_url="",
        one_c_login="odata.user",
        one_c_password="secret",
    )

    assert tenant_uses_nova_org(tenant) is True


def test_auto_mode_uses_odata_when_real_odata_url_present():
    tenant = make_tenant(
        one_c_connection_mode=CONNECTION_MODE_AUTO,
        nova_organization_id=118,
        one_c_base_url="https://1cstart.example.kz/odata/standard.odata/",
        one_c_login="odata.user",
        one_c_password="secret",
    )

    assert tenant_uses_nova_org(tenant) is False

    integration = build_integration_for_tenant(tenant)

    assert integration.last_error is None
    assert integration._uses_nova is False


def test_missing_login_or_password_still_errors_when_not_using_nova():
    tenant = make_tenant(
        one_c_connection_mode=CONNECTION_MODE_ODATA,
        one_c_base_url="https://1cstart.example.kz/odata/standard.odata/",
        one_c_login="",
        one_c_password="",
    )

    integration = build_integration_for_tenant(tenant)

    assert integration.client is None
    assert "логин или пароль" in integration.last_error


def test_nova_mode_without_org_id_does_not_crash():
    """mode=nova_org but nova_organization_id missing: logs a warning (see
    build_integration_for_tenant) and falls through to the odata branch instead
    of using Nova — must not raise."""
    tenant = make_tenant(
        one_c_connection_mode=CONNECTION_MODE_NOVA,
        nova_organization_id=None,
        one_c_base_url="https://1cstart.example.kz/odata/standard.odata/",
        one_c_login="odata.user",
        one_c_password="secret",
    )

    integration = build_integration_for_tenant(tenant)

    assert integration._uses_nova is False
    assert integration.last_error is None


def test_no_tenant_does_not_crash():
    """No tenant selected: must not raise. (Whether a client ends up set depends
    on global ONE_C_* defaults, which is unrelated to tenant mode-resolution —
    out of scope here.)"""
    integration = build_integration_for_tenant(None)

    assert integration is not None
