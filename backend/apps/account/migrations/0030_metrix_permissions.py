from django.db import migrations


NEW_PERMISSIONS = [
    ("rounds_monitor",   "ecopark",  "view",   "general", "Эксплуатация: журнал обходов и история помещений"),
    ("edit_tenants",     "tenants",  "edit",   "tenants", "Арендаторы: редактирование, удаление, архив"),
    ("tickets_dispatch", "requests", "assign", "general", "Заявки: распределение и перенаправление (диспетчер)"),
]

RELABEL = {
    "hr_companies": ("hr", "edit", "HR: оргструктура (компании, отделы, должности)"),
    "hr_positions": ("hr", "edit", "HR: справочник должностей"),
    "hr_journal":   ("hr", "view", "HR: журнал и реестр посещаемости (все отделы)"),
}

GRANTS = {
    "administrator": ["rounds_monitor", "edit_tenants", "tickets_dispatch"],
    "owner": ["rounds_monitor", "hr_journal"],
}

SECURITY_PROFILE = "Служба безопасности (просмотр)"


def forwards(apps, schema_editor):
    AppPermission = apps.get_model('account', 'AppPermission')
    PermissionProfile = apps.get_model('account', 'PermissionProfile')

    for code, block, operation, category, label in NEW_PERMISSIONS:
        AppPermission.objects.update_or_create(
            code=code,
            defaults={
                'block': block, 'operation': operation,
                'category': category, 'label': label, 'is_active': True,
            },
        )

    for code, (block, operation, label) in RELABEL.items():
        AppPermission.objects.filter(code=code).update(
            block=block, operation=operation, label=label,
        )

    for role, codes in GRANTS.items():
        profile = PermissionProfile.objects.filter(role=role).first()
        if profile:
            profile.permissions.add(*AppPermission.objects.filter(code__in=codes))

    security, _ = PermissionProfile.objects.get_or_create(
        name=SECURITY_PROFILE,
        defaults={
            'is_system': False,
            'description': 'Просмотр посещаемости всех отделов и журнала обходов без прав на редактирование',
        },
    )
    security.permissions.add(*AppPermission.objects.filter(
        code__in=['dashboard', 'profile', 'hr_self', 'hr_journal', 'rounds_monitor'],
    ))


def backwards(apps, schema_editor):
    AppPermission = apps.get_model('account', 'AppPermission')
    PermissionProfile = apps.get_model('account', 'PermissionProfile')
    PermissionProfile.objects.filter(name=SECURITY_PROFILE, is_system=False).delete()
    AppPermission.objects.filter(code__in=[p[0] for p in NEW_PERMISSIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0029_profileassignment_position_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
