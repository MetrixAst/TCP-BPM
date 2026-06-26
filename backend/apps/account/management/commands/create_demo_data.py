from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from account.models import UserAccount, Department
from hr.models import Company, Position, LeaveType, LeaveRequest
from tasks.models import Task, TaskHistory
from purchases.models import Supplier, SupplierCategory
from tenants.models import Tenant, TenantCategory, Room
from ecopark.models import EcoObject, EcoExecutor, EcoWork
from tickets.models import ServiceRequest, ServiceRequestHistory


class Command(BaseCommand):
    help = 'Создать демо данные для всех разделов'

    def handle(self, *args, **kwargs):

        company, _ = Company.objects.get_or_create(
            name='Ritz Palace',
            defaults={'bin_number': '123456789077'}
        )
        self.stdout.write('Компания: %s' % company.name)

        dept_admin, _ = Department.objects.get_or_create(name='Администрация', company=company)
        dept_hr, _ = Department.objects.get_or_create(name='HR отдел', company=company)
        dept_finance, _ = Department.objects.get_or_create(name='Финансовый отдел', company=company)
        dept_ops, _ = Department.objects.get_or_create(name='Операционный отдел', company=company)
        self.stdout.write('Отделы созданы')

        pos_data = [
            ('Директор', dept_admin),
            ('HR-менеджер', dept_hr),
            ('Менеджер', dept_ops),
            ('Финансовый директор', dept_finance),
            ('Главный бухгалтер', dept_finance),
            ('Сотрудник', dept_ops),
        ]
        positions = {}
        for title, dept in pos_data:
            pos, _ = Position.objects.get_or_create(title=title, department=dept)
            positions[title] = pos
        self.stdout.write('Должности созданы')

        users_data = [
            ('admin1',       'admin2123',  'administrator',    'Асылбек',  'Жаксыбеков', dept_admin,   'Директор',            True),
            ('hr_manager',  'hr123',     'hr',               'Айгерим',  'Нурланова',  dept_hr,      'HR-менеджер',         True),
            ('staff_user',  'staff123',  'staff',            'Нурлан',   'Бекбосынов', dept_ops,     'Менеджер',            False),
            ('owner_user',  'owner123',  'owner',            'Болат',    'Сейткали',   dept_admin,   'Директор',            False),
            ('cfo_user',    'cfo123',    'cfo',              'Гульнара', 'Ахметова',   dept_finance, 'Финансовый директор', True),
            ('accountant',  'acc123',    'chief_accountant', 'Зарина',   'Кенжебаева', dept_finance, 'Главный бухгалтер',   False),
            ('guest_user',  'guest123',  'guest',            'Арман',    'Сейткалиев', dept_ops,     'Сотрудник',           False),
        ]

        created_users = {}
        employees = {}
        for username, password, role, first, last, dept, pos_title, head in users_data:
            user, created = UserAccount.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'role': role,
                    'is_active': True,
                }
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write('Создан: %s / %s (%s)' % (username, password, role))
            else:
                self.stdout.write('Уже существует: %s' % username)
            created_users[username] = user

            from account.models import Employee
            emp, _ = Employee.objects.get_or_create(
                user=user,
                defaults={
                    'department': dept,
                    'position': positions[pos_title],
                    'head': head,
                }
            )
            employees[username] = emp

        admin_user = created_users.get('admin') or UserAccount.objects.filter(role='administrator').first()
        staff_user = created_users.get('staff_user') or UserAccount.objects.filter(role='staff').first()
        hr_user = created_users.get('hr_manager') or UserAccount.objects.filter(role='hr').first()

        tasks_data = [
            ('Проверка систем безопасности', 'created', 'high', date.today() + timedelta(days=7)),
            ('Подготовка отчета за квартал', 'accepted', 'medium', date.today() + timedelta(days=14)),
            ('Обновление документации', 'completed', 'low', date.today() + timedelta(days=3)),
            ('Встреча с арендаторами', 'created', 'critical', date.today() + timedelta(days=2)),
            ('Техническое обслуживание лифтов', 'accepted', 'high', date.today() + timedelta(days=10)),
        ]
        for title, status, priority, deadline in tasks_data:
            task, created = Task.objects.get_or_create(
                title=title,
                defaults={
                    'author': admin_user,
                    'executor': staff_user,
                    'status': status,
                    'priority': priority,
                    'deadline': deadline,
                    'task_type': 'assignment',
                }
            )
            if created:
                TaskHistory.objects.create(task=task, user=admin_user, status=status)
        self.stdout.write('Задачи созданы')

        cat_supplier, _ = SupplierCategory.objects.get_or_create(title='Поставщик')
        cat_service, _ = SupplierCategory.objects.get_or_create(title='Сервисная компания')

        suppliers_data = [
            ('ТОО Казахтелеком', '6000800000', '+7 727 258 00 00', 'active'),
            ('ТОО АлматыСервис', '5001234567', '+7 727 300 00 01', 'active'),
            ('ИП Асылбеков К.', '8001234567', '+7 777 100 00 01', 'active'),
            ('ТОО СтройМастер', '4001234567', '+7 727 400 00 02', 'review'),
        ]
        created_suppliers = []
        for name, bin_num, phone, status in suppliers_data:
            supplier, _ = Supplier.objects.get_or_create(
                name=name,
                defaults={
                    'identifier': bin_num,
                    'phone': phone,
                    'status': status,
                    'address2': 'г. Алматы',
                    'author': admin_user,
                }
            )
            created_suppliers.append(supplier)
        self.stdout.write('Контрагенты созданы')

        cat_food, _ = TenantCategory.objects.get_or_create(title='Питание')
        cat_fashion, _ = TenantCategory.objects.get_or_create(title='Мода')
        cat_electronics, _ = TenantCategory.objects.get_or_create(title='Электроника')

        rooms_data = [
            ('101', 'room-101', 1),
            ('102', 'room-102', 1),
            ('201', 'room-201', 2),
            ('202', 'room-202', 2),
            ('301', 'room-301', 3),
        ]
        rooms = {}
        for number, map_id, floor in rooms_data:
            room, _ = Room.objects.get_or_create(
                number=number,
                defaults={'map_id': map_id, 'floor': floor}
            )
            rooms[number] = room

        today = date.today()
        tenants_data = [
            ('KFC', cat_food, '101', 250.0, 12000, '+7 727 100 11 11', 'kfc@example.kz', 'г. Алматы, ул. Абая 1', 'Асанов Серик'),
            ('H&M', cat_fashion, '102', 320.0, 15000, '+7 727 100 22 22', 'hm@example.kz', 'г. Алматы, ул. Абая 2', 'Берикова Айна'),
            ('Samsung', cat_electronics, '201', 180.0, 18000, '+7 727 100 33 33', 'samsung@example.kz', 'г. Алматы, ул. Абая 3', 'Джаксыбеков Нур'),
            ('Zara', cat_fashion, '202', 280.0, 14000, '+7 727 100 44 44', 'zara@example.kz', 'г. Алматы, ул. Абая 4', 'Ержанова Гуля'),
            ('Starbucks', cat_food, '301', 120.0, 20000, '+7 727 100 55 55', 'starbucks@example.kz', 'г. Алматы, ул. Абая 5', 'Касымов Дамир'),
        ]
        created_tenants = []
        for name, category, room_num, area, price, phone, email, address, contact in tenants_data:
            tenant, _ = Tenant.objects.get_or_create(
                name=name,
                defaults={
                    'category': category,
                    'room': rooms[room_num],
                    'area': area,
                    'price': price,
                    'phone': phone,
                    'email': email,
                    'address': address,
                    'contact': contact,
                    'start_date': today - timedelta(days=180),
                    'end_date': today + timedelta(days=365),
                    'discount_date': today + timedelta(days=90),
                    'increase_type': 'percent',
                    'discount': 0,
                }
            )
            created_tenants.append(tenant)
        self.stdout.write('Арендаторы созданы')

        eco_objects_data = [
            'Эскалатор', 'Лифт', 'Электрика', 'Сантехника',
            'Вентиляция/кондиционирование', 'Кровля', 'Фасад',
            'Парковка', 'Видеонаблюдение', 'Пожарная сигнализация',
            'Освещение', 'Общие зоны',
        ]
        eco_objs = {}
        for name in eco_objects_data:
            obj, _ = EcoObject.objects.get_or_create(name=name)
            eco_objs[name] = obj

        eco_executors_data = ['Штатный техник', 'Внешний подрядчик', 'ТОО АлматыСервис', 'ИП Асылбеков К.']
        eco_execs = {}
        for name in eco_executors_data:
            ex, _ = EcoExecutor.objects.get_or_create(name=name)
            eco_execs[name] = ex

        works_data = [
            ('Замена расходников эскалатора', 'Эскалатор', 'Штатный техник', 'Жаксыбеков А.', 125430, 'done'),
            ('Проверка насосной станции', 'Сантехника', 'ТОО АлматыСервис', 'Нурланова А.', 89200, 'progress'),
            ('Ремонт освещения 1 этажа', 'Освещение', 'Внешний подрядчик', 'Бекбосынов Н.', 214800, 'pending'),
            ('Устранение протечки (4 этаж)', 'Сантехника', 'ИП Асылбеков К.', 'Ахметова Г.', 67500, 'overdue'),
            ('ТО системы вентиляции', 'Вентиляция/кондиционирование', 'Штатный техник', 'Кенжебаева З.', 98000, 'done'),
        ]
        for title, obj_name, exec_name, responsible, amount, status in works_data:
            EcoWork.objects.get_or_create(
                title=title,
                defaults={
                    'eco_object': eco_objs.get(obj_name),
                    'executor': eco_execs.get(exec_name),
                    'responsible': responsible,
                    'amount': amount,
                    'status': status,
                }
            )
        self.stdout.write('Эксплуатация создана')

        leave_type_annual, _ = LeaveType.objects.get_or_create(
            name='Ежегодный оплачиваемый',
            defaults={'is_paid': True, 'max_days_per_year': 24}
        )
        leave_type_unpaid, _ = LeaveType.objects.get_or_create(
            name='Без сохранения зарплаты',
            defaults={'is_paid': False, 'max_days_per_year': 14}
        )

        leaves_data = [
            ('admin', leave_type_annual, today + timedelta(days=30), today + timedelta(days=44), 'approved'),
            ('staff_user', leave_type_annual, today - timedelta(days=10), today - timedelta(days=1), 'approved'),
            ('hr_manager', leave_type_unpaid, today + timedelta(days=60), today + timedelta(days=65), 'draft'),
        ]
        for username, leave_type, start, end, status in leaves_data:
            emp = employees.get(username)
            if emp:
                approver = employees.get('hr_manager')
                LeaveRequest.objects.get_or_create(
                    employee=emp,
                    leave_type=leave_type,
                    start_date=start,
                    defaults={
                        'end_date': end,
                        'status': status,
                        'approver': approver,
                    }
                )
        self.stdout.write('Отпуска созданы')

        tickets_data = [
            (created_tenants[0], admin_user, 'electrical', 'Не работает розетка в торговом зале', 'medium', 'new'),
            (created_tenants[1], admin_user, 'plumbing', 'Протечка в подсобном помещении', 'high', 'in_progress'),
            (created_tenants[2], admin_user, 'cleaning', 'Требуется уборка после ремонта', 'low', 'done'),
            (created_tenants[3], admin_user, 'other', 'Заменить лампочки в примерочных', 'medium', 'new'),
            (created_tenants[4], staff_user, 'hvac', 'Не работает кондиционер', 'high', 'accepted'),
        ]
        for tenant, author, category, title, priority, status in tickets_data:
            ticket, created = ServiceRequest.objects.get_or_create(
                title=title,
                defaults={
                    'tenant': tenant,
                    'author': author,
                    'category': category,
                    'description': title,
                    'priority': priority,
                    'status': status,
                    'room': tenant.number,
                    'department': dept_ops,
                    'assignee': staff_user,
                }
            )
            if created:
                ServiceRequestHistory.objects.create(
                    request=ticket,
                    user=author,
                    status=status,
                    comment='Создана демо заявка',
                )
        self.stdout.write('Заявки от арендаторов созданы')

        self.stdout.write(self.style.SUCCESS('Все демо данные созданы'))