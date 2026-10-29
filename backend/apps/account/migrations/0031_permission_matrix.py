from django.db import migrations

NEW_PERMISSIONS = [
    ("tasks_view_all",    "tasks",     "view",    "tasks",     "Задачи: просмотр всех задач"),
    ("tasks_edit_any",    "tasks",     "edit",    "tasks",     "Задачи: редактирование любых задач"),
    ("tasks_delete",      "tasks",     "delete",  "tasks",     "Задачи: удаление любых задач"),
    ("tasks_assign",      "tasks",     "assign",  "tasks",     "Задачи: назначение и перенаправление исполнителя"),
    ("documents_delete",  "documents", "delete",  "documents", "Документы: удаление любых документов"),
    ("documents_approve", "documents", "approve", "documents", "Документы: согласование любых документов"),
    ("documents_sign",    "documents", "sign",    "documents", "Документы: подписание"),
    ("tickets_approve",   "requests",  "approve", "general",   "Заявки: согласование любых заявок"),
]

RELABEL = {
    "edit_task":     ("tasks", "create", "Задачи: создание и редактирование своих"),
    "edit_document": ("documents", "create", "Документы: создание и редактирование своих"),
}

GRANTS = {
    "administrator": [code for code, *_rest in NEW_PERMISSIONS],
    "owner": ["tasks_view_all"],
}


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
        AppPermission.objects.filter(code=code).update(block=block, operation=operation, label=label)

    for role, codes in GRANTS.items():
        profile = PermissionProfile.objects.filter(role=role).first()
        if profile:
            profile.permissions.add(*AppPermission.objects.filter(code__in=codes))


def backwards(apps, schema_editor):
    AppPermission = apps.get_model('account', 'AppPermission')
    AppPermission.objects.filter(code__in=[p[0] for p in NEW_PERMISSIONS]).delete()
    AppPermission.objects.filter(code='edit_task').update(operation='edit', label='Задачи: редактирование')
    AppPermission.objects.filter(code='edit_document').update(operation='edit', label='Документы: редактирование')


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0030_metrix_permissions'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
