class AttachmentSpec:
    def __init__(self, key, get_object, get_file, get_title, can_view, can_edit):
        self.key = key
        self.get_object = get_object
        self.get_file = get_file
        self.get_title = get_title
        self.can_view = can_view
        self.can_edit = can_edit


_REGISTRY = {}


def register(spec):
    _REGISTRY[spec.key] = spec


def get_spec(key):
    return _REGISTRY.get(key)


def _document_spec():
    from .models import Document
    from account.role_permissions import RolePermissions, PermissionEnums

    def get_object(request, pk):
        return Document.get_by_id(request, pk)

    def get_file(obj):
        return obj.document

    def get_title(obj):
        return obj.title or (obj.document.name.split('/')[-1] if obj.document else '')

    def can_view(request, obj):
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.DOCUMENTS)

    def can_edit(request, obj):
        if not RolePermissions.checkPermission(request.user.role, PermissionEnums.EDIT_DOCUMENT):
            return False
        if obj.author_id == request.user.id:
            return True
        return obj.coordinators.filter(id=request.user.id).exists()

    return AttachmentSpec('document', get_object, get_file, get_title, can_view, can_edit)


def _task_file_spec():
    from tasks.models import Task, TaskFile
    from account.role_permissions import RolePermissions, PermissionEnums

    def get_object(request, pk):
        return TaskFile.objects.select_related('task').filter(pk=pk).first()

    def get_file(obj):
        return obj.file

    def get_title(obj):
        return obj.file.name.split('/')[-1] if obj.file else ''

    def can_view(request, obj):
        if obj is None:
            return False
        task = obj.task
        return Task.get_available_queryset(request).filter(pk=task.pk).exists()

    def can_edit(request, obj):
        if obj is None:
            return False
        task = obj.task
        if task.author_id == request.user.id or task.executor_id == request.user.id:
            return True
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.EDIT_DOCUMENT)

    return AttachmentSpec('task_file', get_object, get_file, get_title, can_view, can_edit)


def _hr_document_spec():
    from hr.models import EmployeeDocument
    from account.role_permissions import RolePermissions, PermissionEnums

    def get_object(request, pk):
        return EmployeeDocument.objects.select_related('employee').filter(pk=pk).first()

    def get_file(obj):
        return obj.file

    def get_title(obj):
        return obj.title or (obj.file.name.split('/')[-1] if obj.file else '')

    def can_view(request, obj):
        if obj is None:
            return False
        employee = getattr(request.user, 'employee_info', None)
        if employee and obj.employee_id == employee.id:
            return True
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)

    def can_edit(request, obj):
        if obj is None:
            return False
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)

    return AttachmentSpec('hr_document', get_object, get_file, get_title, can_view, can_edit)


register(_document_spec())
register(_task_file_spec())
register(_hr_document_spec())


def _hr_cert_spec():
    from hr.models import EmployeeCertification
    from account.role_permissions import RolePermissions, PermissionEnums
 
    def get_object(request, pk):
        return EmployeeCertification.objects.select_related('employee').filter(pk=pk).first()
 
    def get_file(obj):
        return obj.scan  # ImageField/FileField со сканом сертификата
 
    def get_title(obj):
        return obj.cert_type or (obj.scan.name.split('/')[-1] if obj.scan else '')
 
    def can_view(request, obj):
        if obj is None:
            return False
        employee = getattr(request.user, 'employee_info', None)
        if employee and obj.employee_id == employee.id:
            return True
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)
 
    def can_edit(request, obj):
        if obj is None:
            return False
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)
 
    return AttachmentSpec('hr_cert', get_object, get_file, get_title, can_view, can_edit)
 
 
def _hr_permit_spec():
    from hr.models import EmployeeWorkPermit
    from account.role_permissions import RolePermissions, PermissionEnums
 
    def get_object(request, pk):
        return EmployeeWorkPermit.objects.select_related('employee', 'category').filter(pk=pk).first()
 
    def get_file(obj):
        return obj.scan  # скан допуска
 
    def get_title(obj):
        cat = obj.category.name if obj.category else ''
        return cat or (obj.scan.name.split('/')[-1] if obj.scan else '')
 
    def can_view(request, obj):
        if obj is None:
            return False
        employee = getattr(request.user, 'employee_info', None)
        if employee and obj.employee_id == employee.id:
            return True
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)
 
    def can_edit(request, obj):
        if obj is None:
            return False
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)
 
    return AttachmentSpec('hr_permit', get_object, get_file, get_title, can_view, can_edit)
 
 
register(_hr_cert_spec())
register(_hr_permit_spec())


def _hr_cert_spec():
    from hr.models import EmployeeCertification
    from account.role_permissions import RolePermissions, PermissionEnums
 
    def get_object(request, pk):
        return EmployeeCertification.objects.select_related('employee').filter(pk=pk).first()
 
    def get_file(obj):
        return obj.scan  # ImageField/FileField со сканом сертификата
 
    def get_title(obj):
        return obj.cert_type or (obj.scan.name.split('/')[-1] if obj.scan else '')
 
    def can_view(request, obj):
        if obj is None:
            return False
        employee = getattr(request.user, 'employee_info', None)
        if employee and obj.employee_id == employee.id:
            return True
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)
 
    def can_edit(request, obj):
        if obj is None:
            return False
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)
 
    return AttachmentSpec('hr_cert', get_object, get_file, get_title, can_view, can_edit)
 
 
def _hr_permit_spec():
    from hr.models import EmployeeWorkPermit
    from account.role_permissions import RolePermissions, PermissionEnums
 
    def get_object(request, pk):
        return EmployeeWorkPermit.objects.select_related('employee', 'category').filter(pk=pk).first()
 
    def get_file(obj):
        return obj.scan  # скан допуска
 
    def get_title(obj):
        cat = obj.category.name if obj.category else ''
        return cat or (obj.scan.name.split('/')[-1] if obj.scan else '')
 
    def can_view(request, obj):
        if obj is None:
            return False
        employee = getattr(request.user, 'employee_info', None)
        if employee and obj.employee_id == employee.id:
            return True
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)
 
    def can_edit(request, obj):
        if obj is None:
            return False
        return RolePermissions.checkPermission(request.user.role, PermissionEnums.HR)
 
    return AttachmentSpec('hr_permit', get_object, get_file, get_title, can_view, can_edit)
 
 
register(_hr_cert_spec())
register(_hr_permit_spec())


def _ticket_attachment_spec():
    from tickets.models import TicketAttachment, TicketMessage
    from account.role_permissions import RolePermissions, PermissionEnums
 
    def get_object(request, pk):
        return TicketAttachment.objects.select_related('request', 'uploaded_by').filter(pk=pk).first()
 
    def get_file(obj):
        return obj.file
 
    def get_title(obj):
        return obj.filename or (obj.file.name.split('/')[-1] if obj.file else '')
 
    def can_view(request, obj):
        if obj is None:
            return False
        return TicketMessage.can_view(obj.request, request.user)
 
    def can_edit(request, obj):
        if obj is None:
            return False
        # Редактировать могут менеджеры или загрузивший файл
        from tickets.models import user_is_manager
        if user_is_manager(request.user):
            return True
        return obj.uploaded_by_id == request.user.id
 
    return AttachmentSpec('ticket_att', get_object, get_file, get_title, can_view, can_edit)
 
 
register(_ticket_attachment_spec())