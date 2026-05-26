from django.db import migrations


def seed_root_folders(apps, schema_editor):
    # MPTT: нужна реальная модель, иначе не заполняются lft/rgt/tree_id.
    from documents.models import Folder

    roots = (
        ('Документооборот', 'documents'),
        ('Закупки', 'purchases'),
        ('Бюджет', 'budget'),
    )
    for name, root_type in roots:
        if not Folder.objects.filter(root_type=root_type).exists():
            Folder.objects.create(name=name, root_type=root_type)


def unseed_root_folders(apps, schema_editor):
    Folder = apps.get_model('documents', 'Folder')
    Folder.objects.filter(
        root_type__in=['documents', 'purchases', 'budget'],
        parent__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_document_date_notify'),
    ]

    operations = [
        migrations.RunPython(seed_root_folders, unseed_root_folders),
    ]
