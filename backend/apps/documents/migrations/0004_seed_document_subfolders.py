from django.db import migrations

from documents.folder_structure import _FOLDER_SPECS


def seed_subfolders(apps, schema_editor):
    # MPTT: только живая модель корректно заполняет lft/rgt/tree_id.
    from documents.models import Folder
    from documents.folder_structure import _get_root_folder

    for document_type, names in _FOLDER_SPECS.items():
        root = _get_root_folder(document_type)
        for name in names:
            folder, created = Folder.objects.get_or_create(
                name=name,
                defaults={'parent': root},
            )
            if not created and folder.parent_id != root.id:
                folder.parent = root
                folder.save()


def unseed_subfolders(apps, schema_editor):
    Folder = apps.get_model('documents', 'Folder')
    all_names = [n for names in _FOLDER_SPECS.values() for n in names]
    Folder.objects.filter(name__in=all_names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0003_seed_root_folders'),
    ]

    operations = [
        migrations.RunPython(seed_subfolders, unseed_subfolders),
    ]
