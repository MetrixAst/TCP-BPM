from decimal import Decimal

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('onec', '0006_counterparty_acl'),
        ('tasks', '0010_add_task_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='counterparty',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tasks',
                to='onec.counterparty',
                verbose_name='Контрагент',
            ),
        ),
        migrations.CreateModel(
            name='TaskChecklistItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255, verbose_name='Пункт')),
                ('is_done', models.BooleanField(default=False, verbose_name='Выполнено')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Порядок')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checklist_items', to='tasks.task', verbose_name='Задача')),
            ],
            options={
                'verbose_name': 'Пункт чеклиста',
                'verbose_name_plural': 'Чеклист задачи',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='TaskLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Наименование')),
                ('quantity', models.DecimalField(decimal_places=2, default=Decimal('1'), max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Количество')),
                ('unit', models.CharField(blank=True, default='шт', max_length=20, verbose_name='Ед. изм.')),
                ('price', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='Цена')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_items', to='tasks.task', verbose_name='Задача')),
            ],
            options={
                'verbose_name': 'Позиция задачи',
                'verbose_name_plural': 'Позиции задачи',
                'ordering': ['id'],
            },
        ),
    ]
