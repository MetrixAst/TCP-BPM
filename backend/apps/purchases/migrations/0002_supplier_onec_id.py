from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchases', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplier',
            name='onec_id',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=50,
                null=True,
                unique=True,
                verbose_name='ID 1С',
            ),
        ),
    ]
