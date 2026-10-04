from django.test import SimpleTestCase

from events.subjects import validate_events


class ValidateEventsTests(SimpleTestCase):
    def test_accepts_valid_subjects_and_preserves_order(self):
        self.assertEqual(
            validate_events(["app.one", "app.>", "app.orders.*"]),
            ("app.one", "app.>", "app.orders.*"),
        )

    def test_rejects_empty_duplicate_malformed_whitespace_non_string_and_too_many(self):
        invalid_values = [
            [],
            ["app.one", "app.one"],
            ["app.order*"],
            ["app.>.orders"],
            ["app..orders"],
            ["app.orders "],
            [1],
            [f"app.{index}" for index in range(33)],
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_events(value)
