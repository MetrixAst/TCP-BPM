import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('onec', '0007_counterparty_activity_type_counterparty_description_and_more'),
        ('tenants', '0007_alter_room_map_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='counterparty',
            field=models.ForeignKey(
                blank=True,
                help_text='По нему счета и оплаты из 1С попадают в реестр арендатора',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tenants',
                to='onec.counterparty',
                verbose_name='Контрагент в 1С',
            ),
        ),
    ]
