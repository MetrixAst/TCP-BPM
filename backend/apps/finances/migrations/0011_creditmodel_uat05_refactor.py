from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def backfill_credit_models(apps, schema_editor):
    CreditModel = apps.get_model('finances', 'CreditModel')
    seen = set()
    for credit in CreditModel.objects.order_by('pk').iterator():
        credit.year = (
            credit.period_start.year
            if credit.period_start
            else credit.created_at.year
        )
        credit.loan_term_months = 12
        principal = credit.loan_amount or Decimal('0')
        annual_rate = (credit.loan_rate or Decimal('0')) / Decimal('100')
        if not principal:
            credit.annual_debt_service = Decimal('0')
        elif not annual_rate:
            credit.annual_debt_service = principal
        else:
            monthly_rate = annual_rate / Decimal('12')
            factor = monthly_rate / (
                1 - (1 + monthly_rate) ** Decimal('-12')
            )
            credit.annual_debt_service = (
                principal * factor * Decimal('12')
            ).quantize(Decimal('0.01'))
        if credit.scenario == 'stress':
            credit.scenario = 'pessimistic'

        key = (credit.name, credit.scenario, credit.year)
        if key in seen:
            suffix = f' ({credit.pk})'
            credit.name = f'{credit.name[:200 - len(suffix)]}{suffix}'
            key = (credit.name, credit.scenario, credit.year)
        seen.add(key)
        credit.save(update_fields=[
            'year',
            'loan_term_months',
            'annual_debt_service',
            'scenario',
            'name',
        ])


class Migration(migrations.Migration):
    dependencies = [
        ('finances', '0010_financialstatement_onec_fields'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='creditmodel',
            options={'ordering': ['-year', 'scenario']},
        ),
        migrations.AddField(
            model_name='creditmodel',
            name='annual_debt_service',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=16,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='creditmodel',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creditmodel',
            name='financial_statement',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='credit_models',
                to='finances.financialstatement',
            ),
        ),
        migrations.AddField(
            model_name='creditmodel',
            name='forecast_cashflow',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='creditmodel',
            name='forecast_pnl',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='creditmodel',
            name='loan_term_months',
            field=models.PositiveIntegerField(default=12),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='creditmodel',
            name='risk_notes',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creditmodel',
            name='year',
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(backfill_credit_models, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='creditmodel',
            name='dscr',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='free_cashflow',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='loan_amount',
            field=models.DecimalField(decimal_places=2, max_digits=16),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='loan_rate',
            field=models.DecimalField(decimal_places=2, max_digits=6),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='name',
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='period_end',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='period_start',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='projected_cashflow',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='projected_expenses',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='projected_income',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='risk_level',
            field=models.CharField(
                choices=[
                    ('low', 'Низкий'),
                    ('medium', 'Средний'),
                    ('high', 'Высокий'),
                ],
                default='medium',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='scenario',
            field=models.CharField(
                choices=[
                    ('base', 'Базовый'),
                    ('optimistic', 'Оптимистичный'),
                    ('pessimistic', 'Пессимистичный'),
                ],
                default='base',
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name='creditmodel',
            name='year',
            field=models.PositiveIntegerField(),
        ),
        migrations.AddConstraint(
            model_name='creditmodel',
            constraint=models.UniqueConstraint(
                fields=('name', 'scenario', 'year'),
                name='finances_creditmodel_name_scenario_year_9f7c29f8_uniq',
            ),
        ),
    ]
