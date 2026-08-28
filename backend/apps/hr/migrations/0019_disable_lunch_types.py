from django.db import migrations


def mark_lunch_records_as_legacy(apps, schema_editor):
    pass


def reverse_migration(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0018_employeeworkschedule'),
    ]

    operations = [
        migrations.RunPython(
            mark_lunch_records_as_legacy,
            reverse_migration,
        ),
    ]