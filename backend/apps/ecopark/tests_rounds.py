import uuid

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from account.models import UserAccount, Employee, Department
from hr.models import Company
from .models import (
    RoundPoint, ChecklistTemplate, ChecklistItem,
    RoundVisit, RoundVisitAnswer, Defect,
)


def make_setup(head=False):
    company = Company.objects.create(name='Rounds Co', bin_number='999888777666')
    dept = Department.objects.create(name='Rounds Dept', company=company)
    admin = UserAccount.objects.create_user(username='admin_rounds', password='pass', role='administrator')
    staff_user = UserAccount.objects.create_user(username='staff_rounds', password='pass', role='staff')
    employee = Employee.objects.create(user=staff_user, department=dept, status='active', head=head)

    checklist = ChecklistTemplate.objects.create(name='Стандартный', created_by=admin)
    item_no_photo = ChecklistItem.objects.create(
        template=checklist, order=0, text='Освещение', requires_photo_on_fail=False,
    )
    item_photo = ChecklistItem.objects.create(
        template=checklist, order=1, text='Огнетушитель', requires_photo_on_fail=True,
    )
    point = RoundPoint.objects.create(
        name='Точка 1', checklist=checklist, created_by=admin, check_interval_hours=24,
    )
    return admin, staff_user, employee, checklist, point, item_no_photo, item_photo


def tiny_image():
    return SimpleUploadedFile('photo.jpg', b'\x47\x49\x46\x38', content_type='image/jpeg')


class RoundsScanTest(TestCase):
    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()

    def _scan_url(self, point_uuid):
        return f'/ecopark/rounds/scan/{point_uuid}/'

    def test_unknown_point_rejected(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self._scan_url(uuid.uuid4()))
        self.assertEqual(response.status_code, 404)

    def test_inactive_point_rejected(self):
        self.point.is_active = False
        self.point.save()
        self.client.force_login(self.staff_user)
        response = self.client.get(self._scan_url(self.point.uuid))
        self.assertEqual(response.status_code, 400)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self._scan_url(self.point.uuid))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/account/', response['Location'])

    def test_user_without_employee_profile_rejected(self):
        bare_user = UserAccount.objects.create_user(username='no_employee', password='pass', role='staff')
        self.client.force_login(bare_user)
        response = self.client.get(self._scan_url(self.point.uuid))
        self.assertEqual(response.status_code, 403)

    def test_all_pass_creates_visit_no_defects(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(self._scan_url(self.point.uuid), {
            f'item_{self.item_no_photo.pk}_passed': 'yes',
            f'item_{self.item_photo.pk}_passed': 'yes',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RoundVisit.objects.count(), 1)
        self.assertEqual(Defect.objects.count(), 0)
        visit = RoundVisit.objects.first()
        self.assertFalse(visit.has_failed_items)

    def test_fail_without_required_photo_rejected(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(self._scan_url(self.point.uuid), {
            f'item_{self.item_no_photo.pk}_passed': 'yes',
            f'item_{self.item_photo.pk}_passed': 'no',
            # фото не приложено, хотя requires_photo_on_fail=True
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(RoundVisit.objects.count(), 0)

    def test_fail_with_photo_creates_defect(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(self._scan_url(self.point.uuid), {
            f'item_{self.item_no_photo.pk}_passed': 'yes',
            f'item_{self.item_photo.pk}_passed': 'no',
            f'item_{self.item_photo.pk}_comment': 'Пусто, огнетушителя нет',
            f'item_{self.item_photo.pk}_photo': tiny_image(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RoundVisit.objects.count(), 1)
        self.assertEqual(Defect.objects.count(), 1)
        defect = Defect.objects.first()
        self.assertEqual(defect.status, Defect.STATUS_OPEN)
        self.assertEqual(defect.point, self.point)

    def test_fail_without_required_photo_on_item_that_does_not_require_it(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(self._scan_url(self.point.uuid), {
            f'item_{self.item_no_photo.pk}_passed': 'no',
            f'item_{self.item_photo.pk}_passed': 'yes',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Defect.objects.count(), 1)


class RoundsAdminAccessTest(TestCase):
    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()

    def test_non_admin_cannot_list_points(self):
        self.client.force_login(self.staff_user)
        response = self.client.get('/ecopark/rounds/points/')
        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_points(self):
        self.client.force_login(self.admin)
        response = self.client.get('/ecopark/rounds/points/')
        self.assertEqual(response.status_code, 200)

    def test_non_admin_cannot_create_checklist(self):
        self.client.force_login(self.staff_user)
        response = self.client.get('/ecopark/rounds/checklists/create/')
        self.assertEqual(response.status_code, 403)


class RoundAssignmentTest(TestCase):
    def setUp(self):
        (
            self.admin,
            self.staff_user,
            self.employee,
            self.checklist,
            self.point,
            self.item_no_photo,
            self.item_photo,
        ) = make_setup()
        self.other_user = UserAccount.objects.create_user(
            username='other_rounds',
            password='pass',
            role='staff',
        )
        self.other_employee = Employee.objects.create(
            user=self.other_user,
            department=self.employee.department,
            status='active',
        )

    def _scan_url(self):
        return f'/ecopark/rounds/scan/{self.point.uuid}/'

    def test_unassigned_point_is_available_to_any_employee(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self._scan_url())

        self.assertEqual(response.status_code, 200)

    def test_unassigned_employee_is_rejected(self):
        self.point.responsible_employee = self.employee
        self.point.save(update_fields=['responsible_employee'])
        self.client.force_login(self.other_user)

        response = self.client.get(self._scan_url())

        self.assertEqual(response.status_code, 403)

    def test_responsible_employee_is_allowed(self):
        self.point.responsible_employee = self.employee
        self.point.save(update_fields=['responsible_employee'])
        self.client.force_login(self.staff_user)

        response = self.client.get(self._scan_url())

        self.assertEqual(response.status_code, 200)

    def test_responsible_department_employee_is_allowed(self):
        self.point.responsible_department = self.employee.department
        self.point.save(update_fields=['responsible_department'])
        self.client.force_login(self.other_user)

        response = self.client.get(self._scan_url())

        self.assertEqual(response.status_code, 200)

    def test_substitute_employee_is_allowed(self):
        self.point.responsible_employee = self.employee
        self.point.substitute_employee = self.other_employee
        self.point.save(
            update_fields=['responsible_employee', 'substitute_employee']
        )
        self.client.force_login(self.other_user)

        response = self.client.get(self._scan_url())

        self.assertEqual(response.status_code, 200)

    def test_admin_can_save_round_assignments(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            f'/ecopark/rounds/points/{self.point.pk}/edit/',
            {
                'name': self.point.name,
                'check_interval_hours': 12,
                'is_active': 'on',
                'responsible_employee': self.employee.pk,
                'responsible_department': self.employee.department_id,
                'substitute_employee': self.other_employee.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.point.refresh_from_db()
        self.assertEqual(self.point.responsible_employee, self.employee)
        self.assertEqual(
            self.point.responsible_department,
            self.employee.department,
        )
        self.assertEqual(self.point.substitute_employee, self.other_employee)


class RoundsMonitorAccessTest(TestCase):
    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()

    def test_regular_staff_cannot_see_journal(self):
        self.client.force_login(self.staff_user)
        response = self.client.get('/ecopark/rounds/journal/')
        self.assertEqual(response.status_code, 403)

    def test_department_head_can_see_journal(self):
        head_user = UserAccount.objects.create_user(username='head_rounds', password='pass', role='staff')
        Employee.objects.create(user=head_user, department=self.employee.department, status='active', head=True)
        self.client.force_login(head_user)
        response = self.client.get('/ecopark/rounds/journal/')
        self.assertEqual(response.status_code, 200)

    def test_admin_can_see_journal_and_defects(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/ecopark/rounds/journal/').status_code, 200)
        self.assertEqual(self.client.get('/ecopark/rounds/defects/').status_code, 200)

    def test_department_head_cannot_manage_points(self):
        head_user = UserAccount.objects.create_user(username='head_rounds2', password='pass', role='staff')
        Employee.objects.create(user=head_user, department=self.employee.department, status='active', head=True)
        self.client.force_login(head_user)
        response = self.client.get('/ecopark/rounds/points/')
        self.assertEqual(response.status_code, 403)


class DefectResolveTest(TestCase):
    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()
        self.visit = RoundVisit.objects.create(point=self.point, employee=self.employee)
        answer = RoundVisitAnswer.objects.create(visit=self.visit, item=self.item_photo, passed=False)
        self.defect = Defect.objects.create(
            visit=self.visit, answer=answer, point=self.point,
            description='Тест', reported_by=self.employee,
        )

    def test_resolve_sets_status_and_resolver(self):
        self.client.force_login(self.admin)
        response = self.client.post(f'/ecopark/rounds/defects/{self.defect.pk}/resolve/')
        self.assertEqual(response.status_code, 302)
        self.defect.refresh_from_db()
        self.assertEqual(self.defect.status, Defect.STATUS_RESOLVED)
        self.assertEqual(self.defect.resolved_by, self.admin)
        self.assertIsNotNone(self.defect.resolved_at)

    def test_non_monitor_cannot_resolve(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(f'/ecopark/rounds/defects/{self.defect.pk}/resolve/')
        self.assertEqual(response.status_code, 403)
        self.defect.refresh_from_db()
        self.assertEqual(self.defect.status, Defect.STATUS_OPEN)


class DefectEscalateTest(TestCase):
    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()
        self.visit = RoundVisit.objects.create(point=self.point, employee=self.employee)
        answer = RoundVisitAnswer.objects.create(visit=self.visit, item=self.item_photo, passed=False)
        self.defect = Defect.objects.create(
            visit=self.visit, answer=answer, point=self.point,
            description='Тест', reported_by=self.employee,
        )

    def test_escalate_sets_priority_and_assignee(self):
        self.client.force_login(self.admin)
        response = self.client.post(f'/ecopark/rounds/defects/{self.defect.pk}/escalate/')
        self.assertEqual(response.status_code, 302)
        self.defect.refresh_from_db()
        self.assertEqual(self.defect.priority, Defect.PRIORITY_CRITICAL)
        self.assertEqual(self.defect.status, Defect.STATUS_IN_PROGRESS)
        self.assertEqual(self.defect.assigned_to, self.admin)
        self.assertIsNotNone(self.defect.escalated_at)

    def test_non_monitor_cannot_escalate(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(f'/ecopark/rounds/defects/{self.defect.pk}/escalate/')
        self.assertEqual(response.status_code, 403)
        self.defect.refresh_from_db()
        self.assertEqual(self.defect.priority, Defect.PRIORITY_MEDIUM)


class EquipmentTest(TestCase):
    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()

    def test_admin_can_add_equipment_via_point_edit(self):
        self.client.force_login(self.admin)
        response = self.client.post(f'/ecopark/rounds/points/{self.point.pk}/edit/', {
            'name': self.point.name,
            'location': self.point.location,
            'check_interval_hours': self.point.check_interval_hours,
            'equipment_id[]': [''],
            'equipment_name[]': ['Насос №1'],
            'equipment_description[]': ['Основной насос'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.point.equipment.count(), 1)
        self.assertEqual(self.point.equipment.first().name, 'Насос №1')

    def test_non_admin_cannot_reach_point_edit(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(f'/ecopark/rounds/points/{self.point.pk}/edit/')
        self.assertEqual(response.status_code, 403)


class OverdueCalculationTest(TestCase):
    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()

    def test_never_visited_point_overdue_after_interval_from_creation(self):
        from django.utils import timezone
        from datetime import timedelta
        self.point.check_interval_hours = 1
        self.point.created_at = timezone.now() - timedelta(hours=2)
        self.point.save()
        self.assertTrue(self.point.is_overdue)

    def test_never_visited_point_not_overdue_within_interval(self):
        self.point.check_interval_hours = 24
        self.assertFalse(self.point.is_overdue)

    def test_recently_visited_point_not_overdue(self):
        RoundVisit.objects.create(point=self.point, employee=self.employee)
        self.assertFalse(self.point.is_overdue)


class HistoryPreservationTest(TestCase):
    """Точку/чек-лист/пункт с историей нельзя жёстко удалить (PROTECT)."""

    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()
        self.visit = RoundVisit.objects.create(point=self.point, employee=self.employee)
        RoundVisitAnswer.objects.create(visit=self.visit, item=self.item_no_photo, passed=True)

    def test_deleting_point_with_history_deactivates_instead(self):
        self.client.force_login(self.admin)
        response = self.client.post(f'/ecopark/rounds/points/{self.point.pk}/delete/')
        self.assertEqual(response.status_code, 302)
        self.point.refresh_from_db()
        self.assertFalse(self.point.is_active)
        self.assertEqual(RoundVisit.objects.count(), 1)

    def test_deleting_point_without_history_hard_deletes(self):
        empty_point = RoundPoint.objects.create(name='Пустая точка', created_by=self.admin)
        self.client.force_login(self.admin)
        response = self.client.post(f'/ecopark/rounds/points/{empty_point.pk}/delete/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RoundPoint.objects.filter(pk=empty_point.pk).exists())

    def test_deleting_checklist_with_history_deactivates_instead(self):
        self.client.force_login(self.admin)
        response = self.client.post(f'/ecopark/rounds/checklists/{self.checklist.pk}/delete/')
        self.assertEqual(response.status_code, 302)
        self.checklist.refresh_from_db()
        self.assertFalse(self.checklist.is_active)
        self.assertEqual(RoundVisitAnswer.objects.count(), 1)


class RoundVisitGeoTest(TestCase):
    """
    Статичный (печатный) QR, в отличие от короткоживущего check-in-токена,
    можно сфотографировать один раз и переиспользовать удалённо — сверка
    геолокации ловит именно этот случай ("отметился, не приходя на место").
    """

    def setUp(self):
        self.admin, self.staff_user, self.employee, self.checklist, self.point, self.item_no_photo, self.item_photo = make_setup()

    def test_point_without_coords_is_unknown(self):
        visit = RoundVisit.objects.create(point=self.point, employee=self.employee, latitude=43.222, longitude=76.851)
        self.assertEqual(visit.geo_status, RoundVisit.GEO_UNKNOWN)
        self.assertIsNone(visit.geo_distance_m)

    def test_visit_without_coords_is_missing(self):
        self.point.latitude = 43.222
        self.point.longitude = 76.851
        self.point.save()
        visit = RoundVisit.objects.create(point=self.point, employee=self.employee)
        self.assertEqual(visit.geo_status, RoundVisit.GEO_MISSING)

    def test_nearby_visit_is_ok(self):
        self.point.latitude = 43.222000
        self.point.longitude = 76.851000
        self.point.save()
        # ~15м смещение — в пределах порога и обычной погрешности GPS
        visit = RoundVisit.objects.create(
            point=self.point, employee=self.employee,
            latitude=43.222100, longitude=76.851000,
        )
        self.assertEqual(visit.geo_status, RoundVisit.GEO_OK)

    def test_far_visit_is_mismatch(self):
        self.point.latitude = 43.222000
        self.point.longitude = 76.851000
        self.point.save()
        # ~1.1км смещение по широте — явно "не на месте"
        visit = RoundVisit.objects.create(
            point=self.point, employee=self.employee,
            latitude=43.232000, longitude=76.851000,
        )
        self.assertEqual(visit.geo_status, RoundVisit.GEO_MISMATCH)
        self.assertGreater(visit.geo_distance_m, 200)

    def test_scan_submission_saves_coordinates(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(f'/ecopark/rounds/scan/{self.point.uuid}/', {
            f'item_{self.item_no_photo.pk}_passed': 'yes',
            f'item_{self.item_photo.pk}_passed': 'yes',
            'latitude': '43.2220000',
            'longitude': '76.8510000',
        })
        self.assertEqual(response.status_code, 200)
        visit = RoundVisit.objects.first()
        self.assertIsNotNone(visit.latitude)
        self.assertIsNotNone(visit.longitude)

    def test_scan_submission_without_geolocation_still_succeeds(self):
        # Отказ в доступе к геолокации не должен блокировать обход —
        # только помечает его как "нет данных" для руководителя.
        self.client.force_login(self.staff_user)
        response = self.client.post(f'/ecopark/rounds/scan/{self.point.uuid}/', {
            f'item_{self.item_no_photo.pk}_passed': 'yes',
            f'item_{self.item_photo.pk}_passed': 'yes',
        })
        self.assertEqual(response.status_code, 200)
        visit = RoundVisit.objects.first()
        self.assertIsNone(visit.latitude)
