from django.test import TestCase, Client
from django.utils import timezone

from account.models import UserAccount, Employee, Department
from hr.models import Company
from .models import EcoObject, ChecklistTemplate, RoundPoint, RoundVisit, Defect


def make_setup():
    company = Company.objects.create(name='FT05 Defects Co', bin_number='111333555777')
    dept = Department.objects.create(name='FT05 Defects Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_ft05d', password='pass', role='administrator')
    staff_user = UserAccount.objects.create_user(username='staff_ft05d', password='pass', role='staff')
    employee = Employee.objects.create(user=staff_user, department=dept, status='active')

    eco = EcoObject.objects.create(name='FT05 Defects Eco')
    checklist = ChecklistTemplate.objects.create(name='FT05 Defects Checklist', created_by=admin)
    point = RoundPoint.objects.create(name='FT05 Defects Точка', eco_object=eco, checklist=checklist, created_by=admin)

    return admin, staff_user, employee, point


class DefectsListNullReportedByTest(TestCase):
    """defects_list падал с VariableDoesNotExist на любом дефекте без
    reported_by (например, созданном через мобильный RoundPointAnswerView
    до этого фикса) — reported_by у Defect всегда был nullable (SET_NULL),
    так что шаблон обязан переживать None, а не только "фиксить источник"."""

    def setUp(self):
        self.client = Client()
        self.admin, self.staff_user, self.employee, self.point = make_setup()
        self.client.force_login(self.admin)

    def test_page_renders_with_null_reported_by(self):
        visit = RoundVisit.objects.create(point=self.point, employee=self.employee, created_at=timezone.now())
        Defect.objects.create(
            visit=visit,
            point=self.point,
            description='Дефект без автора',
            reported_by=None,
        )

        r = self.client.get('/ecopark/rounds/defects/')

        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Дефект без автора')
        self.assertContains(r, '—')

    def test_page_still_shows_author_when_present(self):
        visit = RoundVisit.objects.create(point=self.point, employee=self.employee, created_at=timezone.now())
        Defect.objects.create(
            visit=visit,
            point=self.point,
            description='Дефект с автором',
            reported_by=self.employee,
        )

        r = self.client.get('/ecopark/rounds/defects/')

        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Дефект с автором')
