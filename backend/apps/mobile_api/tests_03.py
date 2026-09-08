from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company, OfficeQRPoint
from ecopark.models import (
    EcoObject, ChecklistTemplate, ChecklistItem,
    RoundPoint, Route, RoutePoint, PlannedRound, RoundVisit
)


def make_setup():
    company = Company.objects.create(name='FT03 Co', bin_number='111222333555')
    dept = Department.objects.create(name='FT03 Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_ft03', password='pass', role='administrator')
    emp_user = UserAccount.objects.create_user(username='emp_ft03', password='pass', role='staff')
    other_user = UserAccount.objects.create_user(username='other_ft03', password='pass', role='staff')
    employee = Employee.objects.create(user=emp_user, department=dept, status='active')
    Employee.objects.create(user=other_user, department=dept, status='active')

    eco_obj = EcoObject.objects.create(name='FT03 Eco')
    template = ChecklistTemplate.objects.create(name='FT03 Template', created_by=admin)
    item1 = ChecklistItem.objects.create(template=template, order=1, text='Пункт 1')
    item2 = ChecklistItem.objects.create(template=template, order=2, text='Пункт 2')

    point = RoundPoint.objects.create(
        name='FT03 Точка',
        eco_object=eco_obj,
        checklist=template,
        created_by=admin,
    )

    route = Route.objects.create(name='FT03 Маршрут', assigned_employee=emp_user, created_by=admin)
    RoutePoint.objects.create(route=route, point=point, order=1)

    now = timezone.now()
    planned = PlannedRound.objects.create(
        route=route,
        assigned_to=emp_user,
        planned_start=now - timedelta(hours=1),
        planned_end=now + timedelta(hours=1),
    )

    office_qr = OfficeQRPoint.objects.create(name='FT03 Офис', created_by=admin)

    return admin, emp_user, other_user, employee, point, route, planned, office_qr, item1, item2


class RoundsTodayTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp_user, self.other, self.emp, \
            self.point, self.route, self.planned, self.office_qr, \
            self.item1, self.item2 = make_setup()
        self.client.force_authenticate(user=self.emp_user)

    def test_today_returns_own_rounds(self):
        r = self.client.get('/api/v1/mobile/rounds/today/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]['id'], self.planned.pk)

    def test_today_excludes_others_rounds(self):
        self.client.force_authenticate(user=self.other)
        r = self.client.get('/api/v1/mobile/rounds/today/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 0)

    def test_unauthenticated_denied(self):
        self.client.force_authenticate(user=None)
        r = self.client.get('/api/v1/mobile/rounds/today/')
        self.assertEqual(r.status_code, 401)


class RoundsResolveQRTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp_user, self.other, self.emp, \
            self.point, self.route, self.planned, self.office_qr, \
            self.item1, self.item2 = make_setup()
        self.client.force_authenticate(user=self.emp_user)

    def test_resolve_office_qr(self):
        r = self.client.get(f'/api/v1/mobile/rounds/resolve/?qr={self.office_qr.public_id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['type'], 'office_checkin')

    def test_resolve_round_point_qr(self):
        r = self.client.get(f'/api/v1/mobile/rounds/resolve/?qr={self.point.uuid}')
        print('STATUS:', r.status_code)
        print('DATA:', r.data)
        self.assertEqual(r.status_code, 200)

    def test_resolve_invalid_qr(self):
        r = self.client.get('/api/v1/mobile/rounds/resolve/?qr=invalid-uuid')
        self.assertIn(r.status_code, [400, 404])


class RoundDetailTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp_user, self.other, self.emp, \
            self.point, self.route, self.planned, self.office_qr, \
            self.item1, self.item2 = make_setup()
        self.client.force_authenticate(user=self.emp_user)

    def test_detail_returns_correct_data(self):
        r = self.client.get(f'/api/v1/mobile/rounds/{self.planned.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['id'], self.planned.pk)
        self.assertEqual(r.data['total'], 1)
        self.assertEqual(r.data['completed'], 0)

    def test_other_user_gets_403(self):
        self.client.force_authenticate(user=self.other)
        r = self.client.get(f'/api/v1/mobile/rounds/{self.planned.pk}/')
        self.assertEqual(r.status_code, 403)


class RoundPointAnswerTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.emp_user, self.other, self.emp, \
            self.point, self.route, self.planned, self.office_qr, \
            self.item1, self.item2 = make_setup()
        self.client.force_authenticate(user=self.emp_user)

    def test_answer_creates_visit(self):
        r = self.client.post(
            f'/api/v1/mobile/rounds/{self.planned.pk}/points/{self.point.uuid}/answer/',
            {
                f'item_{self.item1.pk}_status': 'ok',
                f'item_{self.item2.pk}_status': 'ok',
                'comment': 'Всё в порядке',
            },
            format='multipart',
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data['success'])
        self.assertTrue(RoundVisit.objects.filter(point=self.point).exists())

    def test_idempotency_no_duplicate_visit(self):
        url = f'/api/v1/mobile/rounds/{self.planned.pk}/points/{self.point.uuid}/answer/'
        self.client.post(url, {}, format='multipart')
        count_before = RoundVisit.objects.count()
        r = self.client.post(url, {}, format='multipart')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['already_done'])
        self.assertEqual(RoundVisit.objects.count(), count_before)

    def test_other_user_gets_403(self):
        self.client.force_authenticate(user=self.other)
        r = self.client.post(
            f'/api/v1/mobile/rounds/{self.planned.pk}/points/{self.point.uuid}/answer/',
            {},
            format='multipart',
        )
        self.assertEqual(r.status_code, 403)

    def test_defect_created_on_fail(self):
        from ecopark.models import Defect
        r = self.client.post(
            f'/api/v1/mobile/rounds/{self.planned.pk}/points/{self.point.uuid}/answer/',
            {
                f'item_{self.item1.pk}_status': 'fail',
                f'item_{self.item1.pk}_comment': 'Сломано',
                f'item_{self.item2.pk}_status': 'ok',
            },
            format='multipart',
        )
        self.assertEqual(r.status_code, 201)
        self.assertGreater(r.data['defects_created'], 0)
        self.assertTrue(Defect.objects.filter(visit__point=self.point).exists())