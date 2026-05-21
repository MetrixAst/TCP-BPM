import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class SwaggerAPITestCase(APITestCase):
    def test_schema_json_200(self):
        response = self.client.get(
            reverse('schema'),
            HTTP_ACCEPT='application/vnd.oai.openapi+json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schema = json.loads(response.content)
        self.assertIn('openapi', schema)
        self.assertIn('paths', schema)
        self.assertIn('/api/v1/tasks/', schema['paths'])

    def test_swagger_ui_html_200(self):
        response = self.client.get(reverse('swagger-ui'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('text/html', response['Content-Type'])
        self.assertIn(b'swagger', response.content.lower())
