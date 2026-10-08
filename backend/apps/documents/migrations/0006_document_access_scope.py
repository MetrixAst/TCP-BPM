from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0018_counterparty_acl'),
        ('documents', '0004_seed_document_subfolders'),
        ('documents', '0005_folder_acl'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='access_scope',
            field=models.ForeignKey(
                blank=True,
                help_text='Для документооборота: пусто = видят все, у кого есть доступ к папке.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='documents',
                to='account.accessscope',
                verbose_name='Зона доступа',
            ),
        ),
    ]
