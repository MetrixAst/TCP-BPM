from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
        ('account', '0018_counterparty_acl'),
    ]

    operations = [
        migrations.AddField(
            model_name='useraccount',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='portal_users',
                to='tenants.tenant',
                verbose_name='Арендатор',
            ),
        ),
        migrations.AlterField(
            model_name='useraccount',
            name='role',
            field=models.SlugField(
                choices=[
                    ('administrator', 'Администратор'),
                    ('hr', 'HR-менеджер'),
                    ('staff', 'Сотрудник'),
                    ('guest', 'Гость'),
                    ('tenant', 'Арендатор'),
                    ('owner', 'Владелец'),
                    ('cfo', 'Финансовый директор'),
                    ('chief_accountant', 'Главный бухгалтер'),
                ],
                verbose_name='Роль',
            ),
        ),
    ]
