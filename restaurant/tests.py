from django.test import TestCase

from .models import SINGLETON_PK, RestaurantSettings


class RestaurantSettingsGetActiveTests(TestCase):
    def test_lazily_creates_row_with_defaults_on_empty_database(self):
        self.assertEqual(RestaurantSettings.objects.count(), 0)

        settings = RestaurantSettings.get_active()

        self.assertEqual(RestaurantSettings.objects.count(), 1)
        self.assertEqual(settings.pk, SINGLETON_PK)
        self.assertEqual(settings.name, 'My Restaurant')
        self.assertEqual(settings.grace_period_minutes, 30)
        self.assertFalse(settings.current_check_in_token)
        self.assertIsNone(settings.check_in_token_generated_at)
        self.assertIsNotNone(settings.created_at)
        self.assertIsNotNone(settings.updated_at)

    def test_second_call_returns_same_row_not_a_new_one(self):
        first = RestaurantSettings.get_active()
        second = RestaurantSettings.get_active()

        self.assertEqual(RestaurantSettings.objects.count(), 1)
        self.assertEqual(first.pk, second.pk)

    def test_second_call_reflects_updates_made_to_the_row(self):
        first = RestaurantSettings.get_active()
        first.name = 'Updated Name'
        first.save()

        second = RestaurantSettings.get_active()

        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.name, 'Updated Name')
        self.assertEqual(RestaurantSettings.objects.count(), 1)

    def test_save_always_forces_singleton_primary_key(self):
        settings = RestaurantSettings(name='Another Attempt')
        settings.save()

        self.assertEqual(settings.pk, SINGLETON_PK)
        self.assertEqual(RestaurantSettings.objects.count(), 1)

    def test_saving_a_freshly_constructed_instance_updates_existing_row(self):
        # Regression test for QA FAIL on issue #3: constructing a fresh
        # RestaurantSettings instance directly (not via get_active()) while
        # a settings row already exists used to crash with an
        # IntegrityError, because the forced pk routed the save() to an
        # UPDATE, and `created_at` (auto_now_add) is never populated on an
        # UPDATE, so the NOT NULL column got a NULL write attempt.
        first = RestaurantSettings.get_active()
        original_created_at = first.created_at

        second = RestaurantSettings(name='Second Attempt')
        second.save()  # must not raise IntegrityError

        self.assertEqual(RestaurantSettings.objects.count(), 1)
        self.assertEqual(second.pk, SINGLETON_PK)

        refreshed = RestaurantSettings.get_active()
        self.assertEqual(refreshed.pk, SINGLETON_PK)
        self.assertEqual(refreshed.name, 'Second Attempt')
        self.assertEqual(refreshed.created_at, original_created_at)
