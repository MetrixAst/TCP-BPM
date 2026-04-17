from django.test import TestCase, RequestFactory
from account.models import UserAccount, Employee, Department
from hr.models import Position
from hr.utils import OrgChart

class OrgChartTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.chart = OrgChart()
        
        # 1. Структура
        self.root_dept = Department.objects.create(name="Head Office", parent=None)
        self.sub_dept = Department.objects.create(name="IT Dept", parent=self.root_dept)
        
        # 2. Должность
        self.pos = Position.objects.create(title="Manager", department=self.root_dept)
        
        # 3. Юзеры
        self.user_admin = UserAccount.objects.create_user(username='admin_user', password='123', role='administrator')
        self.emp_head = Employee.objects.create(
            user=self.user_admin, 
            department=self.root_dept, 
            position=self.pos, 
            status='active'
        )
        
        self.user_staff = UserAccount.objects.create_user(username='staff_user', password='123', role='staff')
        self.emp_staff = Employee.objects.create(
            user=self.user_staff, 
            department=self.sub_dept, 
            position=self.pos, 
            status='active'
        )

    def test_empty_db_returns_only_header(self):
        Department.objects.all().delete()
        request = self.factory.get('/')
        request.user = self.user_admin  # ДОБАВЛЯЕМ ЮЗЕРА
        data = self.chart.get_data(request)
        self.assertEqual(len(data), 1)

    def test_hierarchy_and_data_integrity(self):
        request = self.factory.get('/')
        request.user = self.user_admin  # ДОБАВЛЯЕМ ЮЗЕРА
        data = self.chart.get_data(request)
        
        ids = [row[8] for row in data]
        self.assertIn(f"dept_{self.root_dept.id}", ids)
        
        it_dept_row = next(row for row in data if row[8] == f"dept_{self.sub_dept.id}")
        self.assertEqual(it_dept_row[9], f"dept_{self.root_dept.id}")

    def test_no_avatar_uses_default(self):
        request = self.factory.get('/')
        request.user = self.user_admin  # ДОБАВЛЯЕМ ЮЗЕРА
        data = self.chart.get_data(request)
        
        image_urls = [row[1] for row in data[1:]]
        for url in image_urls:
            self.assertEqual(url, OrgChart.DEFAULT_IMAGE)

    def test_dismissed_employee_excluded(self):
        self.emp_staff.status = 'dismissed'
        self.emp_staff.save()
        
        request = self.factory.get('/')
        request.user = self.user_admin  # ДОБАВЛЯЕМ ЮЗЕРА
        data = self.chart.get_data(request)
        
        names = [row[0] for row in data]
        self.assertNotIn(str(self.emp_staff), names)