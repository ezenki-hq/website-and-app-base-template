import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


BACKEND_DIR = Path(__file__).resolve().parents[2]
S3_ENVIRONMENT_KEYS = (
    "S3_STORAGE_BUCKET_NAME",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "S3_ENDPOINT_URL",
    "S3_REGION_NAME",
    "S3_CUSTOM_DOMAIN",
)


def load_storages(environment):
    clean_environment = os.environ.copy()
    for key in S3_ENVIRONMENT_KEYS:
        clean_environment.pop(key, None)
    clean_environment.update(environment)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; sys.argv = ['manage.py', 'check']; "
            "import config.settings as settings; "
            "print(json.dumps(getattr(settings, 'STORAGES', None)))",
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        check=True,
        env=clean_environment,
        text=True,
    )
    return json.loads(result.stdout)


class S3StorageSettingsTests(SimpleTestCase):
    def test_missing_s3_credentials_keep_default_storage(self):
        self.assertIsNone(load_storages({}))

    def test_each_missing_required_value_keeps_default_storage(self):
        required_values = {
            "S3_STORAGE_BUCKET_NAME": "media-bucket",
            "S3_ACCESS_KEY_ID": "access-key",
            "S3_SECRET_ACCESS_KEY": "secret-key",
        }

        for missing_key in required_values:
            with self.subTest(missing_key=missing_key):
                environment = {
                    key: value
                    for key, value in required_values.items()
                    if key != missing_key
                }
                self.assertIsNone(load_storages(environment))

    def test_complete_credentials_configure_s3_media_and_keep_static_files_local(self):
        storages = load_storages(
            {
                "S3_STORAGE_BUCKET_NAME": "media-bucket",
                "S3_ACCESS_KEY_ID": "access-key",
                "S3_SECRET_ACCESS_KEY": "secret-key",
                "S3_ENDPOINT_URL": "https://s3.example.test",
                "S3_REGION_NAME": "region-1",
                "S3_CUSTOM_DOMAIN": "cdn.example.test",
            }
        )

        self.assertEqual(
            storages,
            {
                "default": {
                    "BACKEND": "storages.backends.s3.S3Storage",
                    "OPTIONS": {
                        "bucket_name": "media-bucket",
                        "access_key": "access-key",
                        "secret_key": "secret-key",
                        "endpoint_url": "https://s3.example.test",
                        "region_name": "region-1",
                        "custom_domain": "cdn.example.test",
                    },
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            },
        )
