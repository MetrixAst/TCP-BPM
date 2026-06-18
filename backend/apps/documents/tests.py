from datetime import date, timedelta

from django.test import TestCase

from account.models import UserAccount
from account.role_permissions import RoleEnums
from documents import attachments, onlyoffice
from documents.models import Document, Folder
from tasks.models import Task, TaskFile
from hr.models import EmployeeDocument, Employee


class FakeRequest:
    def __init__(self, user):
        self.user = user
        self.current_lang = 'ru'

    def build_absolute_uri(self, path):
        return f'http://localhost{path}'


class OnlyOfficeRegistryTestCase(TestCase):
    def setUp(self):
        self.manager = UserAccount.objects.create_user(
            username='oo_manager', password='pass', role=RoleEnums.ADMINISTRATOR.value,
        )
        self.outsider = UserAccount.objects.create_user(
            username='oo_outsider', password='pass', role=RoleEnums.GUEST.value,
        )

    def test_registry_has_expected_specs(self):
        for key in ('document', 'task_file', 'hr_document'):
            self.assertIsNotNone(attachments.get_spec(key))

    def test_unknown_spec_returns_none(self):
        self.assertIsNone(attachments.get_spec('not_a_real_kind'))


class DocumentAttachmentSpecTestCase(TestCase):
    def setUp(self):
        self.manager = UserAccount.objects.create_user(
            username='doc_manager', password='pass', role=RoleEnums.ADMINISTRATOR.value,
        )
        self.outsider = UserAccount.objects.create_user(
            username='doc_outsider', password='pass', role=RoleEnums.GUEST.value,
        )
        self.folder = Folder.objects.create(name='Тестовая папка', root_type='incoming')
        self.document = Document.objects.create(
            title='Тестовый документ', author=self.manager, folder=self.folder,
        )
        from django.core.files.base import ContentFile
        self.document.document.save('test_doc.docx', ContentFile(b'fake content'), save=True)

    def test_get_title_returns_document_title(self):
        spec = attachments.get_spec('document')
        self.assertEqual(spec.get_title(self.document), 'Тестовый документ')

    def test_get_file_returns_file_field(self):
        spec = attachments.get_spec('document')
        file_field = spec.get_file(self.document)
        self.assertTrue(file_field.name.endswith('.docx'))

    def test_author_can_edit(self):
        spec = attachments.get_spec('document')
        req = FakeRequest(self.manager)
        self.assertTrue(spec.can_view(req, self.document))
        self.assertTrue(spec.can_edit(req, self.document))

    def test_build_config_works_for_document(self):
        spec = attachments.get_spec('document')
        req = FakeRequest(self.manager)
        title = spec.get_title(self.document)
        file_field = spec.get_file(self.document)
        config = onlyoffice.build_config(
            req, self.document.pk, file_field, title, True, '/callback/',
        )
        self.assertEqual(config['document']['title'], 'Тестовый документ')
        self.assertEqual(config['documentType'], 'word')
        self.assertIn('token', config)


class TaskFileAttachmentSpecTestCase(TestCase):
    def setUp(self):
        self.author = UserAccount.objects.create_user(
            username='tf_author', password='pass', role=RoleEnums.STAFF.value,
        )
        self.executor = UserAccount.objects.create_user(
            username='tf_executor', password='pass', role=RoleEnums.STAFF.value,
        )
        self.outsider = UserAccount.objects.create_user(
            username='tf_outsider', password='pass', role=RoleEnums.GUEST.value,
        )
        self.task = Task.objects.create(
            author=self.author, executor=self.executor, title='Тестовая задача',
            status='created', deadline=date.today() + timedelta(days=5),
        )
        from django.core.files.base import ContentFile
        self.task_file = TaskFile.objects.create(task=self.task, uploaded_by=self.author)
        self.task_file.file.save('test_task.xlsx', ContentFile(b'fake xlsx content'), save=True)

    def test_get_title_returns_filename(self):
        spec = attachments.get_spec('task_file')
        title = spec.get_title(self.task_file)
        self.assertTrue(title.startswith('test_task'))
        self.assertTrue(title.endswith('.xlsx'))

    def test_author_can_view_and_edit(self):
        spec = attachments.get_spec('task_file')
        req = FakeRequest(self.author)
        self.assertTrue(spec.can_view(req, self.task_file))
        self.assertTrue(spec.can_edit(req, self.task_file))

    def test_executor_can_view_and_edit(self):
        spec = attachments.get_spec('task_file')
        req = FakeRequest(self.executor)
        self.assertTrue(spec.can_view(req, self.task_file))
        self.assertTrue(spec.can_edit(req, self.task_file))

    def test_outsider_cannot_view_or_edit(self):
        spec = attachments.get_spec('task_file')
        req = FakeRequest(self.outsider)
        self.assertFalse(spec.can_view(req, self.task_file))
        self.assertFalse(spec.can_edit(req, self.task_file))

    def test_build_config_works_for_task_file(self):
        spec = attachments.get_spec('task_file')
        req = FakeRequest(self.author)
        title = spec.get_title(self.task_file)
        file_field = spec.get_file(self.task_file)
        config = onlyoffice.build_config(
            req, self.task_file.pk, file_field, title, True, '/callback/',
        )
        self.assertTrue(config['document']['title'].endswith('.xlsx'))
        self.assertEqual(config['documentType'], 'cell')


class HrDocumentAttachmentSpecTestCase(TestCase):
    def setUp(self):
        from account.models import Department
        from hr.models import Company

        self.hr_user = UserAccount.objects.create_user(
            username='hr_user', password='pass', role=RoleEnums.HR.value,
        )
        self.outsider = UserAccount.objects.create_user(
            username='hr_outsider', password='pass', role=RoleEnums.GUEST.value,
        )
        company = Company.objects.create(name='Тест компания', bin_number='123456789013')
        department = Department.objects.create(company=company, name='Тест отдел', level_type='department')
        self.employee = Employee.objects.create(
            user=self.outsider, iin='123456789012', hire_date=date.today(), department=department,
        )
        from django.core.files.base import ContentFile
        self.hr_doc = EmployeeDocument.objects.create(
            employee=self.employee, title='Трудовой договор', doc_type='contract',
        )
        self.hr_doc.file.save('contract.pdf', ContentFile(b'%PDF-1.4 fake'), save=True)

    def test_get_title_returns_title(self):
        spec = attachments.get_spec('hr_document')
        self.assertEqual(spec.get_title(self.hr_doc), 'Трудовой договор')

    def test_hr_role_can_view_and_edit(self):
        spec = attachments.get_spec('hr_document')
        req = FakeRequest(self.hr_user)
        self.assertTrue(spec.can_view(req, self.hr_doc))
        self.assertTrue(spec.can_edit(req, self.hr_doc))

    def test_owning_employee_can_view_but_not_edit(self):
        spec = attachments.get_spec('hr_document')
        req = FakeRequest(self.outsider)
        req.user.employee_info = self.employee
        self.assertTrue(spec.can_view(req, self.hr_doc))

    def test_build_config_works_for_hr_document(self):
        spec = attachments.get_spec('hr_document')
        req = FakeRequest(self.hr_user)
        title = spec.get_title(self.hr_doc)
        file_field = spec.get_file(self.hr_doc)
        config = onlyoffice.build_config(
            req, self.hr_doc.pk, file_field, title, True, '/callback/',
        )
        self.assertEqual(config['document']['title'], 'Трудовой договор')
        self.assertEqual(config['documentType'], 'pdf')


class OnlyOfficeHelpersTestCase(TestCase):
    def test_is_supported_known_extension(self):
        self.assertTrue(onlyoffice.is_supported('report.docx'))
        self.assertTrue(onlyoffice.is_supported('sheet.xlsx'))
        self.assertTrue(onlyoffice.is_supported('scan.pdf'))

    def test_is_supported_unknown_extension(self):
        self.assertFalse(onlyoffice.is_supported('archive.zip'))
        self.assertFalse(onlyoffice.is_supported('video.mp4'))

    def test_is_editable_for_editable_formats(self):
        self.assertTrue(onlyoffice.is_editable('report.docx'))
        self.assertTrue(onlyoffice.is_editable('sheet.xlsx'))

    def test_is_editable_for_view_only_formats(self):
        self.assertFalse(onlyoffice.is_editable('scan.pdf'))

    def test_get_document_type_mapping(self):
        self.assertEqual(onlyoffice.get_document_type('docx'), 'word')
        self.assertEqual(onlyoffice.get_document_type('xlsx'), 'cell')
        self.assertEqual(onlyoffice.get_document_type('pptx'), 'slide')
        self.assertEqual(onlyoffice.get_document_type('pdf'), 'pdf')
        self.assertEqual(onlyoffice.get_document_type('zip'), '')