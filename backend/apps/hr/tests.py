from unittest.mock import Mock, patch
import requests

from django.db import IntegrityError
from django.test import TestCase, override_settings

from hr.enbek_client import (
    EnbekClient,
    EnbekClientError,
    AuthenticationError,
    ConnectionError,
)
from account.models import UserAccount, Department, Employee
from hr.models import Company, Vacation, SickLeave, EmploymentContract
from hr.services import EnbekSyncService
from hr.tasks import sync_enbek_data
from account.role_permissions import MenuItem


@override_settings(
    ENBEK_BASE_URL='http://testserver/api/enbek',
    ENBEK_USERNAME='test_user',
    ENBEK_PASSWORD='test_password',
    ENBEK_TIMEOUT=5,
)
class EnbekClientTestCase(TestCase):
    def setUp(self):
        self.client = EnbekClient()

    def test_authenticate_with_valid_credentials_returns_token(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(self.client.session, 'post', return_value=mock_response) as mock_post:
            token = self.client.authenticate()

        self.assertEqual(token, "mock_token_123")
        self.assertEqual(self.client.token, "mock_token_123")

        mock_post.assert_called_once_with(
            'http://testserver/api/enbek/auth/login/',
            json={
                'username': 'test_user',
                'password': 'test_password',
            },
            headers={
                'Content-Type': 'application/json',
                'Host': 'localhost',
            },
            timeout=5,
        )

    def test_authenticate_with_invalid_credentials_raises_authentication_error(self):
        mock_response = Mock()
        mock_response.status_code = 401

        with patch.object(self.client.session, 'post', return_value=mock_response):
            with self.assertRaises(AuthenticationError):
                self.client.authenticate()

    def test_get_vacations_returns_list(self):
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        vacations_response = Mock()
        vacations_response.status_code = 200
        vacations_response.json.return_value = [
            {
                "id": 1,
                "employee_name": "Иван Иванов",
                "type": "annual",
                "start_date": "2024-06-01",
                "end_date": "2024-06-14",
                "status": "approved",
            }
        ]

        with patch.object(self.client.session, 'post', return_value=auth_response):
            with patch.object(self.client.session, 'get', return_value=vacations_response) as mock_get:
                vacations = self.client.get_vacations()

        self.assertIsInstance(vacations, list)
        self.assertEqual(len(vacations), 1)
        self.assertEqual(vacations[0]['id'], 1)
        self.assertEqual(vacations[0]['employee_name'], 'Иван Иванов')
        self.assertEqual(vacations[0]['type'], 'annual')

        mock_get.assert_called_once_with(
            'http://testserver/api/enbek/leaves/',
            headers={
                'Content-Type': 'application/json',
                'Host': 'localhost',
                'Authorization': 'Bearer mock_token_123',
            },
            timeout=5,
        )

    def test_get_sick_leaves_empty_response_returns_empty_list(self):
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        sick_leaves_response = Mock()
        sick_leaves_response.status_code = 200
        sick_leaves_response.json.return_value = []

        with patch.object(self.client.session, 'post', return_value=auth_response):
            with patch.object(self.client.session, 'get', return_value=sick_leaves_response):
                sick_leaves = self.client.get_sick_leaves()

        self.assertIsInstance(sick_leaves, list)
        self.assertEqual(sick_leaves, [])

    def test_timeout_when_api_unavailable_raises_connection_error_with_retry_case(self):
        with patch.object(
            self.client.session,
            'post',
            side_effect=requests.exceptions.Timeout
        ):
            with self.assertRaises(ConnectionError):
                self.client.authenticate()

    def test_handle_response_with_invalid_json_raises_enbek_client_error(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError('Invalid JSON')

        with self.assertRaises(EnbekClientError):
            self.client._handle_response(mock_response)

    def test_authenticate_without_token_in_response_raises_authentication_error(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(self.client.session, 'post', return_value=mock_response):
            with self.assertRaises(AuthenticationError):
                self.client.authenticate()

    def test_server_error_raises_connection_error(self):
        mock_response = Mock()
        mock_response.status_code = 500

        with self.assertRaises(ConnectionError):
            self.client._handle_response(mock_response)

    def test_client_error_raises_enbek_client_error(self):
        mock_response = Mock()
        mock_response.status_code = 404

        with self.assertRaises(EnbekClientError):
            self.client._handle_response(mock_response)

class EnbekModelsTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Test Company',
            bin_number='123456789012',
        )

        self.department = Department.objects.create(
            name='IT Department',
            company=self.company,
        )

        self.user = UserAccount.objects.create_user(
            username='employee1',
            password='testpass123',
            role='staff',
        )

        self.employee = Employee.objects.create(
            user=self.user,
            department=self.department,
            iin='123456789012',
            status='active',
        )

    def test_create_vacation_with_unique_enbek_id(self):
        vacation = Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        self.assertIsNotNone(vacation.id)
        self.assertEqual(vacation.enbek_id, 'vac_1')
        self.assertEqual(vacation.employee, self.employee)

    def test_duplicate_vacation_enbek_id_raises_integrity_error(self):
        Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        with self.assertRaises(IntegrityError):
            Vacation.objects.create(
                employee=self.employee,
                type='annual',
                start_date='2024-07-01',
                end_date='2024-07-10',
                status='approved',
                enbek_id='vac_1',
            )

    def test_sick_leave_is_linked_to_employee(self):
        sick_leave = SickLeave.objects.create(
            employee=self.employee,
            start_date='2024-03-01',
            end_date='2024-03-05',
            document_number='SL-001',
            enbek_id='sick_1',
        )

        self.assertEqual(sick_leave.employee, self.employee)
        self.assertIn(sick_leave, self.employee.sick_leaves.all())

    def test_employment_contract_saved_with_type_and_status(self):
        contract = EmploymentContract.objects.create(
            employee=self.employee,
            number='CTR-001',
            date='2024-01-10',
            type='labor',
            status='active',
            enbek_id='contract_1',
        )

        self.assertEqual(contract.number, 'CTR-001')
        self.assertEqual(contract.type, 'labor')
        self.assertEqual(contract.status, 'active')
        self.assertEqual(contract.enbek_id, 'contract_1')
        self.assertEqual(contract.employee, self.employee)

    def test_delete_employee_sets_null_in_related_enbek_models(self):
        vacation = Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        sick_leave = SickLeave.objects.create(
            employee=self.employee,
            start_date='2024-03-01',
            end_date='2024-03-05',
            document_number='SL-001',
            enbek_id='sick_1',
        )

        contract = EmploymentContract.objects.create(
            employee=self.employee,
            number='CTR-001',
            date='2024-01-10',
            type='labor',
            status='active',
            enbek_id='contract_1',
        )

        self.employee.delete()

        vacation.refresh_from_db()
        sick_leave.refresh_from_db()
        contract.refresh_from_db()

        self.assertIsNone(vacation.employee)
        self.assertIsNone(sick_leave.employee)
        self.assertIsNone(contract.employee)

class EnbekSyncServiceTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Test Company',
            bin_number='123456789012',
        )

        self.department = Department.objects.create(
            name='IT Department Sync',
            company=self.company,
        )

        self.user = UserAccount.objects.create_user(
            username='sync_employee',
            password='testpass123',
            role='staff',
        )

        self.employee = Employee.objects.create(
            user=self.user,
            department=self.department,
            iin='111111111111',
            status='active',
        )

        self.service = EnbekSyncService()

    @patch('hr.services.logger')
    @patch('hr.services.EnbekClient.get_employment_contracts')
    @patch('hr.services.EnbekClient.get_sick_leaves')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_with_new_data_creates_records(
        self,
        mock_get_vacations,
        mock_get_sick_leaves,
        mock_get_contracts,
        mock_logger
    ):
        mock_get_vacations.return_value = [
            {
                'id': 'vac_1',
                'iin': '111111111111',
                'type': 'annual',
                'start_date': '2024-06-01',
                'end_date': '2024-06-14',
                'status': 'approved',
            }
        ]
        mock_get_sick_leaves.return_value = [
            {
                'id': 'sick_1',
                'iin': '111111111111',
                'start_date': '2024-03-01',
                'end_date': '2024-03-05',
                'document_number': 'SL-001',
            }
        ]
        mock_get_contracts.return_value = [
            {
                'id': 'contract_1',
                'iin': '111111111111',
                'number': 'CTR-001',
                'date': '2024-01-10',
                'type': 'labor',
                'status': 'active',
            }
        ]

        result = self.service.sync_all()

        self.assertEqual(result['created'], 3)
        self.assertEqual(result['updated'], 0)

        self.assertEqual(Vacation.objects.count(), 1)
        self.assertEqual(SickLeave.objects.count(), 1)
        self.assertEqual(EmploymentContract.objects.count(), 1)

        vacation = Vacation.objects.get(enbek_id='vac_1')
        sick_leave = SickLeave.objects.get(enbek_id='sick_1')
        contract = EmploymentContract.objects.get(enbek_id='contract_1')

        self.assertEqual(vacation.employee, self.employee)
        self.assertEqual(sick_leave.employee, self.employee)
        self.assertEqual(contract.employee, self.employee)

        mock_logger.info.assert_any_call("sync_started")
        mock_logger.info.assert_any_call(
            "sync_completed",
            extra={
                "created_count": 3,
                "updated_count": 0,
                "vacations_count": 1,
                "sick_leaves_count": 1,
                "employment_contracts_count": 1,
            }
        )

    @patch('hr.services.EnbekClient.get_employment_contracts')
    @patch('hr.services.EnbekClient.get_sick_leaves')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_with_existing_data_updates_records(
        self,
        mock_get_vacations,
        mock_get_sick_leaves,
        mock_get_contracts
    ):
        Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )
        SickLeave.objects.create(
            employee=self.employee,
            start_date='2024-03-01',
            end_date='2024-03-05',
            document_number='SL-001',
            enbek_id='sick_1',
        )
        EmploymentContract.objects.create(
            employee=self.employee,
            number='CTR-001',
            date='2024-01-10',
            type='labor',
            status='active',
            enbek_id='contract_1',
        )

        mock_get_vacations.return_value = [
            {
                'id': 'vac_1',
                'iin': '111111111111',
                'type': 'study',
                'start_date': '2024-07-01',
                'end_date': '2024-07-10',
                'status': 'changed',
            }
        ]
        mock_get_sick_leaves.return_value = [
            {
                'id': 'sick_1',
                'iin': '111111111111',
                'start_date': '2024-03-02',
                'end_date': '2024-03-06',
                'document_number': 'SL-002',
            }
        ]
        mock_get_contracts.return_value = [
            {
                'id': 'contract_1',
                'iin': '111111111111',
                'number': 'CTR-999',
                'date': '2024-02-15',
                'type': 'updated_type',
                'status': 'inactive',
            }
        ]

        result = self.service.sync_all()

        self.assertEqual(result['created'], 0)
        self.assertEqual(result['updated'], 3)

        self.assertEqual(Vacation.objects.count(), 1)
        self.assertEqual(SickLeave.objects.count(), 1)
        self.assertEqual(EmploymentContract.objects.count(), 1)

        vacation = Vacation.objects.get(enbek_id='vac_1')
        sick_leave = SickLeave.objects.get(enbek_id='sick_1')
        contract = EmploymentContract.objects.get(enbek_id='contract_1')

        self.assertEqual(vacation.type, 'study')
        self.assertEqual(str(vacation.start_date), '2024-07-01')
        self.assertEqual(vacation.status, 'changed')

        self.assertEqual(str(sick_leave.start_date), '2024-03-02')
        self.assertEqual(str(sick_leave.end_date), '2024-03-06')
        self.assertEqual(sick_leave.document_number, 'SL-002')

        self.assertEqual(contract.number, 'CTR-999')
        self.assertEqual(str(contract.date), '2024-02-15')
        self.assertEqual(contract.type, 'updated_type')
        self.assertEqual(contract.status, 'inactive')

    @patch('hr.services.logger')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_on_api_error_logs_error_and_existing_data_not_changed(
        self,
        mock_get_vacations,
        mock_logger
    ):
        vacation = Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        mock_get_vacations.side_effect = Exception('API is down')

        with self.assertRaises(Exception):
            self.service.sync_all()

        vacation.refresh_from_db()
        self.assertEqual(vacation.type, 'annual')
        self.assertEqual(vacation.status, 'approved')
        self.assertEqual(Vacation.objects.count(), 1)

        mock_logger.info.assert_any_call("sync_started")
        mock_logger.exception.assert_called_once_with("sync_error")

    @patch('hr.services.logger')
    @patch('hr.services.EnbekClient.get_employment_contracts')
    @patch('hr.services.EnbekClient.get_sick_leaves')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_with_empty_response_changes_nothing(
        self,
        mock_get_vacations,
        mock_get_sick_leaves,
        mock_get_contracts,
        mock_logger
    ):
        Vacation.objects.create(
            employee=self.employee,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )

        mock_get_vacations.return_value = []
        mock_get_sick_leaves.return_value = []
        mock_get_contracts.return_value = []

        result = self.service.sync_all()

        self.assertEqual(result['created'], 0)
        self.assertEqual(result['updated'], 0)

        self.assertEqual(Vacation.objects.count(), 1)
        self.assertEqual(SickLeave.objects.count(), 0)
        self.assertEqual(EmploymentContract.objects.count(), 0)

        mock_logger.info.assert_any_call("sync_started")
        mock_logger.info.assert_any_call(
            "sync_completed",
            extra={
                "created_count": 0,
                "updated_count": 0,
                "vacations_count": 0,
                "sick_leaves_count": 0,
                "employment_contracts_count": 0,
            }
        )   

    @patch('hr.services.EnbekClient.get_employment_contracts')
    @patch('hr.services.EnbekClient.get_sick_leaves')
    @patch('hr.services.EnbekClient.get_vacations')
    def test_sync_does_not_create_duplicates_for_same_enbek_id(
        self,
        mock_get_vacations,
        mock_get_sick_leaves,
        mock_get_contracts
    ):
        mock_get_vacations.return_value = [
            {
                'id': 'vac_1',
                'iin': '111111111111',
                'type': 'annual',
                'start_date': '2024-06-01',
                'end_date': '2024-06-14',
                'status': 'approved',
            }
        ]
        mock_get_sick_leaves.return_value = []
        mock_get_contracts.return_value = []

        first_result = self.service.sync_all()
        second_result = self.service.sync_all()

        self.assertEqual(first_result['created'], 1)
        self.assertEqual(first_result['updated'], 0)

        self.assertEqual(second_result['created'], 0)
        self.assertEqual(second_result['updated'], 1)

        self.assertEqual(Vacation.objects.filter(enbek_id='vac_1').count(), 1)

class EnbekCeleryTaskTestCase(TestCase):

    @patch('hr.tasks.EnbekSyncService')
    def test_task_calls_sync_service_and_returns_result(self, mock_service_class):
        mock_service = mock_service_class.return_value
        mock_service.sync_all.return_value = {
            "created": 2,
            "updated": 1,
        }

        result = sync_enbek_data()

        self.assertEqual(result, {
            "created": 2,
            "updated": 1,
        })

        mock_service.sync_all.assert_called_once()

    @patch('hr.tasks.logger')
    @patch('hr.tasks.EnbekSyncService')
    def test_task_logs_error_and_raises_exception(self, mock_service_class, mock_logger):
        mock_service = mock_service_class.return_value
        mock_service.sync_all.side_effect = Exception("API error")

        with self.assertRaises(Exception):
            sync_enbek_data()

        mock_logger.exception.assert_called_once_with("celery_sync_error")

    @patch('hr.tasks.cache')
    @patch('hr.tasks.EnbekSyncService')
    def test_task_skips_when_locked(self, mock_service_class, mock_cache):
        mock_cache.get.return_value = True  # lock уже есть

        result = sync_enbek_data()

        self.assertEqual(result, {"status": "skipped"})
        mock_service_class.assert_not_called()

class EnbekViewsTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='View Test Company',
            bin_number='999999999999',
        )

        self.department = Department.objects.create(
            name='HR View Department',
            company=self.company,
        )

        self.admin_user = UserAccount.objects.create_user(
            username='hr_admin',
            password='testpass123',
            role='administrator',
        )

        self.employee_user_1 = UserAccount.objects.create_user(
            username='emp1',
            password='testpass123',
            role='staff',
            first_name='Ivan',
        )

        self.employee_user_2 = UserAccount.objects.create_user(
            username='emp2',
            password='testpass123',
            role='staff',
            first_name='Petr',
        )

        self.employee_1 = Employee.objects.create(
            user=self.employee_user_1,
            department=self.department,
            iin='100000000001',
            status='active',
        )

        self.employee_2 = Employee.objects.create(
            user=self.employee_user_2,
            department=self.department,
            iin='100000000002',
            status='active',
        )

        Vacation.objects.create(
            employee=self.employee_1,
            type='annual',
            start_date='2024-06-01',
            end_date='2024-06-14',
            status='approved',
            enbek_id='vac_1',
        )
        Vacation.objects.create(
            employee=self.employee_2,
            type='study',
            start_date='2024-07-01',
            end_date='2024-07-10',
            status='approved',
            enbek_id='vac_2',
        )

        SickLeave.objects.create(
            employee=self.employee_1,
            start_date='2024-03-01',
            end_date='2024-03-05',
            document_number='SL-001',
            enbek_id='sick_1',
        )

        EmploymentContract.objects.create(
            employee=self.employee_1,
            number='CTR-001',
            date='2024-01-10',
            type='labor',
            status='active',
            enbek_id='contract_1',
        )

        self.client.force_login(self.admin_user)

    def test_get_hr_vacations_returns_200_and_list(self):
        response = self.client.get('/hr/vacations/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Отпуска (Enbek)')
        self.assertContains(response, 'vac_1')
        self.assertContains(response, 'vac_2')

    def test_get_hr_sick_leaves_returns_200_and_list(self):
        response = self.client.get('/hr/sick-leaves/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Больничные (Enbek)')
        self.assertContains(response, 'sick_1')

    def test_get_hr_contracts_returns_200_and_list(self):
        response = self.client.get('/hr/contracts/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Договоры (Enbek)')
        self.assertContains(response, 'contract_1')

    def test_filter_by_employee_returns_only_employee_data(self):
        response = self.client.get(f'/hr/vacations/?employee={self.employee_1.id}')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'vac_1')
        self.assertNotContains(response, 'vac_2')

    def test_views_are_read_only(self):
        response = self.client.get('/hr/vacations/')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Редактировать')
        self.assertNotContains(response, 'Удалить')

    def test_hr_menu_contains_new_enbek_items(self):
        menu = MenuItem.generate_menu(self.admin_user)

        hr_item = next(item for item in menu if item.id == 'hr')
        submenu_titles = [item.title for item in hr_item.submenu]

        self.assertIn('Отпуска (Enbek)', submenu_titles)
        self.assertIn('Больничные (Enbek)', submenu_titles)
        self.assertIn('Договоры (Enbek)', submenu_titles)