from django.db import migrations

# ТЗ 4.1: владелец видит только агрегаты — без детальных счетов и реестра платежей.
# Кредитную модель и сценарии он только просматривает: управление — у CFO (_can_manage_credit).
OWNER_REVOKE = ['finance_invoices', 'finance_registers']


def forwards(apps, schema_editor):
    AppPermission = apps.get_model('account', 'AppPermission')
    PermissionProfile = apps.get_model('account', 'PermissionProfile')
    owner = PermissionProfile.objects.filter(role='owner').first()
    if owner:
        owner.permissions.remove(*AppPermission.objects.filter(code__in=OWNER_REVOKE))


def backwards(apps, schema_editor):
    AppPermission = apps.get_model('account', 'AppPermission')
    PermissionProfile = apps.get_model('account', 'PermissionProfile')
    owner = PermissionProfile.objects.filter(role='owner').first()
    if owner:
        owner.permissions.add(*AppPermission.objects.filter(code__in=OWNER_REVOKE))


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0013_invoicesyncrun_generatedinvoice_counterparty_name_and_more'),
        ('account', '0031_permission_matrix'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
