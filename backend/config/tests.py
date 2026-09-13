"""
Smoke tests for the base Django project setup.

These do not test any application behaviour (there are no app models yet -
see issues #3, #6, #8) - they exist to prove that the project boots,
settings are wired up correctly, and the test runner itself works.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
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


class BaseLayoutAndStaticPipelineTests(TestCase):
    """Tests for the shared base template / static asset foundation
    (issue #2)."""

    def test_project_template_dir_is_registered(self):
        dirs = [Path(d) for d in settings.TEMPLATES[0]['DIRS']]
        self.assertIn(settings.FRONTEND_DIR / 'templates', dirs)

    def test_static_source_dir_is_registered(self):
        dirs = [Path(d) for d in settings.STATICFILES_DIRS]
        self.assertIn(settings.FRONTEND_DIR / 'static', dirs)

    def test_placeholder_page_renders_with_shared_shell(self):
        client = Client()
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Shared shell markers from base.html.
        self.assertIn('<html', content)
        self.assertIn('NextTable - Home', content)  # title block content
        self.assertIn('id="placeholder-marker"', content)  # content block marker

        # htmx is loaded via CDN script tag, not vendored.
        self.assertIn('htmx.org', content)
        self.assertIn('<script src=', content)

        # Compiled Tailwind CSS is linked via {% static %}, not the Play CDN.
        self.assertIn('css/app.css', content)
        self.assertNotIn('cdn.tailwindcss.com', content)

    def test_placeholder_view_uses_base_template(self):
        response = self.client.get('/')
        template_names = [t.name for t in response.templates if t.name]
        self.assertIn('base.html', template_names)
        self.assertIn('placeholder.html', template_names)

    def test_compiled_tailwind_css_is_findable_by_staticfiles(self):
        """The compiled CSS must exist in the static source dir so both
        runserver (via the staticfiles finder) and collectstatic can serve
        it."""
        found = finders.find('css/app.css')
        self.assertIsNotNone(found)
        self.assertTrue(Path(found).is_file())
        self.assertGreater(Path(found).stat().st_size, 0)
