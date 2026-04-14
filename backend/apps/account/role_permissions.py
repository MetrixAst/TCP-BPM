from enum import Enum
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

class RoleEnums(Enum):
    ADMINISTRATOR = "administrator"
    STAFF = "staff"
    GUEST = "guest"

    @staticmethod
    def tenant_roles():
        return [RoleEnums.ADMINISTRATOR.value, RoleEnums.STAFF.value]
    

class PermissionEnums(Enum):

    PROFILE = "profile"
    
    #dashboard
    DASHBOARD = "dashboard"

    #tasks
    TASKS = "tasks"
    EDIT_TASK = "edit_task"

    #documents
    DOCUMENTS = "documents"
    EDIT_DOCUMENT = "edit_document"

    #tenants
    TENANTS = "tenants"

    #purchases
    PURCHASES = "purchases"
    SUPPLIERS = "suppliers"
    EDIT_SUPPLIERS = "edit_suppliers"

    #finances
    FINANCES = "finances"

    #hr
    HR = "hr"

    #ecopark
    ECOPARK = "ecopark"

    #requistions
    REQUISTIONS = "requistions"

    #reports
    REPORTS = "reports"

    #ADDITS
    COMMENT = "comment"
    USERS_LIST = "users_list"
    
    

class RolePermissions:
    permissions = {
        RoleEnums.ADMINISTRATOR.value: [

            PermissionEnums.PROFILE,
            PermissionEnums.USERS_LIST,
            
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
            PermissionEnums.ECOPARK,
            PermissionEnums.REQUISTIONS,
            PermissionEnums.REPORTS,
            PermissionEnums.COMMENT,
        ],

        RoleEnums.STAFF.value: [
            PermissionEnums.PROFILE,
            PermissionEnums.DASHBOARD,
            PermissionEnums.TASKS,
            PermissionEnums.EDIT_TASK,
            PermissionEnums.USERS_LIST,
            
            PermissionEnums.DOCUMENTS,
            PermissionEnums.TENANTS,
            PermissionEnums.HR,
            PermissionEnums.COMMENT,
        ],

        RoleEnums.GUEST.value: [
            PermissionEnums.DASHBOARD,
            PermissionEnums.REQUISTIONS,
        ],
    }

    @staticmethod
    def checkPermission(role, permission):
        return permission in RolePermissions.permissions[role]



#DECORATORS

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

def need_permission(permission):
    def _method_wrapper(view_method):
        def _arguments_wrapper(request, *args, **kwargs) :
            if request.user.is_authenticated:
                role = request.user.role
                if role is not None:
                    if RolePermissions.checkPermission(role, permission):
                        return view_method(request, *args, **kwargs)
                
                raise PermissionDenied()
                
            else:
                response = redirect('account:auth')
                response['Location'] += f"?next={request.path}"
                return response
        return _arguments_wrapper
    return _method_wrapper


#MENU
class MenuItem():
    def __init__(self, id, url, icon, title, submenu = None, url_param = None, indicator_alias = None):
        self.id = id
        self.title = title
        self.icon = icon
        self.submenu = submenu
        self.indicator_alias = indicator_alias or self.id

        self.url = url
        if url != '#' and not url.startswith("#"):
            if url_param is not None:
                self.url = reverse(url, args=url_param)
            else:
                self.url = reverse(url)

    def first_page(user):
        items = {
            RoleEnums.ADMINISTRATOR.value: 'dashboard:dashboard',
            RoleEnums.STAFF.value: 'dashboard:dashboard',
            RoleEnums.GUEST.value: 'requistions:home',
        }

        return items.get(user.role, None)
    
    def first_page_as_string(user):
        route = MenuItem.first_page(user)
        if route is not None:
            return reverse(route)
        return None

    

    @staticmethod
    def generate_menu(user):
        items = {
            RoleEnums.ADMINISTRATOR.value: [
                MenuItem('tasks', 'tasks:list', 'grid-1', 'Менеджер задач', indicator_alias='task'),
                MenuItem('documents', 'documents:list', 'file-text', 'Документооборот', url_param=['documents']),
                # MenuItem('tenants', 'tenants:list', 'home', 'Арендаторы'),
                MenuItem('tenants', '#tenants', 'home', 'Компании', submenu=[
                    MenuItem('suppliers', 'purchases:suppliers', '', 'Контрагенты'),
                    MenuItem('tenants_list', 'tenants:list', '', 'Арендаторы'),
                ]),
                MenuItem('purchases', 'documents:list', 'folders', 'Закупки', url_param=['purchases']),
                MenuItem('finances', '#finances', 'form', 'Финансы', submenu=[
                    MenuItem('reg', 'finances:reg', '', 'Реестр оплат'),
                    MenuItem('calendar', 'finances:calendar', '', 'Финансовый календарь'),
                    MenuItem('budget', 'documents:list', '', 'Бюджет компании', url_param=['budget']),
                    MenuItem('bill', 'finances:bill', '', 'Счет компании'),
                ]),
                MenuItem('hr', '#hr', 'user', 'HR', submenu=[
                    MenuItem('org', 'hr:org', '', 'Орг. структура'),
                    MenuItem('employees', 'hr:employees', '', 'Сотрудники'),
                    MenuItem('secondment', 'hr:calendar', '', 'Командировки', url_param=['secondment']),
                    MenuItem('vacation', 'hr:calendar', '', 'Отпуски', url_param=['vacation']),
                    # MenuItem('vacancies', 'hr:home', '', 'Вакансии'),
                    # MenuItem('templates', 'hr:home', '', 'Шаблон (документов)'),
                ]),
                MenuItem('ecopark', 'ecopark:home', 'water', 'Эксплуатация'),
                MenuItem('requistions', 'requistions:home', 'notebook-1', 'Заявки от арендаторов'),
                MenuItem('reports', 'reports:home', 'eye', 'Показатели'),
            ],

            RoleEnums.STAFF.value: [
                MenuItem('tasks', 'tasks:list', 'grid-1', 'Менеджер задач', indicator_alias='task'),
                MenuItem('documents', 'documents:list', 'file-text', 'Документооборот', url_param=['documents']),
                MenuItem('tenants', 'tenants:list', 'home', 'Арендаторы'),
            ],


            RoleEnums.GUEST.value: [
                MenuItem('requistions', 'requistions:home', 'notebook-1', 'Заявки'),
            ],
        }

        result = items.get(user.role, [])

        return result