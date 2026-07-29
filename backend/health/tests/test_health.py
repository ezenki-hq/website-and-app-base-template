from unittest import mock

from django.db import DatabaseError
from django.test import TestCase


class HealthTests(TestCase):
    def test_health_reports_ready(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})

    @mock.patch("health.views.connection.cursor", side_effect=DatabaseError)
    def test_health_reports_database_failure(self, _cursor):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(response.content, {"status": "unavailable"})
