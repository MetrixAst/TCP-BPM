# Generated for the mobile rounds / checklists feature

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('account', '0027_notificationuser'),
        ('ecopark', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChecklistTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Название')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_checklist_templates', to=settings.AUTH_USER_MODEL, verbose_name='Создал')),
            ],
            options={
                'verbose_name': 'Чек-лист',
                'verbose_name_plural': 'Чек-листы',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ChecklistItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Порядок')),
                ('text', models.CharField(max_length=500, verbose_name='Пункт')),
                ('requires_photo_on_fail', models.BooleanField(default=True, verbose_name='Требовать фото при несоответствии')),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='ecopark.checklisttemplate', verbose_name='Чек-лист')),
            ],
            options={
                'verbose_name': 'Пункт чек-листа',
                'verbose_name_plural': 'Пункты чек-листа',
                'ordering': ['template', 'order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='RoundPoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name='UUID')),
                ('name', models.CharField(max_length=255, verbose_name='Название')),
                ('location', models.CharField(blank=True, max_length=255, verbose_name='Местоположение')),
                ('check_interval_hours', models.PositiveIntegerField(default=24, verbose_name='Интервал проверки, ч')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('checklist', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='points', to='ecopark.checklisttemplate', verbose_name='Чек-лист')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_round_points', to=settings.AUTH_USER_MODEL, verbose_name='Создал')),
                ('eco_object', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='round_points', to='ecopark.ecoobject', verbose_name='Объект')),
            ],
            options={
                'verbose_name': 'Точка обхода',
                'verbose_name_plural': 'Точки обхода',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='RoundVisit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('comment', models.CharField(blank=True, max_length=1000, verbose_name='Комментарий')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='round_visits', to='account.employee', verbose_name='Сотрудник')),
                ('point', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='visits', to='ecopark.roundpoint', verbose_name='Точка')),
            ],
            options={
                'verbose_name': 'Обход точки',
                'verbose_name_plural': 'Обходы точек',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RoundVisitAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('passed', models.BooleanField(verbose_name='Соответствует')),
                ('comment', models.CharField(blank=True, max_length=500, verbose_name='Комментарий')),
                ('photo', models.ImageField(blank=True, null=True, upload_to='ecopark/rounds/%Y/%m/%d/', verbose_name='Фото')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='answers', to='ecopark.checklistitem', verbose_name='Пункт')),
                ('visit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='ecopark.roundvisit', verbose_name='Обход')),
            ],
            options={
                'verbose_name': 'Ответ по пункту',
                'verbose_name_plural': 'Ответы по пунктам',
                'ordering': ['item__order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Defect',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=1000, verbose_name='Описание')),
                ('photo', models.ImageField(blank=True, null=True, upload_to='ecopark/defects/%Y/%m/%d/', verbose_name='Фото')),
                ('status', models.CharField(choices=[('open', 'Открыта'), ('in_progress', 'В работе'), ('resolved', 'Устранена')], default='open', max_length=20, verbose_name='Статус')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='Устранена')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('answer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='defects', to='ecopark.roundvisitanswer', verbose_name='Ответ')),
                ('point', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='defects', to='ecopark.roundpoint', verbose_name='Точка')),
                ('reported_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reported_defects', to='account.employee', verbose_name='Обнаружил')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_defects', to=settings.AUTH_USER_MODEL, verbose_name='Устранил')),
                ('visit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='defects', to='ecopark.roundvisit', verbose_name='Обход')),
            ],
            options={
                'verbose_name': 'Неисправность',
                'verbose_name_plural': 'Неисправности',
                'ordering': ['-created_at'],
            },
        ),
    ]
