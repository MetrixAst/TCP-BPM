from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("esigner", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="esignersigning",
            name="esigner_document_id",
            field=models.CharField(
                max_length=64,
                unique=True,
                verbose_name="ID документа в eSigner",
            ),
        ),
    ]
