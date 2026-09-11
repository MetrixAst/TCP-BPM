from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company, OfficeQRPoint, AttendanceRecord
from hr.enums import CheckInEnum
from ecopark.models import (
    EcoObject, ChecklistTemplate, ChecklistItem,
    RoundPoint, Route, RoutePoint, PlannedRound,
)


def make_setup():
    company = Company.objects.create(name='FT03R Co', bin_number='222333444555')
    dept = Department.objects.create(name='FT03R Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_ft03r', password='pass', role='administrator')
    emp_user = UserAccount.objects.create_user(username='emp_ft03r', password='pass', role='staff')
    no_profile_user = UserAccount.objects.create_user(username='noprofile_ft03r', password='pass', role='staff')
    employee = Employee.objects.create(user=emp_user, department=dept, status='active')

    office_qr = OfficeQRPoint.objects.create(name='FT03R Офис', created_by=admin)

    eco_obj = EcoObject.objects.create(name='FT03R Eco')
    template = ChecklistTemplate.objects.create(name='FT03R Template', created_by=admin)
    item1 = ChecklistItem.objects.create(template=template, order=1, text='Огнетушитель на месте', requires_photo_on_fail=True)
    item2 = ChecklistItem.objects.create(template=template, order=2, text='Освещение работает', requires_photo_on_fail=False)
    point = RoundPoint.objects.create(name='FT03R Точка', eco_object=eco_obj, checklist=template, created_by=admin)

    route = Route.objects.create(name='FT03R Маршрут', assigned_employee=emp_user, created_by=admin)
    RoutePoint.objects.create(route=route, point=point, order=1)
    now = timezone.now()
    planned = PlannedRound.objects.create(
        route=route, assigned_to=emp_user,
        planned_start=now - timedelta(hours=1), planned_end=now + timedelta(hours=1),
    )

    return admin, emp_user, no_profile_user, employee, office_qr, point, route, planned, item1, item2


class AttendanceOfficeQRCheckinTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        (self.admin, self.emp_user, self.no_profile_user, self.employee,
         self.office_qr, self.point, self.route, self.planned,
         self.item1, self.item2) = make_setup()
        self.client.force_authenticate(user=self.emp_user)

    def test_first_call_creates_day_start(self):
        r = self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['event_type'], CheckInEnum.DAY_START)
        self.assertTrue(AttendanceRecord.objects.filter(
            employee=self.employee, event_type=CheckInEnum.DAY_START, source='qr',
        ).exists())

    def test_second_call_creates_day_end(self):
        self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        r = self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['event_type'], CheckInEnum.DAY_END)

    def test_third_call_reports_already_done_no_new_record(self):
        self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        count_before = AttendanceRecord.objects.filter(employee=self.employee).count()
        r = self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['already_done'])
        self.assertEqual(AttendanceRecord.objects.filter(employee=self.employee).count(), count_before)

    def test_unknown_point_returns_404(self):
        import uuid
        r = self.client.post(f'/api/v1/mobile/attendance/office-qr/{uuid.uuid4()}/checkin/')
        self.assertEqual(r.status_code, 404)

    def test_inactive_point_returns_404(self):
        self.office_qr.is_active = False
        self.office_qr.save()
        r = self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.assertEqual(r.status_code, 404)

    def test_no_employee_profile_returns_403(self):
        self.client.force_authenticate(user=self.no_profile_user)
        r = self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.assertEqual(r.status_code, 403)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.assertEqual(r.status_code, 401)

    def test_idempotency_key_prevents_duplicate(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': 'ft03r-key-1'}
        r1 = self.client.post(
            f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/', **headers
        )
        r2 = self.client.post(
            f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/', **headers
        )
        self.assertEqual(r1.data['event_type'], r2.data['event_type'])
        self.assertEqual(
            AttendanceRecord.objects.filter(employee=self.employee).count(), 1
        )

    def test_historical_face_record_preserved(self):
        AttendanceRecord.objects.create(
            employee=self.employee,
            event_type=CheckInEnum.DAY_START,
            timestamp=timezone.now() - timedelta(days=3),
            source='face',
        )
        self.client.post(f'/api/v1/mobile/attendance/office-qr/{self.office_qr.public_id}/checkin/')
        self.assertTrue(AttendanceRecord.objects.filter(employee=self.employee, source='face').exists())


class RoundsResolveQRNextActionTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        (self.admin, self.emp_user, self.no_profile_user, self.employee,
         self.office_qr, self.point, self.route, self.planned,
         self.item1, self.item2) = make_setup()
        self.client.force_authenticate(user=self.emp_user)

    def test_next_action_is_day_start_initially(self):
        r = self.client.get(f'/api/v1/mobile/rounds/resolve/?qr={self.office_qr.public_id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['next_action'], CheckInEnum.DAY_START)
        self.assertFalse(r.data['already_done'])

    def test_already_done_after_both_marks(self):
        AttendanceRecord.objects.create(employee=self.employee, event_type=CheckInEnum.DAY_START, timestamp=timezone.now(), source='qr')
        AttendanceRecord.objects.create(employee=self.employee, event_type=CheckInEnum.DAY_END, timestamp=timezone.now(), source='qr')
        r = self.client.get(f'/api/v1/mobile/rounds/resolve/?qr={self.office_qr.public_id}')
        self.assertTrue(r.data['already_done'])
        self.assertIsNone(r.data['next_action'])


class RoundPointDetailTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        (self.admin, self.emp_user, self.no_profile_user, self.employee,
         self.office_qr, self.point, self.route, self.planned,
         self.item1, self.item2) = make_setup()
        self.client.force_authenticate(user=self.emp_user)

    def test_returns_checklist_items_in_order(self):
        r = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['items']), 2)
        self.assertEqual(r.data['items'][0]['id'], self.item1.pk)
        self.assertEqual(r.data['items'][0]['text'], 'Огнетушитель на месте')
        self.assertTrue(r.data['items'][0]['requires_photo_on_fail'])
        self.assertFalse(r.data['items'][1]['requires_photo_on_fail'])

    def test_already_visited_false_initially(self):
        r = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/')
        self.assertFalse(r.data['already_visited'])

    def test_already_visited_true_after_visit(self):
        from ecopark.models import RoundVisit
        RoundVisit.objects.create(point=self.point, employee=self.employee, created_at=timezone.now())
        r = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/')
        self.assertTrue(r.data['already_visited'])

    def test_unknown_point_returns_404(self):
        import uuid
        r = self.client.get(f'/api/v1/mobile/rounds/points/{uuid.uuid4()}/')
        self.assertEqual(r.status_code, 404)

    def test_no_employee_profile_returns_403(self):
        self.client.force_authenticate(user=self.no_profile_user)
        r = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/')
        self.assertEqual(r.status_code, 403)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/')
        self.assertEqual(r.status_code, 401)
