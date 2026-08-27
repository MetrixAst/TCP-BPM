from django.test import TestCase, Client
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import UserAccount, Employee, Department
from hr.models import Company
from ecopark.models import (
    EcoObject, InspectionPoint, ChecklistItem,
    InspectionSchedule, InspectionRound, InspectionResult, Defect
)


def make_setup():
    admin = UserAccount.objects.create_user(username='admin_insp', password='pass', role='administrator')
    company = Company.objects.create(name='Insp Co', bin_number='555666777888')
    dept = Department.objects.create(name='Insp Dept', company=company)
    emp_user = UserAccount.objects.create_user(username='emp_insp', password='pass', role='staff')
    Employee.objects.create(user=emp_user, department=dept, status='active')
    eco_obj = EcoObject.objects.create(name='Корпус А')
    point = InspectionPoint.objects.create(
        name='Венткамера 1',
        point_type='ventilation',
        location='Подвал',
        eco_object=eco_obj,
    )
    InspectionSchedule.objects.create(point=point, interval_hours=4, assigned_to=emp_user)
    item1 = ChecklistItem.objects.create(point=point, order=1, text='Вентилятор работает', is_required=True)
    item2 = ChecklistItem.objects.create(point=point, order=2, text='Фильтры чистые', is_required=True)
    return admin, emp_user, point, item1, item2


class InspectionPointTest(TestCase):

    def setUp(self):
        self.admin, self.emp, self.point, self.item1, self.item2 = make_setup()

    def test_qr_code_generated(self):
        self.assertTrue(bool(self.point.qr_code))
        self.assertGreater(len(self.point.qr_code), 10)

    def test_qr_code_unique(self):
        eco_obj = EcoObject.objects.create(name='Корпус Б')
        point2 = InspectionPoint.objects.create(name='Электрощитовая 1', eco_object=eco_obj)
        self.assertNotEqual(self.point.qr_code, point2.qr_code)


class InspectionScanTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.emp, self.point, self.item1, self.item2 = make_setup()
        self.client.login(username='emp_insp', password='pass')

    def test_scan_valid_qr(self):
        r = self.client.get(f'/ecopark/inspection/scan/{self.point.qr_code}/')
        self.assertEqual(r.status_code, 200)

    def test_scan_invalid_qr(self):
        r = self.client.get('/ecopark/inspection/scan/invalid_qr_xxx/')
        self.assertEqual(r.status_code, 404)

    def test_scan_inactive_point(self):
        self.point.is_active = False
        self.point.save()
        r = self.client.get(f'/ecopark/inspection/scan/{self.point.qr_code}/')
        self.assertEqual(r.status_code, 404)


class InspectionSubmitTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.emp, self.point, self.item1, self.item2 = make_setup()
        self.client.login(username='emp_insp', password='pass')

    def test_submit_creates_round(self):
        import json
        payload = {
            'point_id': self.point.pk,
            'results': [
                {'checklist_item_id': self.item1.pk, 'status': 'ok', 'notes': ''},
                {'checklist_item_id': self.item2.pk, 'status': 'ok', 'notes': ''},
            ],
            'notes': 'Всё в порядке',
        }
        r = self.client.post(
            '/ecopark/inspection/api/submit/',
            json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['success'])
        self.assertTrue(InspectionRound.objects.filter(point=self.point, employee=self.emp).exists())

    def test_submit_with_defect_creates_defect(self):
        import json
        payload = {
            'point_id': self.point.pk,
            'results': [
                {'checklist_item_id': self.item1.pk, 'status': 'defect', 'notes': 'Сломан вентилятор'},
                {'checklist_item_id': self.item2.pk, 'status': 'ok', 'notes': ''},
            ],
            'notes': '',
        }
        r = self.client.post(
            '/ecopark/inspection/api/submit/',
            json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['has_defects'])
        self.assertTrue(Defect.objects.filter(
            result__round__point=self.point,
            status=Defect.STATUS_OPEN,
        ).exists())

    def test_submit_unauthenticated(self):
        import json
        self.client.logout()
        r = self.client.post(
            '/ecopark/inspection/api/submit/',
            json.dumps({'point_id': self.point.pk, 'results': []}),
            content_type='application/json',
        )
        self.assertIn(r.status_code, [302, 403])

    def test_server_time_set(self):
        import json
        payload = {
            'point_id': self.point.pk,
            'results': [],
            'notes': '',
        }
        self.client.post(
            '/ecopark/inspection/api/submit/',
            json.dumps(payload),
            content_type='application/json',
        )
        round_obj = InspectionRound.objects.filter(point=self.point).first()
        self.assertIsNotNone(round_obj.server_time)

    def test_historical_data_preserved(self):
        import json
        payload = {'point_id': self.point.pk, 'results': [], 'notes': ''}
        self.client.post('/ecopark/inspection/api/submit/', json.dumps(payload), content_type='application/json')
        self.client.post('/ecopark/inspection/api/submit/', json.dumps(payload), content_type='application/json')
        self.assertEqual(InspectionRound.objects.filter(point=self.point).count(), 2)


class DefectEscalateTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, self.emp, self.point, self.item1, self.item2 = make_setup()
        self.client.login(username='admin_insp', password='pass')

        round_obj = InspectionRound.objects.create(
            point=self.point, employee=self.emp, status='completed'
        )
        result = InspectionResult.objects.create(
            round=round_obj, checklist_item=self.item1, status='defect'
        )
        self.defect = Defect.objects.create(
            result=result,
            description='Сломан вентилятор',
            priority=Defect.PRIORITY_MEDIUM,
        )

    def test_escalate_changes_priority(self):
        r = self.client.post(f'/ecopark/inspection/api/defect/{self.defect.pk}/escalate/')
        self.assertEqual(r.status_code, 200)
        self.defect.refresh_from_db()
        self.assertEqual(self.defect.priority, Defect.PRIORITY_CRITICAL)
        self.assertIsNotNone(self.defect.escalated_at)

    def test_escalate_changes_status(self):
        self.client.post(f'/ecopark/inspection/api/defect/{self.defect.pk}/escalate/')
        self.defect.refresh_from_db()
        self.assertEqual(self.defect.status, Defect.STATUS_IN_PROGRESS)