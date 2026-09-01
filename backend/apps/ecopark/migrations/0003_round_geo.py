# Геолокация точки и обхода — сверка, что сотрудник физически был рядом
# со статичным (печатным) QR, а не переслал ссылку удалённо.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ecopark', '0002_rounds'),
    ]

    operations = [
        migrations.AddField(
            model_name='roundpoint',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True, verbose_name='Широта'),
        ),
        migrations.AddField(
            model_name='roundpoint',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True, verbose_name='Долгота'),
        ),
        migrations.AddField(
            model_name='roundvisit',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True, verbose_name='Широта'),
        ),
        migrations.AddField(
            model_name='roundvisit',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True, verbose_name='Долгота'),
        ),
    ]
