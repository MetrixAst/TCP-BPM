# Оборудование на точке + приоритет/эскалация/назначение неисправностей —
# фичи из параллельной ветки BE-inspection, перенесённые поверх
# RoundPoint/Defect (см. решение по объединению двух независимых бэкендов).

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ecopark', '0003_round_geo'),
    ]

    operations = [
        migrations.CreateModel(
            name='Equipment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Название')),
                ('description', models.CharField(blank=True, max_length=1000, verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активно')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('point', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='equipment', to='ecopark.roundpoint', verbose_name='Точка')),
            ],
            options={
                'verbose_name': 'Оборудование',
                'verbose_name_plural': 'Оборудование',
                'ordering': ['point', 'name'],
            },
        ),
        migrations.AddField(
            model_name='defect',
            name='priority',
            field=models.CharField(choices=[('low', 'Низкий'), ('medium', 'Средний'), ('high', 'Высокий'), ('critical', 'Критический')], default='medium', max_length=20, verbose_name='Приоритет'),
        ),
        migrations.AddField(
            model_name='defect',
            name='escalated_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Эскалирована'),
        ),
        migrations.AddField(
            model_name='defect',
            name='assigned_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_defects', to=settings.AUTH_USER_MODEL, verbose_name='Назначена'),
        ),
    ]
