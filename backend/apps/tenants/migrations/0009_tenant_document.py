import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import project.utils


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tenants', '0008_tenant_counterparty'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=255, verbose_name='Название')),
                ('file', models.FileField(upload_to=project.utils.PathAndRename('tenant_documents/'), verbose_name='Файл')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documents',
                    to='tenants.tenant',
                    verbose_name='Арендатор',
                )),
                ('uploaded_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='tenant_documents',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Кто загрузил',
                )),
            ],
            options={
                'verbose_name': 'Документ арендатора',
                'verbose_name_plural': 'Документы арендаторов',
                'ordering': ['-created_at'],
            },
        ),
    ]
