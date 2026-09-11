from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company
from ecopark.models import (
    EcoObject, ChecklistTemplate, ChecklistItem, RoundPoint,
    Route, RoutePoint, PlannedRound, Defect,
)


class MobileDefectAttributionTest(TestCase):
    """RoundPointAnswerView создавал Defect без reported_by — из-за этого
    падала веб-страница /ecopark/rounds/defects/ (VariableDoesNotExist) на
    любом дефекте, заведённом с телефона. Проверяем, что автор теперь
    проставляется так же, как в веб-версии (rounds_scan)."""

    def setUp(self):
        self.client = APIClient()
        company = Company.objects.create(name='FT05 Attr Co', bin_number='222444666888')
        dept = Department.objects.create(name='FT05 Attr Dept', company=company)
        admin = UserAccount.objects.create_user(username='admin_ft05a', password='pass', role='administrator')
        self.emp_user = UserAccount.objects.create_user(username='emp_ft05a', password='pass', role='staff')
        self.employee = Employee.objects.create(user=self.emp_user, department=dept, status='active')

        eco = EcoObject.objects.create(name='FT05 Attr Eco')
        template = ChecklistTemplate.objects.create(name='FT05 Attr Template', created_by=admin)
        self.item = ChecklistItem.objects.create(template=template, order=1, text='Пункт', requires_photo_on_fail=False)
        self.point = RoundPoint.objects.create(name='FT05 Attr Точка', eco_object=eco, checklist=template, created_by=admin)

        route = Route.objects.create(name='FT05 Attr Маршрут', assigned_employee=self.emp_user, created_by=admin)
        RoutePoint.objects.create(route=route, point=self.point, order=1)
        now = timezone.now()
        self.planned = PlannedRound.objects.create(
            route=route, assigned_to=self.emp_user,
            planned_start=now - timedelta(hours=1), planned_end=now + timedelta(hours=1),
        )
        self.client.force_authenticate(user=self.emp_user)

    def test_defect_from_mobile_has_reported_by(self):
        r = self.client.post(
            f'/api/v1/mobile/rounds/{self.planned.pk}/points/{self.point.uuid}/answer/',
            {f'item_{self.item.pk}_status': 'fail', f'item_{self.item.pk}_comment': 'Сломано'},
            format='multipart',
        )
        self.assertEqual(r.status_code, 201)
        defect = Defect.objects.get(visit__point=self.point)
        self.assertEqual(defect.reported_by, self.employee)
        self.assertIsNotNone(defect.answer_id)
