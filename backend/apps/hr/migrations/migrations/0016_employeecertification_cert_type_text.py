from django.db import migrations, models


def copy_cert_type_names(apps, schema_editor):
    EmployeeCertification = apps.get_model('hr', 'EmployeeCertification')
    CertificationType = apps.get_model('hr', 'CertificationType')
    type_names = {ct.pk: ct.name for ct in CertificationType.objects.all()}
    for cert in EmployeeCertification.objects.all():
        name = type_names.get(cert.cert_type_id, '')
        cert.cert_type_text = name or 'Сертификация'
        cert.save(update_fields=['cert_type_text'])


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0015_attendancerecord_location_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeecertification',
            name='cert_type_text',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Тип сертификации'),
        ),
        migrations.RunPython(copy_cert_type_names, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='employeecertification',
            name='cert_type',
        ),
        migrations.RenameField(
            model_name='employeecertification',
            old_name='cert_type_text',
            new_name='cert_type',
        ),
    ]
