from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0014_alter_employeedocument_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancerecord',
            name='location_address',
            field=models.CharField(
                blank=True,
                default='',
                max_length=512,
                verbose_name='Адрес отметки',
            ),
        ),
    ]
