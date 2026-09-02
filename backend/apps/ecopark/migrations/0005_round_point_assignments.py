from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0028_temporaryaccess'),
        ('ecopark', '0004_equipment_defect_priority'),
    ]

    operations = [
        migrations.AddField(
            model_name='roundpoint',
            name='responsible_department',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='responsible_round_points',
                to='account.department',
                verbose_name='Ответственный отдел',
            ),
        ),
        migrations.AddField(
            model_name='roundpoint',
            name='responsible_employee',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='responsible_round_points',
                to='account.employee',
                verbose_name='Ответственный сотрудник',
            ),
        ),
        migrations.AddField(
            model_name='roundpoint',
            name='substitute_employee',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='substitute_round_points',
                to='account.employee',
                verbose_name='Замещающий сотрудник',
            ),
        ),
    ]
