from django.test import TestCase

from account.forms import EmployeeForm, validate_iin_logic
from account.models import Employee, Department, UserAccount
from hr.models import Company
from hr.serializers import EmployeeSerializer


def make_department():
    company = Company.objects.create(name='IIN Test Co', bin_number='999111222333')
    return Department.objects.create(name='IIN Test Dept', company=company)


class ValidateIinLogicTest(TestCase):
    """
    Пустой ИИН должен нормализоваться к None, а не оставаться ''. iin —
    unique=True, и в отличие от NULL пустая строка ЯВЛЯЕТСЯ значением для
    проверки уникальности: два сотрудника с iin='' конфликтуют, а два
    сотрудника с iin=None — нет (обычное поведение unique+null в Django/SQL).
    """

    def test_empty_string_normalizes_to_none(self):
        self.assertIsNone(validate_iin_logic(''))

    def test_none_stays_none(self):
        self.assertIsNone(validate_iin_logic(None))

    def test_valid_iin_passes_through(self):
        self.assertEqual(validate_iin_logic('123456789012'), '123456789012')


class EmployeeFormIinTest(TestCase):

    def setUp(self):
        self.dept = make_department()

    def _form_data(self, iin=''):
        return {
            'department': self.dept.pk,
            'status': 'active',
            'iin': iin,
            'phone': '',
            'personal_email': '',
        }

    def test_form_with_empty_iin_is_valid(self):
        form = EmployeeForm(data=self._form_data(iin=''))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['iin'])

    def test_two_employees_without_iin_can_both_be_saved(self):
        user1 = UserAccount.objects.create_user(username='iin_test_1', password='pass', role='staff')
        user2 = UserAccount.objects.create_user(username='iin_test_2', password='pass', role='staff')

        form1 = EmployeeForm(data=self._form_data(iin=''))
        self.assertTrue(form1.is_valid(), form1.errors)
        emp1 = form1.save(commit=False)
        emp1.user = user1
        emp1.save()

        form2 = EmployeeForm(data=self._form_data(iin=''))
        self.assertTrue(form2.is_valid(), form2.errors)
        emp2 = form2.save(commit=False)
        emp2.user = user2
        emp2.save()  # раньше падало: "Сотрудник с ИИН  уже существует."

        self.assertIsNone(emp1.iin)
        self.assertIsNone(emp2.iin)


class EmployeeSerializerIinTest(TestCase):

    def setUp(self):
        self.dept = make_department()

    def test_validate_iin_empty_returns_none(self):
        serializer = EmployeeSerializer()
        self.assertIsNone(serializer.validate_iin(''))

    def test_two_employees_without_iin_via_serializer(self):
        user1 = UserAccount.objects.create_user(username='iin_api_1', password='pass', role='staff')
        user2 = UserAccount.objects.create_user(username='iin_api_2', password='pass', role='staff')

        for user in (user1, user2):
            serializer = EmployeeSerializer(data={
                'user': user.pk,
                'department': self.dept.pk,
                'status': 'active',
                'iin': '',
            })
            self.assertTrue(serializer.is_valid(), serializer.errors)
            serializer.save()  # раньше второй вызов падал на уникальности ИИН

        self.assertEqual(Employee.objects.filter(user__in=[user1, user2], iin__isnull=True).count(), 2)
