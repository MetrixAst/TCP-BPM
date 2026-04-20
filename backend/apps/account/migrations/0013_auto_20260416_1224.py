from django.db import migrations

def migrate_job_titles_to_positions(apps, schema_editor):
    Employee = apps.get_model('account', 'Employee')
    Position = apps.get_model('hr', 'Position')
    
    queryset = Employee.objects.exclude(job_title__isnull=True).exclude(job_title="")
    
    for emp in queryset:
        position_obj, created = Position.objects.get_or_create(
            title=emp.job_title,
            department=emp.department
        )
        
        emp.position = position_obj
        emp.save()

def reverse_migration(apps, schema_editor):
    Employee = apps.get_model('account', 'Employee')
    for emp in Employee.objects.filter(position__isnull=False):
        emp.job_title = emp.position.title
        emp.save()

class Migration(migrations.Migration):

    dependencies = [
        ('account', '0012_alter_employee_options'), 
        ('hr', '0003_position'), 
    ]

    operations = [
        migrations.RunPython(migrate_job_titles_to_positions, reverse_migration),
    ]