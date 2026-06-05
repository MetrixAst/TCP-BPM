"""
Привязка HR-карточек к служебным аккаунтам (owner, cfo, accountant).

  python manage.py seed_role_hr_profiles
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from account.models import UserAccount, Department, Employee
from hr.enums import DocumentTypeEnum, DocumentStatusEnum, EmployeeStatusEnum
from hr.models import Position, EmployeeDocument


ROLE_PROFILES = (
    {
        'username': 'owner',
        'first_name': 'Асхат',
        'last_name': 'Токаев',
        'dept_name': 'Управление',
        'position_title': 'Совладелец',
        'iin': '880101300501',
        'head': True,
        'phone': '+77071110001',
    },
    {
        'username': 'cfo',
        'first_name': 'Нурлан',
        'last_name': 'Сейитов',
        'dept_name': 'Финансы',
        'position_title': 'Финансовый директор',
        'iin': '880101300502',
        'head': True,
        'phone': '+77071110002',
    },
    {
        'username': 'accountant',
        'first_name': 'Айгуль',
        'last_name': 'Смагулова',
        'dept_name': 'Финансы',
        'position_title': 'Главный бухгалтер',
        'iin': '880101300503',
        'head': False,
        'phone': '+77071110003',
        'supervisor_username': 'cfo',
    },
)


class Command(BaseCommand):
    help = 'Заполнить HR-карточки для owner, cfo, accountant'

    @transaction.atomic
    def handle(self, *args, **options):
        today = date.today()
        hire_base = today - timedelta(days=900)
        employees_by_username = {}

        for spec in ROLE_PROFILES:
            user = UserAccount.objects.filter(username=spec['username']).first()
            if not user:
                self.stdout.write(self.style.WARNING(f"Пропуск: нет пользователя {spec['username']}"))
                continue

            dept = Department.objects.filter(name=spec['dept_name']).first()
            if not dept:
                self.stdout.write(self.style.ERROR(f"Нет отдела «{spec['dept_name']}» — сначала seed_hr_org_demo"))
                continue

            position, _ = Position.objects.get_or_create(
                title=spec['position_title'],
                department=dept,
                defaults={'description': spec['position_title']},
            )

            user.first_name = spec['first_name']
            user.last_name = spec['last_name']
            if not user.email:
                user.email = f"{spec['username']}@metricx.demo"
            user.save(update_fields=['first_name', 'last_name', 'email'])

            employee, created = Employee.objects.get_or_create(
                user=user,
                defaults={
                    'department': dept,
                    'position': position,
                    'iin': spec['iin'],
                    'status': EmployeeStatusEnum.ACTIVE,
                    'hire_date': hire_base,
                    'phone': spec['phone'],
                    'personal_email': f"{spec['username']}@metricx.demo",
                    'head': spec['head'],
                },
            )
            employee.department = dept
            employee.position = position
            employee.iin = spec['iin']
            employee.status = EmployeeStatusEnum.ACTIVE
            employee.hire_date = employee.hire_date or hire_base
            employee.phone = spec['phone']
            employee.personal_email = f"{spec['username']}@metricx.demo"
            employee.head = spec['head']
            employee.save()

            if spec['head']:
                employee.set_head()

            sup_username = spec.get('supervisor_username')
            if sup_username and sup_username in employees_by_username:
                employee.supervisor = employees_by_username[sup_username]
                employee.save(update_fields=['supervisor'])

            employees_by_username[spec['username']] = employee

            EmployeeDocument.objects.update_or_create(
                employee=employee,
                doc_type=DocumentTypeEnum.EMPLOYMENT_CONTRACT,
                version=1,
                defaults={
                    'title': f"Трудовой договор — {spec['first_name']} {spec['last_name']}",
                    'status': DocumentStatusEnum.ACTIVE,
                    'signed_at': employee.hire_date,
                },
            )

            action = 'создана' if created else 'обновлена'
            self.stdout.write(self.style.SUCCESS(
                f"{spec['username']}: карточка {action} — {employee}"
            ))

        self.stdout.write(self.style.SUCCESS('Готово. Карточки: /hr/employees/'))
