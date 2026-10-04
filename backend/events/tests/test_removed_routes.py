from django.test import TestCase


class RemovedNatsAuthRoutesTests(TestCase):
    def test_old_token_and_authorize_routes_are_not_found(self):
        self.assertEqual(self.client.get("/api/" + "nats/token/").status_code, 404)
        self.assertEqual(self.client.get("/api/" + "nats/authorize/").status_code, 404)
