from enum import Enum
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse



class RoleEnums(Enum):
    ADMINISTRATOR = "administrator"
    HR = "hr"
    STAFF = "staff"
    GUEST = "guest"
    TENANT = "tenant"
    OWNER = "owner"
    CFO = "cfo"
    CHIEF_ACCOUNTANT = "chief_accountant"

    @staticmethod
    def tenant_roles():
        return [
            RoleEnums.ADMINISTRATOR.value,
            RoleEnums.HR.value,
            RoleEnums.STAFF.value,
        ]

    @staticmethod
    def portal_roles():
        return [
            RoleEnums.GUEST.value,
            RoleEnums.TENANT.value,
        ]


class PermissionEnums(Enum):
    PROFILE = "profile"
    DASHBOARD = "dashboard"
    TASKS = "tasks"
    EDIT_TASK = "edit_task"
    DOCUMENTS = "documents"
    EDIT_DOCUMENT = "edit_document"
    TENANTS = "tenants"
    PURCHASES = "purchases"
    SUPPLIERS = "suppliers"
    EDIT_SUPPLIERS = "edit_suppliers"
    FINANCES = "finances"
    HR = "hr"
    HR_COMPANIES = "hr_companies"
    HR_POSITIONS = "hr_positions"
    HR_JOURNAL = "hr_journal"
    HR_REGISTRIES = "hr_registries"
    HR_SELF = "hr_self"
    ECOPARK = "ecopark"
    REQUISTIONS = "requistions"
    SERVICE_REQUESTS = "service_requests"
    REPORTS = "reports"
    COMMENT = "comment"
    USERS_LIST = "users_list"
    MANAGE_PERMISSIONS = "manage_permissions"
    FINANCE_DASHBOARD = "finance_dashboard"
    FINANCE_BUDGET = "finance_budget"
    FINANCE_SCENARIOS = "finance_scenarios"
    FINANCE_REPORTS = "finance_reports"
    FINANCE_INVOICES = "finance_invoices"
    FINANCE_REGISTERS = "finance_registers"


class RolePermissions:
    permissions = {
        RoleEnums.ADMINISTRATOR.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.USERS_LIST,
            PermissionEnums.MANAGE_PERMISSIONS,
            PermissionEnums.DASHBOARD,
            PermissionEnums.TASKS,
            PermissionEnums.EDIT_TASK,
            PermissionEnums.DOCUMENTS,
            PermissionEnums.EDIT_DOCUMENT,
            PermissionEnums.TENANTS,
            PermissionEnums.PURCHASES,
            PermissionEnums.SUPPLIERS,
            PermissionEnums.EDIT_SUPPLIERS,
            PermissionEnums.FINANCES,
            PermissionEnums.HR,
            PermissionEnums.HR_SELF,
            PermissionEnums.HR_COMPANIES,
            PermissionEnums.HR_POSITIONS,
            PermissionEnums.HR_REGISTRIES,
            PermissionEnums.ECOPARK,
            PermissionEnums.REQUISTIONS,
            PermissionEnums.SERVICE_REQUESTS,
            PermissionEnums.REPORTS,
            PermissionEnums.COMMENT,
            PermissionEnums.HR_JOURNAL,
            PermissionEnums.FINANCE_DASHBOARD,
            PermissionEnums.FINANCE_INVOICES,
            PermissionEnums.FINANCE_REGISTERS,
            PermissionEnums.FINANCE_BUDGET,
            PermissionEnums.FINANCE_REPORTS,
            PermissionEnums.FINANCE_SCENARIOS,
        ],
        RoleEnums.OWNER.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.DASHBOARD,
            PermissionEnums.FINANCE_DASHBOARD,
            PermissionEnums.FINANCE_BUDGET,
            PermissionEnums.FINANCE_SCENARIOS,
            PermissionEnums.FINANCE_REPORTS,
            PermissionEnums.FINANCE_INVOICES,
            PermissionEnums.FINANCE_REGISTERS,
            PermissionEnums.REPORTS,
            PermissionEnums.TASKS,
            PermissionEnums.EDIT_TASK,
            PermissionEnums.COMMENT,
        ],
        RoleEnums.CFO.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.DASHBOARD,
            PermissionEnums.FINANCE_DASHBOARD,
            PermissionEnums.FINANCE_BUDGET,
            PermissionEnums.FINANCE_SCENARIOS,
            PermissionEnums.FINANCE_REPORTS,
            PermissionEnums.FINANCE_INVOICES,
            PermissionEnums.FINANCE_REGISTERS,
            PermissionEnums.TASKS,
            PermissionEnums.EDIT_TASK,
            PermissionEnums.COMMENT,
        ],
        RoleEnums.CHIEF_ACCOUNTANT.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.DASHBOARD,
            PermissionEnums.HR_SELF,
            PermissionEnums.HR_REGISTRIES,
            PermissionEnums.FINANCE_DASHBOARD,
            PermissionEnums.FINANCE_REPORTS,
            PermissionEnums.FINANCE_INVOICES,
            PermissionEnums.FINANCE_REGISTERS,
            PermissionEnums.FINANCE_BUDGET,
            PermissionEnums.TASKS,
            PermissionEnums.EDIT_TASK,
            PermissionEnums.COMMENT,
        ],
        RoleEnums.HR.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.DASHBOARD,
            PermissionEnums.HR,
            PermissionEnums.HR_SELF,
            PermissionEnums.HR_COMPANIES,
            PermissionEnums.HR_POSITIONS,
            PermissionEnums.HR_REGISTRIES,
            PermissionEnums.HR_JOURNAL,
            PermissionEnums.USERS_LIST,
            PermissionEnums.COMMENT,
            PermissionEnums.TASKS,
            PermissionEnums.EDIT_TASK,
        ],
        RoleEnums.STAFF.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.DASHBOARD,
            PermissionEnums.TASKS,
            PermissionEnums.EDIT_TASK,
            PermissionEnums.USERS_LIST,
            PermissionEnums.DOCUMENTS,
            PermissionEnums.TENANTS,
            PermissionEnums.SERVICE_REQUESTS,
            PermissionEnums.HR_SELF,
            PermissionEnums.COMMENT,
        ],
        RoleEnums.GUEST.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.DASHBOARD,
            PermissionEnums.REQUISTIONS,
            PermissionEnums.SERVICE_REQUESTS,
        ],
        RoleEnums.TENANT.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.DASHBOARD,
            PermissionEnums.REQUISTIONS,
            PermissionEnums.SERVICE_REQUESTS,
        ],
    }

    @staticmethod
    def _permission_key(permission):
        if hasattr(permission, 'value'):
            return permission.value
        return str(permission)

    @classmethod
    def checkPermission(cls, role, permission):
        if hasattr(role, 'value'):
            role = role.value
        try:
            from account.services.permissions import role_has_permission
            return role_has_permission(role, permission)
        except Exception:
            key = cls._permission_key(permission)
            for item in cls.permissions.get(role, []):
                if cls._permission_key(item) == key:
                    return True
            return False


def login_required(function):
    def wrap(request, *args, **kwargs):
        if request.user.is_authenticated:
            return function(request, *args, **kwargs)
        else:
            response = redirect('account:auth')
            response['Location'] += f"?next={request.path}"
            return response
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap


def _permission_display_label(permission):
    code = permission.value if hasattr(permission, 'value') else str(permission)
    try:
        from account.models_rbac import AppPermission
        label = (
            AppPermission.objects
            .filter(code=code)
            .values_list('label', flat=True)
            .first()
        )
    except Exception:
        label = None
    return label or code


def need_permission(permission):
    def _method_wrapper(view_method):
        def _arguments_wrapper(request, *args, **kwargs):
            if request.user.is_authenticated:
                from account.services.permissions import user_has_permission
                if user_has_permission(request.user, permission):
                    return view_method(request, *args, **kwargs)
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(_permission_display_label(permission))
            else:
                response = redirect('account:auth')
                response['Location'] += f"?next={request.path}"
                return response
        return _arguments_wrapper
    return _method_wrapper


class MenuItem:
    def __init__(
        self,
        id,
        url,
        icon,
        title,
        submenu=None,
        url_param=None,
        indicator_alias=None,
        always_expanded=False,
        permission=None,
    ):
        self.id = id
        self.title = title
        self.icon = icon
        self.submenu = submenu
        self.always_expanded = always_expanded
        self.indicator_alias = indicator_alias or self.id
        self.permission = permission
        self.url = url
        if url != '#' and not url.startswith("#"):
            if url_param is not None:
                self.url = reverse(url, args=url_param)
            else:
                self.url = reverse(url)

    @staticmethod
    def _filter_menu(items, user):
        from account.services.permissions import user_has_permission
        result = []
        for item in items:
            if item.permission and not user_has_permission(user, item.permission):
                continue
            if item.submenu:
                item.submenu = MenuItem._filter_menu(item.submenu, user)
            result.append(item)
        return result

    @staticmethod 
    def first_page(user):
        items = {
            RoleEnums.ADMINISTRATOR.value: 'dashboard:dashboard',
            RoleEnums.HR.value: 'hr:employees',
            RoleEnums.STAFF.value: 'dashboard:dashboard',
            RoleEnums.OWNER.value: 'dashboard:dashboard',
            RoleEnums.CFO.value: 'dashboard:dashboard',
            RoleEnums.CHIEF_ACCOUNTANT.value: 'dashboard:dashboard',
            RoleEnums.GUEST.value: 'requistions:home',
            RoleEnums.TENANT.value: 'requistions:home',
        }
        return items.get(user.role, None)

    @staticmethod 
    def first_page_as_string(user):
        route = MenuItem.first_page(user)
        if route is not None:
            return reverse(route)
        return None

    @staticmethod
    def generate_menu(user):
        from account.services.permissions import user_has_permission

        finance_common_submenu = [
            MenuItem('fin_dash', 'finances:dashboard', '', 'Финансовый дашборд'),
            MenuItem('fin_reg', 'finances:reg', '', 'Реестр оплат'),
            MenuItem('fin_calendar', 'finances:payment_calendar', '', 'Календарь платежей'),
            MenuItem('fin_invoices', 'finances:invoice_list', '', 'Счета'),
            MenuItem('fin_opiu', 'finances:opiu', '', 'ОПиУ'),
            MenuItem('fin_cashflow', 'finances:cashflow', '', 'ДДС'),
        ]

        finance_full_submenu = finance_common_submenu + [
            MenuItem('fin_budget', 'finances:budget_list', '', 'Бюджетирование'),
            MenuItem('fin_credit', 'finances:credit_model_list', '', 'Кредитная модель'),
            MenuItem('fin_rent_analytics', 'finances:rent_analytics', '', 'Аналитика аренды'),
        ]

        finance_readonly_submenu = [
            MenuItem('fin_dash', 'finances:dashboard', '', 'Финансовый дашборд'),
            MenuItem('fin_opiu', 'finances:opiu', '', 'ОПиУ'),
            MenuItem('fin_cashflow', 'finances:cashflow', '', 'ДДС'),
            MenuItem('fin_invoices', 'finances:invoice_list', '', 'Счета'),
            MenuItem('fin_reg', 'finances:reg', '', 'Реестр оплат'),
            MenuItem('fin_calendar', 'finances:payment_calendar', '', 'Календарь платежей'),
            MenuItem('fin_budget', 'finances:budget_list', '', 'Бюджетирование'),
            MenuItem('fin_rent_analytics', 'finances:rent_analytics', '', 'Аналитика аренды'),
        ]

        items = {
            RoleEnums.ADMINISTRATOR.value: [
                MenuItem('my_profile', 'hr:my_profile', 'person-circle', 'Личный профиль'),
                MenuItem('tasks', 'tasks:list', 'check2-square', 'Менеджер задач', indicator_alias='task', permission=PermissionEnums.TASKS),
                MenuItem('tasks_trash', 'tasks:trash', 'trash', 'Корзина задач', permission=PermissionEnums.MANAGE_PERMISSIONS),
                MenuItem('access', '#access', 'shield-lock', 'Доступы', permission=PermissionEnums.MANAGE_PERMISSIONS, submenu=[
                    MenuItem('access_users', 'account:access_users', '', 'Пользователи'),
                    MenuItem('access_profiles', 'account:access_profiles', '', 'Профили доступа'),
                ]),
                MenuItem('documents', 'documents:list', 'file-earmark-text', 'Документооборот', url_param=['documents'], permission=PermissionEnums.DOCUMENTS),
                MenuItem('tenants', '#tenants', 'building', 'Компании', submenu=[
                    MenuItem('suppliers', 'purchases:suppliers', '', 'Контрагенты', permission=PermissionEnums.SUPPLIERS),
                    MenuItem('tenants_list', 'tenants:list', '', 'Арендаторы', permission=PermissionEnums.TENANTS),
                ]),
                MenuItem('purchases', 'documents:list', 'folder2', 'Закупки', url_param=['purchases'], permission=PermissionEnums.PURCHASES),
                MenuItem('finances', '#finances', 'credit-card', 'Финансы', permission=PermissionEnums.FINANCES, submenu=finance_full_submenu + [
                    MenuItem('bill', 'finances:bill', '', 'Счет компании'),
                ]),
                MenuItem('hr', '#hr', 'people', 'HR', permission=PermissionEnums.HR, submenu=[
                    MenuItem('my_profile', 'hr:my_profile', '', 'Личный профиль'),
                    MenuItem('org', 'hr:org', '', 'Орг. структура'),
                    MenuItem('employees', 'hr:employees', '', 'Сотрудники'),
                    MenuItem('companies_hr', 'hr:companies', '', 'Компании'),
                    MenuItem('departments_hr', 'hr:departments', '', 'Отделы'),
                    MenuItem('positions_hr', 'hr:positions', '', 'Должности'),
                    MenuItem('leaves', 'hr:leave_list', '', 'Заявки на отпуск'),
                    MenuItem('leave_timeline_page', 'hr:leave_timeline_page', '', 'Календарь отпусков'),
                    MenuItem('secondment', 'hr:calendar', '', 'Командировки', url_param=['secondment']),
                    MenuItem('hr_documents', 'hr:documents_list', '', 'Кадровые документы'),
                    MenuItem('hr_permits', 'hr:permits_list', '', 'Допуски'),
                    MenuItem('hr_certifications', 'hr:certifications_list', '', 'Сертификации'),
                    MenuItem('attendance_journal', 'hr:attendance_journal', '', 'Журнал посещаемости'),
                    MenuItem('attendance_my', 'hr:attendance_my', '', 'Моя посещаемость'),
                ]),

                #MenuItem('onec', '#onec', 'box-arrow-in-down', '1C', submenu=[
                #   MenuItem('onec_counterparties', 'onec:counterparty_list', '', 'Контрагенты'),
                # ]),
                MenuItem('ecopark', 'ecopark:home', 'water', 'Эксплуатация', permission=PermissionEnums.ECOPARK),
                MenuItem('tickets', 'tickets:kanban', 'notebook-1', 'Заявки от арендаторов', indicator_alias='ticket', permission=PermissionEnums.SERVICE_REQUESTS),
                MenuItem('ticket_approvals', 'tickets:approvals', 'inbox-check', 'Согласования', permission=PermissionEnums.SERVICE_REQUESTS),
                MenuItem('ticket_workflow', 'tickets:workflow_settings', 'gear', 'Workflow заявок', permission=PermissionEnums.MANAGE_PERMISSIONS),
                MenuItem('reports', 'reports:home', 'eye', 'Показатели', permission=PermissionEnums.REPORTS),
            ],

            RoleEnums.OWNER.value: [
                MenuItem('my_profile', 'hr:my_profile', 'person-circle', 'Личный профиль'),
                MenuItem('tasks', 'tasks:list', 'check2-square', 'Менеджер задач', indicator_alias='task', permission=PermissionEnums.TASKS),
                MenuItem('finances', '#finances', 'credit-card', 'Финансы', permission=PermissionEnums.FINANCES, submenu=finance_full_submenu),
                MenuItem('reports', 'reports:home', 'eye', 'Показатели', permission=PermissionEnums.REPORTS),
            ],

            RoleEnums.CFO.value: [
                MenuItem('my_profile', 'hr:my_profile', 'person-circle', 'Личный профиль'),
                MenuItem('tasks', 'tasks:list', 'check2-square', 'Менеджер задач', indicator_alias='task', permission=PermissionEnums.TASKS),
                MenuItem('finances', '#finances', 'credit-card', 'Финансы', permission=PermissionEnums.FINANCES, submenu=finance_full_submenu),
                MenuItem('reports', 'reports:home', 'eye', 'Показатели', permission=PermissionEnums.REPORTS),
            ],

            RoleEnums.CHIEF_ACCOUNTANT.value: [
                MenuItem('my_profile', 'hr:my_profile', 'person-circle', 'Личный профиль'),
                MenuItem('tasks', 'tasks:list', 'check2-square', 'Менеджер задач', indicator_alias='task', permission=PermissionEnums.TASKS),
                MenuItem('hr', '#hr', 'people', 'HR', permission=PermissionEnums.HR, submenu=[
                    MenuItem('employees', 'hr:employees', '', 'Сотрудники'),
                    MenuItem('hr_documents', 'hr:documents_list', '', 'Кадровые документы'),
                    MenuItem('hr_permits', 'hr:permits_list', '', 'Допуски'),
                    MenuItem('hr_certifications', 'hr:certifications_list', '', 'Сертификации'),
                ]),
                MenuItem('finances', '#finances', 'credit-card', 'Финансы', permission=PermissionEnums.FINANCES, submenu=finance_readonly_submenu),
            ],

            RoleEnums.HR.value: [
                MenuItem('tasks', 'tasks:list', 'check2-square', 'Менеджер задач', indicator_alias='task', permission=PermissionEnums.TASKS),
                MenuItem('hr', '#hr', 'people', 'HR', permission=PermissionEnums.HR, submenu=[
                    MenuItem('my_profile', 'hr:my_profile', '', 'Личный профиль'),
                    MenuItem('org', 'hr:org', '', 'Орг. структура'),
                    MenuItem('employees', 'hr:employees', '', 'Сотрудники'),
                    MenuItem('companies_hr', 'hr:companies', '', 'Компании'),
                    MenuItem('departments_hr', 'hr:departments', '', 'Отделы'),
                    MenuItem('positions_hr', 'hr:positions', '', 'Должности'),
                    MenuItem('leaves', 'hr:leave_list', '', 'Заявки на отпуск'),
                    MenuItem('leave_timeline_page', 'hr:leave_timeline_page', '', 'Календарь отпусков'),
                    MenuItem('secondment', 'hr:calendar', '', 'Командировки', url_param=['secondment']),
                    MenuItem('hr_documents', 'hr:documents_list', '', 'Кадровые документы'),
                    MenuItem('hr_permits', 'hr:permits_list', '', 'Допуски'),
                    MenuItem('hr_certifications', 'hr:certifications_list', '', 'Сертификации'),
                    MenuItem('attendance_journal', 'hr:attendance_journal', '', 'Журнал посещаемости'),
                    MenuItem('attendance_my', 'hr:attendance_my', '', 'Моя посещаемость'),
                ]),
            ],

            RoleEnums.STAFF.value: [
                MenuItem('tasks', 'tasks:list', 'check2-square', 'Менеджер задач', indicator_alias='task', permission=PermissionEnums.TASKS),
                MenuItem('tickets', 'tickets:kanban', 'notebook-1', 'Заявки от арендаторов', indicator_alias='ticket', permission=PermissionEnums.SERVICE_REQUESTS),
            ],

            RoleEnums.GUEST.value: [
                MenuItem('tickets', 'tickets:home', 'notebook-1', 'Заявки от арендаторов', indicator_alias='ticket', permission=PermissionEnums.SERVICE_REQUESTS),
            ],

            RoleEnums.TENANT.value: [
                MenuItem('my_requisitions', 'requistions:home', 'inbox', 'Заявки на пропуск', permission=PermissionEnums.REQUISTIONS),
                MenuItem('tickets', 'tickets:home', 'tools', 'Заявки на обслуживание', indicator_alias='ticket', permission=PermissionEnums.SERVICE_REQUESTS),
            ],
        }

        role = user.role
        if hasattr(role, 'value'):
            role = role.value

        menu = list(items.get(role, []))

        if role == RoleEnums.STAFF.value:
            hr_submenu = [
                MenuItem('my_profile', 'hr:my_profile', '', 'Личный профиль'),
                MenuItem('leaves', 'hr:leave_list', '', 'Мои отпуска'),
                MenuItem('attendance_my', 'hr:attendance_my', '', 'Моя посещаемость'),
                MenuItem('hr_documents', 'hr:documents_list', '', 'Мои документы'),
            ]
            employee = getattr(user, 'employee_info', None)
            if employee and employee.head:
                hr_submenu[1:1] = [
                    MenuItem('org', 'hr:org', '', 'Орг. структура'),
                    MenuItem('employees', 'hr:employees', '', 'Сотрудники'),
                ]
            menu.append(
                MenuItem('hr', '#hr', 'user', 'HR', permission=PermissionEnums.HR_SELF, submenu=hr_submenu)
            )

        employee = getattr(user, 'employee_info', None)
        if employee and getattr(employee, 'head', False) and role != RoleEnums.ADMINISTRATOR.value:
            if not any(i.id == 'ticket_approvals' for i in menu):
                menu.append(
                    MenuItem('ticket_approvals', 'tickets:approvals', 'inbox-check', 'Согласования', permission=PermissionEnums.SERVICE_REQUESTS)
                )

        menu = MenuItem._filter_menu(menu, user)

        # ── Довыдаём пункты, доступные пользователю сверх стандартного набора его роли
        # (индивидуальные ALLOW-права или пакетные назначения профиля через FE-03).
        # Работает только для верхнеуровневых пунктов, не для отдельных элементов
        # внутри чужого подменю — такое считаем более редким кейсом. ──
        existing_ids = {i.id for i in menu}
        extra_pool = {}
        for role_items in items.values():
            for candidate in role_items:
                if candidate.permission and candidate.id not in extra_pool:
                    extra_pool[candidate.id] = candidate

        for item_id, candidate in extra_pool.items():
            if item_id in existing_ids:
                continue
            if user_has_permission(user, candidate.permission):
                menu.append(candidate)
                existing_ids.add(item_id)

        return menu