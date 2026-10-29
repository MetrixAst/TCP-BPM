from django.db import migrations

CODE = 'plans_view_all'


def forwards(apps, schema_editor):
    AppPermission = apps.get_model('account', 'AppPermission')
    PermissionProfile = apps.get_model('account', 'PermissionProfile')

    permission, _ = AppPermission.objects.update_or_create(
        code=CODE,
        defaults={
            'block': 'plans', 'operation': 'view', 'category': 'tasks',
            'label': 'Планы отделов: просмотр всех отделов', 'is_active': True,
        },
    )
    for profile in PermissionProfile.objects.filter(role__in=['administrator', 'owner']):
        profile.permissions.add(permission)


def backwards(apps, schema_editor):
    apps.get_model('account', 'AppPermission').objects.filter(code=CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0001_initial'),
        ('account', '0030_metrix_permissions'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
