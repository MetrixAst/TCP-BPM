from django.db import migrations


OLD_TO_NEW_STATUS_MAP = {
    'to_do': 'created',
    'doing': 'accepted',
    'done': 'completed',
    'archive': 'completed',
}

NEW_TO_OLD_STATUS_MAP = {
    'created': 'to_do',
    'accepted': 'doing',
    'completed': 'done',   
    'rejected': 'done',    
    'revision': 'doing',  
}


def forward_migrate_statuses(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    TaskHistory = apps.get_model('tasks', 'TaskHistory')

    for old_status, new_status in OLD_TO_NEW_STATUS_MAP.items():
        Task.objects.filter(status=old_status).update(status=new_status)
        TaskHistory.objects.filter(status=old_status).update(status=new_status)


def backward_migrate_statuses(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    TaskHistory = apps.get_model('tasks', 'TaskHistory')

    for new_status, old_status in NEW_TO_OLD_STATUS_MAP.items():
        Task.objects.filter(status=new_status).update(status=old_status)
        TaskHistory.objects.filter(status=new_status).update(status=old_status)


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0005_remove_task_responsible'),
    ]

    operations = [
        migrations.RunPython(
            forward_migrate_statuses,
            backward_migrate_statuses
        ),
    ]