"""
Smoke tests for the base Django project setup.

These do not test any application behaviour (there are no app models yet -
see issues #3, #6, #8) - they exist to prove that the project boots,
settings are wired up correctly, and the test runner itself works.
"""
from django.conf import settings
from django.test import Client, TestCase


class ProjectSmokeTests(TestCase):
    def test_admin_login_page_loads(self):
        """Hitting a real URL confirms urlconf, settings, and templates
        (Django's built-in admin templates) are all wired up correctly."""
        client = Client()
        response = client.get('/admin/login/')
        self.assertEqual(response.status_code, 200)

    def test_debug_defaults_true_and_is_a_bool(self):
        self.assertIs(type(settings.DEBUG), bool)

    def test_time_zone_is_explicitly_set(self):
        self.assertTrue(settings.TIME_ZONE)

    def test_templates_use_django_backend(self):
        backends = [t['BACKEND'] for t in settings.TEMPLATES]
        self.assertIn('django.template.backends.django.DjangoTemplates', backends)
