from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0009_exchangerate'),
    ]

    operations = [
        migrations.AddField(
            model_name='financialstatement',
            name='onec_id',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                unique=True,
                verbose_name='ID в 1С',
            ),
        ),
        migrations.AddField(
            model_name='financialstatement',
            name='onec_synced_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Синхронизация с 1С',
            ),
        ),
    ]
