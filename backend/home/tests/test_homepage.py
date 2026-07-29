from importlib import import_module
import os
import subprocess
import sys

from django.apps import apps
from django.test import TestCase
from wagtail.models import Site

from home.models import HomePage


class HomePageTests(TestCase):
    def test_runtime_requires_django_secret_key(self):
        environment = os.environ.copy()
        environment.pop("DJANGO_SECRET_KEY", None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.argv = ['gunicorn']; import config.settings",
            ],
            capture_output=True,
            env=environment,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_default_site_uses_home_page(self):
        site = Site.objects.get(is_default_site=True)
        self.assertIsInstance(site.root_page.specific, HomePage)

    def test_home_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Billboard website")

    def test_homepage_migration_is_idempotent(self):
        create_homepage = import_module(
            "home.migrations.0002_create_homepage"
        ).create_homepage

        create_homepage(apps, None)

        self.assertEqual(HomePage.objects.filter(slug="home").count(), 1)
        site = Site.objects.get(is_default_site=True)
        self.assertIsInstance(site.root_page.specific, HomePage)
