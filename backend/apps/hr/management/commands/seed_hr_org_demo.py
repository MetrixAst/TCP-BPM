"""
Демо-данные HR: компания, отделы, ~10 сотрудников, документы, допуски, сертификации.
Повторный запуск обновляет связи; не удаляет существующих пользователей вне префикса demo_.

  python manage.py seed_hr_org_demo
  python manage.py seed_hr_org_demo --force
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse

from account.models import UserAccount, Department, Employee
from account.role_permissions import RoleEnums
from hr.enums import (
    DocumentTypeEnum,
    DocumentStatusEnum,
    EmployeeStatusEnum,
)
from hr.models import (
    Company,
    Position,
    WorkCategory,
    EmployeeDocument,
    EmployeeWorkPermit,
    EmployeeCertification,
)

DEMO_BIN = '990940000123'
DEMO_PASSWORD = 'Trc2026!'


def _dept_specs():
    return [
        ('admin', 'Администрация', None),
        ('hr', 'HR и кадры', 'admin'),
        ('finance', 'Финансы', 'admin'),
        ('commercial', 'Коммерческий блок', 'admin'),
        ('ops', 'Эксплуатация и безопасность', 'admin'),
    ]


def _employee_specs():
    return [
        # slug, username, first, last, dept_slug, position_title, head, iin_suffix
        ('aset', 'demo_aset', 'Асет', 'Касымов', 'admin', 'Генеральный директор', True, '01'),
        ('daria', 'demo_daria', 'Дария', 'Нурланова', 'hr', 'Директор по персоналу', True, '02'),
        ('elena', 'demo_elena', 'Елена', 'Петрова', 'finance', 'Финансовый директор', True, '03'),
        ('maria', 'demo_maria', 'Мария', 'Иванова', 'finance', 'Главный бухгалтер', False, '04'),
        ('sergey', 'demo_sergey', 'Сергей', 'Омаров', 'ops', 'Начальник эксплуатации', True, '05'),
        ('aigul', 'demo_aigul', 'Айгуль', 'Садыкова', 'ops', 'Инженер эксплуатации', False, '06'),
        ('nurlan', 'demo_nurlan', 'Нурлан', 'Беков', 'commercial', 'Менеджер по аренде', True, '07'),
        ('alima', 'demo_alima', 'Алима', 'Токтарова', 'commercial', 'Маркетолог', False, '08'),
        ('bagdat', 'demo_bagdat', 'Багдат', 'Рахимов', 'hr', 'HR-специалист', False, '09'),
        ('daniyar', 'demo_daniyar', 'Данияр', 'Жумагулов', 'ops', 'Специалист по охране', False, '10'),
    ]


class Command(BaseCommand):
    help = 'Заполняет оргструктуру демо-сотрудниками и кадровыми записями'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Пересоздать кадровые записи demo_* (пользователи остаются)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options['force']
        company, _ = Company.objects.get_or_create(
            bin_number=DEMO_BIN,
            defaults={
                'name': 'ТОО «ТРЦ Метрикс»',
                'address': 'г. Алматы, пр. Достык 240',
                'phone': '+7 (727) 300-00-00',
                'email': 'info@metricx.kz',
            },
        )
        company.name = 'ТОО «ТРЦ Метрикс»'
        company.save()

        dept_by_slug = {}
        for slug, name, parent_slug in _dept_specs():
            parent = dept_by_slug.get(parent_slug) if parent_slug else None
            dept, _ = Department.objects.get_or_create(
                name=name,
                company=company,
                defaults={'parent': parent, 'level_type': 'department'},
            )
            dept.parent = parent
            dept.company = company
            dept.save()
            dept_by_slug[slug] = dept

        positions = {}
        for spec in _employee_specs():
            dept = dept_by_slug[spec[4]]
            pos, _ = Position.objects.get_or_create(
                title=spec[5],
                department=dept,
                defaults={'description': f'Должность: {spec[5]}'},
            )
            positions[spec[0]] = pos

        work_cat, _ = WorkCategory.objects.get_or_create(
            code='DEMO-ELEC',
            defaults={
                'name': 'Электробезопасность',
                'category_group': 'Эксплуатация',
                'risk_level': 'medium',
            },
        )
        WorkCategory.objects.get_or_create(
            code='DEMO-HEIGHT',
            defaults={
                'name': 'Работы на высоте',
                'category_group': 'Эксплуатация',
                'risk_level': 'high',
            },
        )
        cert_first_aid_name = 'Первая помощь'

        today = date.today()
        created_employees = []

        for spec in _employee_specs():
            slug, username, first, last, dept_slug, pos_title, is_head, iin_suf = spec
            dept = dept_by_slug[dept_slug]
            position = positions[slug]

            user, user_created = UserAccount.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@metricx.demo',
                    'role': RoleEnums.STAFF.value,
                    'first_name': first,
                    'last_name': last,
                },
            )
            if user_created or force:
                user.set_password(DEMO_PASSWORD)
            user.first_name = first
            user.last_name = last
            user.email = f'{username}@metricx.demo'
            user.is_active = True
            user.save()

            iin = f'95010130{iin_suf}12'
            employee, emp_created = Employee.objects.get_or_create(
                user=user,
                defaults={
                    'department': dept,
                    'position': position,
                    'iin': iin,
                    'status': EmployeeStatusEnum.ACTIVE,
                    'hire_date': today - timedelta(days=400 + int(iin_suf) * 30),
                    'phone': f'+770100000{iin_suf}',
                    'personal_email': f'{username}@metricx.demo',
                    'head': is_head,
                },
            )
            employee.department = dept
            employee.position = position
            employee.iin = iin
            employee.status = EmployeeStatusEnum.ACTIVE
            employee.head = is_head
            employee.hire_date = employee.hire_date or (today - timedelta(days=400))
            employee.save()

            if is_head:
                employee.set_head()

            created_employees.append(employee)

            if force or emp_created or not employee.documents.exists():
                EmployeeDocument.objects.update_or_create(
                    employee=employee,
                    doc_type=DocumentTypeEnum.EMPLOYMENT_CONTRACT,
                    version=1,
                    defaults={
                        'title': f'Трудовой договор — {first} {last}',
                        'status': DocumentStatusEnum.ACTIVE,
                        'signed_at': employee.hire_date,
                        'expires_at': None,
                        'notes': 'Демо-запись',
                    },
                )
                EmployeeDocument.objects.update_or_create(
                    employee=employee,
                    doc_type=DocumentTypeEnum.NDA,
                    version=1,
                    defaults={
                        'title': f'NDA — {first} {last}',
                        'status': DocumentStatusEnum.ACTIVE,
                        'signed_at': employee.hire_date,
                        'expires_at': today + timedelta(days=365 * 2),
                    },
                )

            if dept_slug in ('ops', 'commercial') and (
                force or not employee.work_permits.filter(category=work_cat).exists()
            ):
                EmployeeWorkPermit.objects.update_or_create(
                    employee=employee,
                    category=work_cat,
                    defaults={
                        'issue_date': today - timedelta(days=180),
                        'expiry_date': today + timedelta(days=185),
                        'document_number': f'WP-{iin_suf}',
                    },
                )

            if force or not employee.certifications.filter(cert_type=cert_first_aid_name).exists():
                EmployeeCertification.objects.update_or_create(
                    employee=employee,
                    cert_type=cert_first_aid_name,
                    defaults={
                        'certificate_number': f'CERT-FA-{iin_suf}',
                        'issue_date': today - timedelta(days=200),
                        'expiry_date': today + timedelta(days=500),
                        'issuing_body': 'РЦ ГО и ЧС',
                    },
                )

        # Привязать hr_manager к директору HR в оргструктуре
        hr_user = UserAccount.objects.filter(username='hr_manager').first()
        hr_dept = dept_by_slug.get('hr')
        hr_head_pos = positions.get('daria')
        if hr_user and hr_dept and hr_head_pos:
            emp, _ = Employee.objects.get_or_create(
                user=hr_user,
                defaults={
                    'department': hr_dept,
                    'position': hr_head_pos,
                    'iin': '950101309999',
                    'status': EmployeeStatusEnum.ACTIVE,
                    'hire_date': today - timedelta(days=800),
                    'head': True,
                },
            )
            emp.department = hr_dept
            emp.position = hr_head_pos
            emp.head = True
            emp.status = EmployeeStatusEnum.ACTIVE
            emp.save()
            emp.set_head()

        self.stdout.write(self.style.SUCCESS(
            f'Готово: компания «{company.name}», отделов {len(dept_by_slug)}, '
            f'сотрудников в оргструктуре {len(created_employees)}.'
        ))
        self.stdout.write('Откройте /hr/structure/ — сотрудники под отделами.')
        self.stdout.write(f'Демо-логины: demo_aset … demo_daniyar, пароль {DEMO_PASSWORD}')
        sample = created_employees[0]
        if sample:
            url = reverse('hr:edit_employee', args=[sample.pk])
            self.stdout.write(f'Пример карточки: {url}')
