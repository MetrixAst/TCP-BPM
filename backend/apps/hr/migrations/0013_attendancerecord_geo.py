from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0012_certificationtype_employeecertification'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancerecord',
            name='latitude',
            field=models.DecimalField(
                blank=True, decimal_places=7, max_digits=10,
                null=True, verbose_name='Широта'
            ),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='longitude',
            field=models.DecimalField(
                blank=True, decimal_places=7, max_digits=10,
                null=True, verbose_name='Долгота'
            ),
        ),
    ]
