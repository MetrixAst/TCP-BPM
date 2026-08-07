from django.db import migrations


def seed_permissions(apps, schema_editor):
    AppPermission = apps.get_model('account', 'AppPermission')
    PermissionProfile = apps.get_model('account', 'PermissionProfile')

    PERMISSIONS = [
        ("dashboard",          "dashboard", "",       "general",   "Дашборд"),
        ("profile",            "profile",   "",       "general",   "Профиль"),
        ("ecopark",            "ecopark",   "",       "general",   "Эксплуатация"),
        ("comment",            "comment",   "",       "general",   "Комментарии"),
        ("reports",            "reports",   "",       "general",   "Показатели"),
        ("hr",                 "hr",        "view",   "hr",        "HR: просмотр сотрудников"),
        ("hr_self",            "hr",        "view",   "hr",        "HR: личный профиль"),
        ("hr_registries",      "hr",        "view",   "hr",        "HR: реестры"),
        ("hr_companies",       "hr",        "create", "hr",        "HR: управление компаниями"),
        ("hr_positions",       "hr",        "edit",   "hr",        "HR: управление должностями"),
        ("hr_journal",         "hr",        "delete", "hr",        "HR: журнал посещаемости"),
        ("finances",           "finances",  "view",   "finances",  "Финансы: просмотр"),
        ("finance_dashboard",  "finances",  "view",   "finances",  "Финансы: дашборд"),
        ("finance_invoices",   "finances",  "view",   "finances",  "Финансы: счета"),
        ("finance_registers",  "finances",  "view",   "finances",  "Финансы: реестры оплат"),
        ("finance_reports",    "finances",  "view",   "finances",  "Финансы: отчёты"),
        ("finance_budget",     "finances",  "create", "finances",  "Финансы: бюджетирование"),
        ("finance_scenarios",  "finances",  "edit",   "finances",  "Финансы: сценарии"),
        ("tasks",              "tasks",     "view",   "tasks",     "Задачи: просмотр"),
        ("edit_task",          "tasks",     "edit",   "tasks",     "Задачи: редактирование"),
        ("documents",          "documents", "view",   "documents", "Документы: просмотр"),
        ("edit_document",      "documents", "edit",   "documents", "Документы: редактирование"),
        ("suppliers",          "suppliers", "view",   "suppliers", "Поставщики: просмотр"),
        ("edit_suppliers",     "suppliers", "edit",   "suppliers", "Поставщики: редактирование"),
        ("purchases",          "purchases", "view",   "purchases", "Закупки: просмотр"),
        ("tenants",            "tenants",   "view",   "tenants",   "Арендаторы: просмотр"),
        ("users_list",         "users",     "view",   "access",    "Пользователи: просмотр"),
        ("manage_permissions", "users",     "edit",   "access",    "Пользователи: управление правами"),
        ("service_requests",   "requests",  "view",   "general",   "Заявки на обслуживание"),
        ("requistions",        "requests",  "view",   "general",   "Заявки на пропуск"),
    ]

    PROFILES = {
        "administrator": {
            "name": "Администратор",
            "is_system": True,
            "description": "Полный доступ ко всем разделам системы",
            "permissions": [
                "dashboard", "profile", "ecopark", "comment", "reports",
                "hr", "hr_self", "hr_registries", "hr_companies", "hr_positions", "hr_journal",
                "finances", "finance_dashboard", "finance_invoices", "finance_registers",
                "finance_reports", "finance_budget", "finance_scenarios",
                "tasks", "edit_task", "documents", "edit_document",
                "suppliers", "edit_suppliers", "purchases", "tenants",
                "users_list", "manage_permissions", "service_requests", "requistions",
            ],
        },
        "owner": {
            "name": "Владелец",
            "is_system": True,
            "description": "Доступ к финансам и задачам",
            "permissions": [
                "dashboard", "profile", "comment", "reports",
                "finances", "finance_dashboard", "finance_invoices", "finance_registers",
                "finance_reports", "finance_budget", "finance_scenarios",
                "tasks", "edit_task",
            ],
        },
        "cfo": {
            "name": "Финансовый директор",
            "is_system": True,
            "description": "Полный доступ к финансам",
            "permissions": [
                "dashboard", "profile", "comment",
                "finances", "finance_dashboard", "finance_invoices", "finance_registers",
                "finance_reports", "finance_budget", "finance_scenarios",
                "tasks", "edit_task",
            ],
        },
        "chief_accountant": {
            "name": "Главный бухгалтер",
            "is_system": True,
            "description": "Финансы + кадровые реестры",
            "permissions": [
                "dashboard", "profile", "comment",
                "hr_self", "hr_registries",
                "finances", "finance_dashboard", "finance_invoices", "finance_registers",
                "finance_reports", "finance_budget",
                "tasks", "edit_task",
            ],
        },
        "hr": {
            "name": "HR-менеджер",
            "is_system": True,
            "description": "Полный доступ к HR-модулю",
            "permissions": [
                "dashboard", "profile", "comment",
                "hr", "hr_self", "hr_registries", "hr_companies", "hr_positions", "hr_journal",
                "tasks", "edit_task", "users_list",
            ],
        },
        "staff": {
            "name": "Сотрудник",
            "is_system": True,
            "description": "Базовый доступ",
            "permissions": [
                "dashboard", "profile", "comment",
                "hr_self", "tasks", "edit_task",
                "documents", "tenants", "users_list", "service_requests",
            ],
        },
        "guest": {
            "name": "Гость",
            "is_system": True,
            "description": "Только заявки",
            "permissions": ["dashboard", "profile", "service_requests", "requistions"],
        },
        "tenant": {
            "name": "Арендатор",
            "is_system": True,
            "description": "Только заявки",
            "permissions": ["dashboard", "profile", "service_requests", "requistions"],
        },
    }

    for code, block, operation, category, label in PERMISSIONS:
        AppPermission.objects.update_or_create(
            code=code,
            defaults={
                "block": block,
                "operation": operation,
                "category": category,
                "label": label,
                "is_active": True,
            },
        )

    for role, data in PROFILES.items():
        profile, _ = PermissionProfile.objects.update_or_create(
            role=role,
            defaults={
                "name": data["name"],
                "is_system": data["is_system"],
                "description": data["description"],
            },
        )
        perms = AppPermission.objects.filter(code__in=data["permissions"])
        profile.permissions.set(perms)


def unseed_permissions(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0022_apppermission_block_apppermission_operation'),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]