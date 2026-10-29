from django.db import migrations

DISPATCHER_PROFILE = "Диспетчер заявок"
DISPATCHER_CODES = ['dashboard', 'profile', 'service_requests', 'tickets_dispatch', 'tenants']


def forwards(apps, schema_editor):
    AppPermission = apps.get_model('account', 'AppPermission')
    PermissionProfile = apps.get_model('account', 'PermissionProfile')

    profile, _ = PermissionProfile.objects.get_or_create(
        name=DISPATCHER_PROFILE,
        defaults={
            'is_system': False,
            'description': 'Администраторы ТРЦ: видят все заявки арендаторов, распределяют их по отделам и исполнителям',
        },
    )
    profile.permissions.add(*AppPermission.objects.filter(code__in=DISPATCHER_CODES))


def backwards(apps, schema_editor):
    PermissionProfile = apps.get_model('account', 'PermissionProfile')
    PermissionProfile.objects.filter(name=DISPATCHER_PROFILE, is_system=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0031_permission_matrix'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
