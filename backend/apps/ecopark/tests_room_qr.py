"""Один QR на помещение: чек-лист по должности и отчёт руководителю."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import Department, Employee, UserAccount
from ecopark.models import (
    ChecklistItem, ChecklistTemplate, Defect, RoundPoint, RoundPointChecklist, RoundVisit,
)
from hr.models import Company, Position


class RoomQRBase(TestCase):
    def setUp(self):
        company = Company.objects.create(name='RoomQR Co', bin_number='909090909090')
        self.ops = Department.objects.create(name='Эксплуатация', company=company)
        self.cleaning = Department.objects.create(name='Клининг', company=company)
        self.plumber_pos = Position.objects.create(title='Сантехник', department=self.ops)
        self.electric_pos = Position.objects.create(title='Электрик', department=self.ops)

        self.admin = UserAccount.objects.create_user(username='roomqr_admin', password='p', role='administrator')
        self.plumber = self._employee('roomqr_plumber', self.ops, self.plumber_pos)
        self.electrician = self._employee('roomqr_electric', self.ops, self.electric_pos)
        self.cleaner = self._employee('roomqr_cleaner', self.cleaning)
        self.ops_head = self._employee('roomqr_ops_head', self.ops, head=True)
        self.cleaning_head = self._employee('roomqr_clean_head', self.cleaning, head=True)

        self.plumbing = self._checklist('Сантехника венткамеры', ['Нет протечек'])
        self.electric = self._checklist('Электрика венткамеры', ['Щиток закрыт', 'Освещение работает'])
        self.cleaning_cl = self._checklist('Уборка венткамеры', ['Пол чистый'])

        self.point = RoundPoint.objects.create(name='Венткамера 1', created_by=self.admin)
        RoundPointChecklist.objects.create(point=self.point, checklist=self.plumbing, position=self.plumber_pos,
                                           department=self.ops)
        RoundPointChecklist.objects.create(point=self.point, checklist=self.electric, position=self.electric_pos,
                                           department=self.ops)
        RoundPointChecklist.objects.create(point=self.point, checklist=self.cleaning_cl, department=self.cleaning)

    def _employee(self, username, department, position=None, head=False):
        user = UserAccount.objects.create_user(username=username, password='p', role='staff')
        return Employee.objects.create(user=user, department=department, position=position, head=head,
                                       status='active')

    def _checklist(self, name, items):
        template = ChecklistTemplate.objects.create(name=name, created_by=self.admin)
        for order, text in enumerate(items):
            ChecklistItem.objects.create(template=template, order=order, text=text, requires_photo_on_fail=False)
        return template


class ChecklistForEmployeeTest(RoomQRBase):
    def test_each_position_gets_its_own_checklist(self):
        self.assertEqual(self.point.checklists_for(self.plumber), [self.plumbing])
        self.assertEqual(self.point.checklists_for(self.electrician), [self.electric])
        self.assertEqual(self.point.checklists_for(self.cleaner), [self.cleaning_cl])

    def test_employee_without_matching_rule_gets_nothing(self):
        self.assertEqual(self.point.checklists_for(self.ops_head), [])

    def test_department_rule_covers_subdepartments(self):
        sub = Department.objects.create(name='Клининг — смена 2', company=self.cleaning.company, parent=self.cleaning)
        employee = self._employee('roomqr_sub', sub)
        self.assertEqual(self.point.checklists_for(employee), [self.cleaning_cl])

    def test_main_checklist_still_works_next_to_rules(self):
        main = self._checklist('Общий осмотр', ['Дверь закрыта'])
        self.point.checklist = main
        self.point.responsible_department = self.ops
        self.point.save()
        self.assertEqual(self.point.checklists_for(self.plumber), [main, self.plumbing])
        self.assertEqual(self.point.checklists_for(self.cleaner), [self.cleaning_cl])

    def test_point_without_rules_keeps_old_behaviour(self):
        point = RoundPoint.objects.create(name='Старая точка', checklist=self.plumbing, created_by=self.admin)
        self.assertEqual(point.checklists_for(self.cleaner), [self.plumbing])
        point.responsible_department = self.ops
        point.save()
        self.assertEqual(point.checklists_for(self.cleaner), [])

    def test_inactive_checklist_is_not_offered(self):
        self.plumbing.is_active = False
        self.plumbing.save()
        self.assertEqual(self.point.checklists_for(self.plumber), [])

    def test_overdue_is_counted_per_checklist(self):
        RoundPoint.objects.filter(pk=self.point.pk).update(created_at=timezone.now() - timedelta(days=3))
        self.point.refresh_from_db()
        for employee, checklist in ((self.plumber, self.plumbing), (self.cleaner, self.cleaning_cl)):
            RoundVisit.objects.create(point=self.point, employee=employee, checklist=checklist)
        slots = {slot['checklist']: slot['is_overdue'] for slot in self.point.checklist_slots()}
        self.assertEqual(slots, {self.plumbing: False, self.electric: True, self.cleaning_cl: False})
        self.assertTrue(self.point.is_overdue)


class MobileRoomQRTest(RoomQRBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _resolve(self, employee_or_user):
        user = getattr(employee_or_user, 'user', employee_or_user)
        self.client.force_authenticate(user=user)
        return self.client.get(f'/api/v1/mobile/rounds/resolve/?qr={self.point.uuid}').data

    def test_resolve_returns_employee_checklist(self):
        data = self._resolve(self.electrician)
        self.assertTrue(data['can_visit'])
        self.assertFalse(data['can_view_report'])
        self.assertEqual(data['checklists'], [{'id': self.electric.pk, 'name': self.electric.name}])

    def test_resolve_for_department_head_offers_report(self):
        data = self._resolve(self.ops_head)
        self.assertFalse(data['can_visit'])
        self.assertTrue(data['can_view_report'])

    def test_resolve_for_admin_offers_report(self):
        self.assertTrue(self._resolve(self.admin)['can_view_report'])

    def test_detail_returns_items_of_employee_checklist(self):
        self.client.force_authenticate(user=self.electrician.user)
        data = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/').data
        self.assertEqual(data['checklist_id'], self.electric.pk)
        self.assertEqual([i['text'] for i in data['items']], ['Щиток закрыт', 'Освещение работает'])

    def test_employee_with_two_checklists_chooses_one(self):
        main = self._checklist('Общий осмотр', ['Дверь закрыта'])
        self.point.checklist = main
        self.point.responsible_department = self.ops
        self.point.save()
        self.client.force_authenticate(user=self.plumber.user)
        url = f'/api/v1/mobile/rounds/points/{self.point.uuid}/'

        data = self.client.get(url).data
        self.assertEqual(len(data['checklists']), 2)
        data = self.client.get(url, {'checklist': self.plumbing.pk}).data
        self.assertEqual(data['checklist_id'], self.plumbing.pk)
        self.assertEqual([i['text'] for i in data['items']], ['Нет протечек'])

        # Оба чек-листа можно пройти в один день — это разные проверки.
        for checklist in (main, self.plumbing):
            r = self.client.post(f'{url}answer/', {'checklist_id': checklist.pk}, format='multipart')
            self.assertEqual(r.status_code, 201)
        self.assertEqual(
            set(RoundVisit.objects.filter(point=self.point).values_list('checklist_id', flat=True)),
            {main.pk, self.plumbing.pk},
        )

    def test_visit_saves_answers_of_employee_checklist(self):
        self.client.force_authenticate(user=self.electrician.user)
        items = list(self.electric.items.order_by('order'))
        r = self.client.post(f'/api/v1/mobile/rounds/points/{self.point.uuid}/answer/', {
            f'item_{items[0].pk}_status': 'ok',
            f'item_{items[1].pk}_status': 'fail',
            f'item_{items[1].pk}_comment': 'Лампа не горит',
        }, format='multipart')
        self.assertEqual(r.status_code, 201)
        visit = RoundVisit.objects.get(pk=r.data['visit_id'])
        self.assertEqual(visit.checklist, self.electric)
        self.assertEqual(visit.answers.count(), 2)
        self.assertEqual(Defect.objects.filter(visit=visit).count(), 1)

    def test_cannot_submit_someone_elses_checklist(self):
        self.client.force_authenticate(user=self.cleaner.user)
        r = self.client.post(f'/api/v1/mobile/rounds/points/{self.point.uuid}/answer/',
                             {'checklist_id': self.electric.pk}, format='multipart')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(RoundVisit.objects.get(pk=r.data['visit_id']).checklist, self.cleaning_cl)

    def test_head_without_checklist_cannot_mark_point(self):
        self.client.force_authenticate(user=self.ops_head.user)
        r = self.client.post(f'/api/v1/mobile/rounds/points/{self.point.uuid}/answer/', {}, format='multipart')
        self.assertEqual(r.status_code, 403)

    def test_report_for_head_shows_all_checklists_and_defects(self):
        visit = RoundVisit.objects.create(point=self.point, employee=self.plumber, checklist=self.plumbing)
        Defect.objects.create(visit=visit, point=self.point, description='Течёт кран', reported_by=self.plumber)
        self.client.force_authenticate(user=self.ops_head.user)
        r = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/report/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            [row['checklist_name'] for row in r.data['checklists']],
            ['Сантехника венткамеры', 'Электрика венткамеры', 'Уборка венткамеры'],
        )
        plumbing_row = r.data['checklists'][0]
        self.assertEqual(plumbing_row['assignee'], 'Сантехник (Эксплуатация)')
        self.assertIsNotNone(plumbing_row['last_visit_at'])
        self.assertEqual([d['description'] for d in r.data['open_defects']], ['Течёт кран'])
        self.assertEqual(r.data['recent_visits'][0]['checklist_name'], 'Сантехника венткамеры')

    def test_report_forbidden_for_regular_employee(self):
        self.client.force_authenticate(user=self.plumber.user)
        r = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/report/')
        self.assertEqual(r.status_code, 403)

    def test_company_head_sees_report_of_any_point(self):
        director = UserAccount.objects.create_user(username='roomqr_director', password='p', role='staff', head=True)
        self.assertTrue(self._resolve(director)['can_view_report'])
        r = self.client.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/report/')
        self.assertEqual(r.status_code, 200)

    def test_head_of_unrelated_department_has_no_report(self):
        other = Department.objects.create(name='Бухгалтерия', company=self.ops.company)
        head = self._employee('roomqr_other_head', other, head=True)
        self.assertFalse(self._resolve(head)['can_view_report'])


class WebRoomQRTest(RoomQRBase):
    def _scan_url(self):
        return reverse('ecopark:rounds_scan', args=[self.point.uuid])

    def test_scan_shows_employee_checklist(self):
        self.client.force_login(self.electrician.user)
        r = self.client.get(self._scan_url())
        self.assertContains(r, 'Электрика венткамеры')
        self.assertContains(r, 'Щиток закрыт')
        self.assertNotContains(r, 'Нет протечек')

    def test_scan_asks_to_choose_when_several_checklists(self):
        main = self._checklist('Общий осмотр', ['Дверь закрыта'])
        self.point.checklist = main
        self.point.responsible_department = self.ops
        self.point.save()
        self.client.force_login(self.plumber.user)
        r = self.client.get(self._scan_url())
        self.assertContains(r, 'Выберите, какой чек-лист проходите')
        self.assertNotContains(r, 'Нет протечек')
        r = self.client.get(self._scan_url(), {'checklist': self.plumbing.pk})
        self.assertContains(r, 'Нет протечек')

    def test_scan_submit_records_checklist(self):
        self.client.force_login(self.cleaner.user)
        item = self.cleaning_cl.items.get()
        r = self.client.post(self._scan_url(), {'checklist': self.cleaning_cl.pk, f'item_{item.pk}_passed': 'yes'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(RoundVisit.objects.get().checklist, self.cleaning_cl)

    def test_head_who_also_checks_point_gets_checklist_and_report_link(self):
        self.client.force_login(self.cleaning_head.user)
        r = self.client.get(self._scan_url())
        self.assertContains(r, 'Пол чистый')
        self.assertContains(r, 'Отчёт по помещению')

    def test_head_is_sent_to_report(self):
        self.client.force_login(self.ops_head.user)
        r = self.client.get(self._scan_url())
        self.assertRedirects(r, reverse('ecopark:round_point_history', args=[self.point.pk]),
                             fetch_redirect_response=False)
        r = self.client.get(reverse('ecopark:round_point_history', args=[self.point.pk]))
        self.assertContains(r, 'Уборка венткамеры')
        self.assertContains(r, 'Сантехник (Эксплуатация)')

    def test_point_form_saves_rules(self):
        self.client.force_login(self.admin)
        point = RoundPoint.objects.create(name='Комната АХО', created_by=self.admin)
        r = self.client.post(reverse('ecopark:round_point_edit', args=[point.pk]), {
            'name': 'Комната АХО',
            'check_interval_hours': '24',
            'is_active': 'on',
            'rule_id[]': ['', ''],
            'rule_department[]': ['', str(self.cleaning.pk)],
            'rule_position[]': [str(self.plumber_pos.pk), ''],
            'rule_checklist[]': [str(self.plumbing.pk), str(self.cleaning_cl.pk)],
            'rule_interval[]': ['', '8'],
        })
        self.assertEqual(r.status_code, 302)
        rules = list(point.checklist_rules.order_by('order'))
        self.assertEqual(len(rules), 2)
        # Отдел подставляется из должности.
        self.assertEqual((rules[0].position, rules[0].department), (self.plumber_pos, self.ops))
        self.assertEqual((rules[1].department, rules[1].check_interval_hours), (self.cleaning, 8))

        r = self.client.post(reverse('ecopark:round_point_edit', args=[point.pk]), {
            'name': 'Комната АХО',
            'check_interval_hours': '24',
            'is_active': 'on',
            'rule_id[]': [str(rules[0].pk), str(rules[1].pk)],
            'rule_department[]': ['', str(self.cleaning.pk)],
            'rule_position[]': [str(self.plumber_pos.pk), ''],
            'rule_checklist[]': [str(self.plumbing.pk), str(self.cleaning_cl.pk)],
            'rule_interval[]': ['', '8'],
            'rule_delete[]': [str(rules[0].pk)],
        })
        self.assertEqual(list(point.checklist_rules.all()), [rules[1]])


class SeedServiceRoundPointsTest(TestCase):
    """seed_service_round_points: одна точка на помещение, старые пары сливаются."""

    def setUp(self):
        from hr.models import Company
        company = Company.objects.create(name='Seed Co', bin_number='808080808080')
        self.cleaning = Department.objects.create(name='Клининг', company=company)
        self.ops = Department.objects.create(name='Эксплуатация', company=company)

    def _run(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('seed_service_round_points', stdout=StringIO())

    def _checklists(self, point):
        return {
            (rule.department.name, rule.checklist.name, rule.check_interval_hours)
            for rule in point.checklist_rules.select_related('department', 'checklist')
        }

    def test_fresh_database_gets_one_point_per_room(self):
        self._run()
        self.assertFalse(RoundPoint.objects.filter(name__startswith='[').exists())
        point = RoundPoint.objects.get(name='Электрощитовая')
        self.assertIsNone(point.checklist)
        self.assertEqual(self._checklists(point), {
            ('Клининг', 'Клининг — служебное помещение', 168),
            ('Эксплуатация', 'Эксплуатация — служебное помещение', 24),
        })

    def test_old_pair_of_points_is_merged_with_history(self):
        from ecopark.models import Route, RoutePoint
        cleaning_cl = ChecklistTemplate.objects.create(name='Клининг — служебное помещение')
        item = ChecklistItem.objects.create(template=cleaning_cl, order=1, text='Пол чистый, без мусора и луж')
        ops_cl = ChecklistTemplate.objects.create(name='Эксплуатация — служебное помещение')
        old_cleaning = RoundPoint.objects.create(
            name='[Клининг] Помещение АХО', checklist=cleaning_cl, responsible_department=self.cleaning)
        old_ops = RoundPoint.objects.create(
            name='[Эксплуатация] Помещение АХО', checklist=ops_cl, responsible_department=self.ops)
        user = UserAccount.objects.create_user(username='seed_cleaner', password='p', role='staff')
        cleaner = Employee.objects.create(user=user, department=self.cleaning, status='active')
        visit = RoundVisit.objects.create(point=old_cleaning, employee=cleaner, checklist=cleaning_cl)
        visit.answers.create(item=item, passed=False)
        Defect.objects.create(visit=visit, point=old_cleaning, description='Лужа', reported_by=cleaner)
        route = Route.objects.create(name='Обход АХО')
        RoutePoint.objects.create(route=route, point=old_cleaning, order=1)
        RoutePoint.objects.create(route=route, point=old_ops, order=2)

        self._run()
        self._run()  # повторный запуск ничего не дублирует

        point = RoundPoint.objects.get(name='Помещение АХО', is_active=True)
        # Общей становится точка эксплуатации: её QR уже мог быть напечатан.
        self.assertEqual(point.uuid, old_ops.uuid)
        old_cleaning.refresh_from_db()
        self.assertFalse(old_cleaning.is_active)
        self.assertEqual(list(point.visits.all()), [visit])
        self.assertEqual(point.defects.count(), 1)
        self.assertEqual(list(route.route_points.values_list('point_id', flat=True)), [point.pk])
        self.assertEqual(len(self._checklists(point)), 2)
        self.assertEqual(point.checklists_for(cleaner), [cleaning_cl])
        # Отметка клининга по-прежнему закрывает именно чек-лист клининга.
        slots = {slot['checklist'].name: slot['last_visit'] for slot in point.checklist_slots()}
        self.assertEqual(slots['Клининг — служебное помещение'], visit)
        self.assertIsNone(slots['Эксплуатация — служебное помещение'])

    def test_point_disabled_by_admin_stays_disabled(self):
        self._run()
        RoundPoint.objects.filter(name='Выход на кровлю').update(is_active=False)
        self._run()
        self.assertFalse(RoundPoint.objects.get(name='Выход на кровлю').is_active)
        self.assertEqual(RoundPoint.objects.filter(name='Выход на кровлю').count(), 1)

    def test_active_old_point_wins_over_disabled_original(self):
        original = RoundPoint.objects.create(name='Комната отдела АХО', is_active=False)
        ops_point = RoundPoint.objects.create(name='[Эксплуатация] Комната отдела АХО')
        self._run()
        ops_point.refresh_from_db()
        original.refresh_from_db()
        self.assertTrue(ops_point.is_active)
        self.assertEqual(ops_point.name, 'Комната отдела АХО')
        self.assertFalse(original.is_active)

    def test_production_room_keeps_its_point_and_qr(self):
        original = RoundPoint.objects.create(name='Комната отдела АХО', location='Служебный блок, 2 этаж')
        self._run()
        original.refresh_from_db()
        self.assertTrue(original.is_active)
        self.assertEqual(original.name, 'Комната отдела АХО')
        self.assertEqual(original.location, 'Служебный блок, 2 этаж')
        self.assertEqual(original.checklist_rules.count(), 2)
        self.assertFalse(RoundPoint.objects.filter(name__contains='Комната отдела АХО').exclude(pk=original.pk).exists())


class RoomQRJournalAndFilterTest(RoomQRBase):
    def test_journal_and_export_show_checklist(self):
        RoundVisit.objects.create(point=self.point, employee=self.electrician, checklist=self.electric)
        self.client.force_login(self.admin)
        r = self.client.get(reverse('ecopark:rounds_journal'))
        self.assertContains(r, 'Электрика венткамеры')

        import io
        import openpyxl
        r = self.client.get(reverse('ecopark:rounds_journal_export'))
        rows = list(openpyxl.load_workbook(io.BytesIO(r.content)).active.values)
        self.assertEqual(rows[0][:2], ('Точка', 'Чек-лист'))
        self.assertEqual(rows[1][:2], ('Венткамера 1', 'Электрика венткамеры'))

    def test_service_filter_finds_shared_room_point(self):
        other = RoundPoint.objects.create(name='Бухгалтерия', created_by=self.admin)
        self.client.force_login(self.admin)
        r = self.client.get(reverse('ecopark:round_points_list'), {'dept': 'cleaning'})
        self.assertContains(r, 'Венткамера 1')
        self.assertNotContains(r, other.name)
        r = self.client.get(reverse('ecopark:round_points_list'), {'dept': str(self.ops.pk)})
        self.assertContains(r, 'Венткамера 1')

class MergeServicePointsMigrationTest(TestCase):
    """Миграция 0008: дубли служб сливаются при деплое сами."""

    def setUp(self):
        from hr.models import Company
        company = Company.objects.create(name='Merge Co', bin_number='707070707070')
        self.cleaning = Department.objects.create(name='Клининг', company=company)
        self.ops = Department.objects.create(name='Эксплуатация', company=company)
        self.cleaning_cl = ChecklistTemplate.objects.create(name='Клининг — служебное помещение')
        self.ops_cl = ChecklistTemplate.objects.create(name='Эксплуатация — служебное помещение')
        user = UserAccount.objects.create_user(username='merge_cleaner', password='p', role='staff')
        self.cleaner = Employee.objects.create(user=user, department=self.cleaning, status='active')

    def _migrate(self):
        import importlib
        from django.apps import apps
        importlib.import_module('ecopark.migrations.0008_merge_service_points').merge_service_points(apps, None)

    def _pair(self, base):
        return (
            RoundPoint.objects.create(name=f'[Клининг] {base}', checklist=self.cleaning_cl,
                                      responsible_department=self.cleaning, check_interval_hours=8),
            RoundPoint.objects.create(name=f'[Эксплуатация] {base}', checklist=self.ops_cl,
                                      responsible_department=self.ops, check_interval_hours=24),
        )

    def test_pair_merges_into_original_point_with_history(self):
        from ecopark.models import Route, RoutePoint
        original = RoundPoint.objects.create(name='Комната отдела АХО')
        old_cleaning, old_ops = self._pair('Комната отдела АХО')
        visit = RoundVisit.objects.create(point=old_cleaning, employee=self.cleaner)
        Defect.objects.create(visit=visit, point=old_cleaning, description='Лужа', reported_by=self.cleaner)
        route = Route.objects.create(name='Клининг: обход')
        RoutePoint.objects.create(route=route, point=old_cleaning, order=1)

        self._migrate()

        original.refresh_from_db()
        self.assertTrue(original.is_active)
        self.assertEqual(original.name, 'Комната отдела АХО')
        for old in (old_cleaning, old_ops):
            old.refresh_from_db()
            self.assertFalse(old.is_active)
        self.assertEqual(
            {(r.department_id, r.checklist_id, r.check_interval_hours) for r in original.checklist_rules.all()},
            {(self.cleaning.pk, self.cleaning_cl.pk, 8), (self.ops.pk, self.ops_cl.pk, 24)},
        )
        visit.refresh_from_db()
        self.assertEqual((visit.point, visit.checklist), (original, self.cleaning_cl))
        self.assertEqual(original.defects.count(), 1)
        self.assertEqual(list(route.route_points.values_list('point_id', flat=True)), [original.pk])
        self.assertEqual(original.checklists_for(self.cleaner), [self.cleaning_cl])

    def test_pair_without_original_keeps_ops_qr_and_drops_prefix(self):
        old_cleaning, old_ops = self._pair('Электрощитовая')
        self._migrate()
        old_ops.refresh_from_db()
        self.assertEqual(old_ops.name, 'Электрощитовая')
        self.assertTrue(old_ops.is_active)
        self.assertIsNone(old_ops.checklist)
        self.assertEqual(old_ops.checklist_rules.count(), 2)

    def test_different_quotes_are_the_same_room(self):
        original = RoundPoint.objects.create(name='Комната "Слив 1"')
        self._pair('Комната «Слив 1»')
        self._migrate()
        self.assertEqual(RoundPoint.objects.filter(is_active=True).get().pk, original.pk)

    def test_other_points_are_untouched(self):
        point = RoundPoint.objects.create(name='Венткамера', checklist=self.ops_cl, responsible_department=self.ops)
        self._migrate()
        point.refresh_from_db()
        self.assertEqual((point.checklist, point.responsible_department), (self.ops_cl, self.ops))
        self.assertFalse(point.checklist_rules.exists())

    def test_running_twice_changes_nothing(self):
        self._pair('Выход на кровлю')
        self._migrate()
        self._migrate()
        self.assertEqual(RoundPoint.objects.filter(is_active=True).count(), 1)
        self.assertEqual(RoundPoint.objects.get(is_active=True).checklist_rules.count(), 2)

class DefectsByChecklistTest(RoomQRBase):
    def setUp(self):
        super().setUp()
        electric_visit = RoundVisit.objects.create(point=self.point, employee=self.electrician, checklist=self.electric)
        plumbing_visit = RoundVisit.objects.create(point=self.point, employee=self.plumber, checklist=self.plumbing)
        Defect.objects.create(visit=electric_visit, point=self.point, description='Щиток не закрывается',
                              reported_by=self.electrician)
        Defect.objects.create(visit=plumbing_visit, point=self.point, description='Течёт кран',
                              reported_by=self.plumber)

    def test_defects_list_shows_and_filters_by_checklist(self):
        self.client.force_login(self.admin)
        url = reverse('ecopark:defects_list')
        r = self.client.get(url)
        self.assertContains(r, 'Электрика венткамеры')
        self.assertContains(r, 'Сантехника венткамеры')
        r = self.client.get(url, {'checklist': self.electric.pk})
        self.assertContains(r, 'Щиток не закрывается')
        self.assertNotContains(r, 'Течёт кран')

    def test_report_tells_which_checklist_defect_belongs_to(self):
        api = APIClient()
        api.force_authenticate(user=self.ops_head.user)
        r = api.get(f'/api/v1/mobile/rounds/points/{self.point.uuid}/report/')
        self.assertEqual(
            {d['description']: d['checklist_name'] for d in r.data['open_defects']},
            {'Щиток не закрывается': 'Электрика венткамеры', 'Течёт кран': 'Сантехника венткамеры'},
        )