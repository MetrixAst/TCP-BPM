from django.test import TestCase, Client
from django.urls import reverse
from account.models import UserAccount, Department, Employee 
from hr.models import Company, Position
from account.role_permissions import RoleEnums, MenuItem

class HRMenuAndAccessTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="TestCo", bin_number="123456789012")
        self.dept = Department.objects.create(name="IT", company=self.company)
        
        self.admin_user = UserAccount.objects.create_user(
            username='admin_user', password='password123', role=RoleEnums.ADMINISTRATOR.value
        )
        self.staff_user = UserAccount.objects.create_user(
            username='staff_user', password='password123', role=RoleEnums.STAFF.value
        )
        self.guest_user = UserAccount.objects.create_user(
            username='guest_user', password='password123', role=RoleEnums.GUEST.value
        )
        self.hr_user = UserAccount.objects.create_user(
            username='hr_user', password='password123', role=RoleEnums.HR.value
        )

        Employee.objects.create(user=self.admin_user, department=self.dept)
        Employee.objects.create(user=self.staff_user, department=self.dept)
        Employee.objects.create(user=self.hr_user, department=self.dept)

        self.client = Client()

    def test_administrator_hr_access(self):
        self.client.login(username='admin_user', password='password123')
        
        menu = MenuItem.generate_menu(self.admin_user)
        hr_menu = next((item for item in menu if item.id == 'hr'), None)
        self.assertIsNotNone(hr_menu)
        
        submenu_titles = [sub.title for sub in hr_menu.submenu]
        expected = ['Орг. структура', 'Сотрудники', 'Компании', 'Должности', 'Командировки', 'Отпуски']
        for title in expected:
            self.assertIn(title, submenu_titles)

        response = self.client.get(reverse('hr:companies'))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(self.client.get(reverse('hr:leave_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('hr:leave_timeline_page')).status_code, 200)
        self.assertEqual(self.client.get(reverse('hr:documents_list')).status_code, 200)

    def test_staff_hr_access(self):
        self.client.login(username='staff_user', password='password123')
        
        menu = MenuItem.generate_menu(self.staff_user)
        hr_menu = next((item for item in menu if item.id == 'hr'), None)
        self.assertIsNotNone(hr_menu)
        
        submenu_titles = [sub.title for sub in hr_menu.submenu]
        self.assertIn('Личный профиль', submenu_titles)
        self.assertIn('Мои документы', submenu_titles)
        self.assertNotIn('Орг. структура', submenu_titles)
        self.assertNotIn('Сотрудники', submenu_titles)
        self.assertNotIn('Компании', submenu_titles)

        response = self.client.get(reverse('hr:org'))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse('hr:employees'))
        self.assertEqual(response.status_code, 403)

    def test_hr_role_full_hr_menu(self):
        menu = MenuItem.generate_menu(self.hr_user)
        hr_menu = next((item for item in menu if item.id == 'hr'), None)
        self.assertIsNotNone(hr_menu)

        submenu_titles = [sub.title for sub in hr_menu.submenu]
        for title in ('Компании', 'Должности', 'Журнал посещаемости', 'Кадровые документы'):
            self.assertIn(title, submenu_titles)

        self.client.login(username='hr_user', password='password123')
        self.assertEqual(self.client.get(reverse('hr:companies')).status_code, 200)
        self.assertEqual(self.client.get(reverse('hr:attendance_journal')).status_code, 200)
        self.client.logout()

    def test_staff_companies_forbidden(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('hr:companies'))
        self.assertEqual(response.status_code, 403)
        self.client.logout()

    def test_guest_hr_denied(self):
        self.client.login(username='guest_user', password='password123')
        
        menu = MenuItem.generate_menu(self.guest_user)
        hr_menu = next((item for item in menu if item.id == 'hr'), None)
        self.assertIsNone(hr_menu)

        response = self.client.get(reverse('hr:employees'))

        if response.status_code == 200:
            self.assertTrue(
                "Permission Denied" in response.content.decode() or 
                "forbidden" in response.content.decode().lower()
            )
        else:
            self.assertIn(response.status_code, [403, 302])