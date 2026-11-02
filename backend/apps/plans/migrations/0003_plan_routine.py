from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('account', '0030_metrix_permissions'),
        ('plans', '0002_plans_permission'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanRoutine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255, verbose_name='Работа / задача')),
                ('description', models.TextField(blank=True, default='', verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Действует')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('department', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plan_routines', to='account.department', verbose_name='Отдел')),
                ('responsible', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='plan_routines', to=settings.AUTH_USER_MODEL, verbose_name='Ответственный')),
            ],
            options={
                'verbose_name': 'Ежедневная задача',
                'verbose_name_plural': 'Ежедневные задачи',
                'ordering': ['title', 'id'],
            },
        ),
        migrations.AddField(
            model_name='planitem',
            name='routine',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='items', to='plans.planroutine', verbose_name='Ежедневная задача'),
        ),
    ]
