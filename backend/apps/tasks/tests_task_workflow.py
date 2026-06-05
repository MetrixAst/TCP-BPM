from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from account.models import UserAccount, AccessScope
from account.role_permissions import RoleEnums
from onec.models import Counterparty, CounterpartyType
from tasks.models import Task, TaskChecklistItem, TaskLineItem
from tasks.enums import TaskStatusEnum


class TaskWorkflowExtendedTest(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            username='taskuser',
            email='tu@test.kz',
            password='pass',
            role=RoleEnums.ADMINISTRATOR.value,
        )
        self.task = Task.objects.create(
            author=self.user,
            executor=self.user,
            title='Extended',
            deadline=date.today() + timedelta(days=1),
            status=TaskStatusEnum.CREATED.value[0],
        )

    def test_checklist_add_and_toggle(self):
        self.client.login(username=self.user.username, password='pass')
        add_url = reverse('tasks:checklist_add', args=[self.task.pk])
        r = self.client.post(add_url, {'title': 'Step 1'})
        self.assertEqual(r.status_code, 200)
        item = TaskChecklistItem.objects.get(task=self.task)
        toggle_url = reverse('tasks:checklist_toggle', args=[self.task.pk, item.pk])
        r2 = self.client.post(toggle_url)
        self.assertEqual(r2.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_done)

    def test_line_item_add(self):
        self.client.login(username=self.user.username, password='pass')
        url = reverse('tasks:line_item_add', args=[self.task.pk])
        r = self.client.post(url, {
            'name': 'Cable',
            'quantity': '2',
            'price': '100',
            'unit': 'шт',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(TaskLineItem.objects.filter(task=self.task).count(), 1)

    def test_counterparty_with_acl(self):
        scope = AccessScope.objects.create(name='cp-scope', is_global=True)
        cp_type = CounterpartyType.objects.create(
            name='Partners',
            code='partners',
            access_scope=scope,
        )
        cp = Counterparty.objects.create(
            id_1c='cp-test-1',
            full_name='Partner LLC',
            short_name='Partner LLC',
            bin_number='123456789012',
            counterparty_type=cp_type,
        )
        self.client.login(username=self.user.username, password='pass')
        url = reverse('tasks:task_counterparty', args=[self.task.pk])
        r = self.client.post(url, {'counterparty_id': cp.pk})
        self.assertEqual(r.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.counterparty_id, cp.pk)
