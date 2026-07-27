import json
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.urls import reverse

from account.models import UserAccount

from .models import ESignerSigning
from .services import handle_webhook


class ESignerWebhookViewTests(TestCase):
    @override_settings(ESIGNER_WEBHOOK_SECRET='webhook-secret')
    def test_rejects_request_without_signature(self):
        response = self.client.post(
            reverse('esigner:webhook'),
            data=json.dumps({'status': 'COMPLETED', 'document_id': 'doc-1'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(ESIGNER_WEBHOOK_SECRET='webhook-secret')
    def test_accepts_bearer_secret(self):
        response = self.client.post(
            reverse('esigner:webhook'),
            data=json.dumps({'status': 'COMPLETED', 'document_id': 'unknown'}),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer webhook-secret',
        )
        self.assertEqual(response.status_code, 200)


class ESignerWebhookServiceTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.user = UserAccount.objects.create_user(
            username='esigner-test',
            password='test',
        )
        self.signing = ESignerSigning.objects.create(
            content_type=ContentType.objects.get_for_model(self.user),
            object_id=self.user.pk,
            esigner_document_id='document-1',
            esigner_folder_id='folder-1',
            status=ESignerSigning.STATUS_SENT,
        )

    def test_completed_webhook_is_idempotent(self):
        client = MagicMock()
        client.get_document.return_value = {'status': 'COMPLETED'}
        client.download_signed_pdf.return_value = b'%PDF-1.4\nsigned'

        with override_settings(MEDIA_ROOT=self.media_root), patch(
            'esigner.services.ESignerClient',
            return_value=client,
        ) as client_class, patch(
            'esigner.services._apply_post_signing_hook'
        ) as post_signing_hook:
            self.assertTrue(handle_webhook({
                'status': 'COMPLETED',
                'document_id': 'document-1',
            }))
            self.assertTrue(handle_webhook({
                'status': 'COMPLETED',
                'document_id': 'document-1',
            }))

        self.signing.refresh_from_db()
        self.assertEqual(self.signing.status, ESignerSigning.STATUS_COMPLETED)
        self.assertTrue(self.signing.signed_pdf.name.endswith('document-1.pdf'))
        self.assertEqual(client_class.call_count, 1)
        self.assertEqual(post_signing_hook.call_count, 1)
