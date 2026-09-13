from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from .auth import user_is_manager, user_is_staff_or_manager
from .check_in_tokens import (
    get_current_check_in_token,
    is_valid_check_in_token,
)
from .models import (
    EtaRule,
    SINGLETON_PK,
    RestaurantSettings,
    RestaurantTable,
    WaitlistEntry,
    WorkerProfile,
)
from .services import (
    InvalidStatusTransitionError,
    calculate_estimated_wait_minutes,
    check_table_compatibility,
    mark_guest_arrived,
    mark_guest_cancelled,
    mark_guest_left,
    mark_guest_no_show,
    mark_guest_seated,
    match_table_automatically,
    select_next_guest_for_table,
)


class CheckInTokenTests(TestCase):
    def test_token_is_stable_for_same_restaurant_day(self):
        restaurant_day = timezone.datetime(2026, 9, 13).date()

        first_token = get_current_check_in_token(for_date=restaurant_day)
        second_token = get_current_check_in_token(for_date=restaurant_day)

        self.assertEqual(first_token, second_token)

    def test_token_changes_for_next_restaurant_day(self):
        first_day = timezone.datetime(2026, 9, 13).date()
        next_day = timezone.datetime(2026, 9, 14).date()

        first_token = get_current_check_in_token(for_date=first_day)
        next_token = get_current_check_in_token(for_date=next_day)

        self.assertNotEqual(first_token, next_token)

    def test_token_is_not_raw_date_or_sequential_value(self):
        restaurant_day = timezone.datetime(2026, 9, 13).date()

        token = get_current_check_in_token(for_date=restaurant_day)

        self.assertNotEqual(token, restaurant_day.isoformat())
        self.assertNotEqual(token, str(restaurant_day.toordinal()))
        self.assertGreaterEqual(len(token), 24)

    def test_current_token_validates(self):
        restaurant_day = timezone.datetime(2026, 9, 13).date()
        token = get_current_check_in_token(for_date=restaurant_day)

        self.assertTrue(
            is_valid_check_in_token(token, for_date=restaurant_day)
        )

    def test_previous_day_token_is_rejected(self):
        previous_day = timezone.datetime(2026, 9, 12).date()
        current_day = timezone.datetime(2026, 9, 13).date()
        old_token = get_current_check_in_token(for_date=previous_day)

        self.assertFalse(
            is_valid_check_in_token(old_token, for_date=current_day)
        )

    def test_missing_blank_malformed_and_random_tokens_are_rejected(self):
        restaurant_day = timezone.datetime(2026, 9, 13).date()

        invalid_tokens = [None, '', '   ', 'not-a-real-token', object()]
        for token in invalid_tokens:
            with self.subTest(token=repr(token)):
                self.assertFalse(
                    is_valid_check_in_token(token, for_date=restaurant_day)
                )

    @override_settings(SECRET_KEY='first-test-secret')
    def test_token_depends_on_server_side_secret(self):
        restaurant_day = timezone.datetime(2026, 9, 13).date()

        first_secret_token = get_current_check_in_token(
            for_date=restaurant_day
        )
        with override_settings(SECRET_KEY='second-test-secret'):
            second_secret_token = get_current_check_in_token(
                for_date=restaurant_day
            )

        self.assertNotEqual(first_secret_token, second_secret_token)

    @override_settings(TIME_ZONE='Europe/Copenhagen')
    def test_current_token_uses_configured_local_date(self):
        utc_instant = datetime(
            2026,
            9,
            13,
            22,
            30,
            tzinfo=ZoneInfo('UTC'),
        )
        copenhagen_day = timezone.datetime(2026, 9, 14).date()

        with timezone.override('Europe/Copenhagen'):
            local_day = timezone.localtime(utc_instant).date()
            with patch('django.utils.timezone.now', return_value=utc_instant):
                token = get_current_check_in_token()

        self.assertEqual(local_day, copenhagen_day)
        self.assertEqual(
            token,
            get_current_check_in_token(for_date=copenhagen_day),
        )


class GuestCheckInPageTests(TestCase):
    def test_public_guest_can_render_form_with_current_token(self):
        token = get_current_check_in_token()

        response = self.client.get(
            reverse('restaurant:guest_check_in', args=[token])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="guest-check-in-marker"')
        self.assertContains(response, 'Join waitlist')
        self.assertNotContains(response, reverse('login'))

    def test_form_contains_required_and_optional_fields(self):
        token = get_current_check_in_token()

        response = self.client.get(
            reverse('restaurant:guest_check_in', args=[token])
        )

        required_fields = ['guest_name', 'party_size']
        optional_fields = [
            'phone_number',
            'location_preference',
            'seating_preference',
            'accessibility_requirements',
            'high_chair_needed',
            'notes',
        ]
        for field_name in required_fields + optional_fields:
            with self.subTest(field_name=field_name):
                self.assertContains(response, f'name="{field_name}"')

        self.assertContains(response, 'Required', count=2)
        self.assertContains(response, 'Optional', count=len(optional_fields))

    def test_form_uses_numeric_and_constrained_controls(self):
        token = get_current_check_in_token()

        response = self.client.get(
            reverse('restaurant:guest_check_in', args=[token])
        )

        self.assertContains(response, 'name="party_size"')
        self.assertContains(response, 'type="number"')
        self.assertContains(response, 'min="1"')
        self.assertContains(response, 'name="location_preference"')
        self.assertContains(response, 'value="indoor"')
        self.assertContains(response, 'value="outdoor"')
        self.assertContains(response, 'name="seating_preference"')
        self.assertContains(response, 'value="booth"')
        self.assertContains(response, 'name="high_chair_needed"')
        self.assertContains(response, 'value="yes"')

    def test_form_posts_to_guest_check_in_submission_endpoint(self):
        token = get_current_check_in_token()

        response = self.client.get(
            reverse('restaurant:guest_check_in', args=[token])
        )

        self.assertContains(
            response,
            f'action="{reverse("restaurant:guest_check_in_submit", args=[token])}"',
        )

    def test_invalid_token_displays_unavailable_state_without_login(self):
        response = self.client.get(
            reverse('restaurant:guest_check_in', args=['not-a-real-token'])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="guest-check-in-invalid-marker"')
        self.assertContains(response, 'not available')
        self.assertNotContains(response, 'name="guest_name"')
        self.assertNotContains(response, reverse('login'))

    def test_expired_token_displays_expired_state_without_login(self):
        previous_day = timezone.localdate() - timezone.timedelta(days=1)
        old_token = get_current_check_in_token(for_date=previous_day)

        response = self.client.get(
            reverse('restaurant:guest_check_in', args=[old_token])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="guest-check-in-expired-marker"')
        self.assertContains(response, 'has expired')
        self.assertNotContains(response, 'name="guest_name"')
        self.assertNotContains(response, reverse('login'))

    def test_successful_submission_creates_waitlist_entry_and_redirects(self):
        token = get_current_check_in_token()

        response = self.client.post(
            reverse('restaurant:guest_check_in_submit', args=[token]),
            {
                'guest_name': 'Ada Lovelace',
                'party_size': '2',
                'phone_number': '555-0101',
                'location_preference': 'indoor',
                'seating_preference': 'booth',
                'accessibility_requirements': '',
                'high_chair_needed': 'no',
                'notes': 'Near a window if possible',
            },
        )

        entry = WaitlistEntry.objects.get()
        self.assertRedirects(
            response,
            reverse(
                'restaurant:guest_check_in_status',
                args=[entry.public_identifier],
            ),
        )
        self.assertEqual(entry.guest_name, 'Ada Lovelace')
        self.assertEqual(entry.party_size, 2)
        self.assertEqual(entry.contact_text, '555-0101')
        self.assertIn('Indoor/outdoor preference: indoor', entry.preference_notes)
        self.assertIn('Seating preference: booth', entry.preference_notes)
        self.assertIn('Notes: Near a window if possible', entry.preference_notes)
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)
        self.assertEqual(entry.estimated_wait_minutes, 15)
        self.assertIsNotNone(entry.public_identifier)

    def test_status_page_shows_static_waitlist_information_without_duplicate(self):
        entry = WaitlistEntry.objects.create(
            guest_name='Grace Hopper',
            party_size=4,
        )
        status_url = reverse(
            'restaurant:guest_check_in_status',
            args=[entry.public_identifier],
        )

        response = self.client.get(status_url)
        second_response = self.client.get(status_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(response, 'id="guest-check-in-status-marker"')
        self.assertContains(response, 'Grace Hopper')
        self.assertContains(response, '4')
        self.assertContains(response, 'Waiting')
        self.assertContains(response, '15 minutes')
        self.assertEqual(WaitlistEntry.objects.count(), 1)

    def test_invalid_and_expired_token_submissions_do_not_create_entries(self):
        previous_day = timezone.localdate() - timezone.timedelta(days=1)
        old_token = get_current_check_in_token(for_date=previous_day)

        for token, marker in [
            ('not-a-real-token', 'id="guest-check-in-invalid-marker"'),
            (old_token, 'id="guest-check-in-expired-marker"'),
        ]:
            with self.subTest(token=token):
                response = self.client.post(
                    reverse('restaurant:guest_check_in_submit', args=[token]),
                    {'guest_name': 'Ada Lovelace', 'party_size': '2'},
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, marker)
                self.assertEqual(WaitlistEntry.objects.count(), 0)

    def test_invalid_submission_rerenders_form_with_errors_and_safe_values(self):
        token = get_current_check_in_token()

        response = self.client.post(
            reverse('restaurant:guest_check_in_submit', args=[token]),
            {
                'guest_name': '',
                'party_size': '0',
                'phone_number': '555-0101',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required.')
        self.assertContains(response, 'Ensure this value is greater than or equal to 1.')
        self.assertContains(response, '555-0101')
        self.assertEqual(WaitlistEntry.objects.count(), 0)

    def test_submission_ignores_client_submitted_internal_fields(self):
        token = get_current_check_in_token()
        submitted_public_identifier = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

        response = self.client.post(
            reverse('restaurant:guest_check_in_submit', args=[token]),
            {
                'guest_name': 'Katherine Johnson',
                'party_size': '3',
                'phone_number': '555-0202',
                'status': WaitlistEntry.Status.SEATED,
                'estimated_wait_minutes': '1',
                'public_identifier': submitted_public_identifier,
                'priority_metadata': '{"score": 999}',
                'assigned_table': '1',
                'notified_at': '2026-09-13T12:00:00Z',
            },
        )

        entry = WaitlistEntry.objects.get()
        self.assertRedirects(
            response,
            reverse(
                'restaurant:guest_check_in_status',
                args=[entry.public_identifier],
            ),
        )
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)
        self.assertEqual(entry.estimated_wait_minutes, 15)
        self.assertNotEqual(str(entry.public_identifier), submitted_public_identifier)
        self.assertEqual(entry.priority_metadata, {})
        self.assertIsNone(entry.assigned_table)
        self.assertIsNone(entry.notified_at)


class GuestWaitingPageTests(TestCase):
    def create_entry(self, **overrides):
        defaults = {
            'guest_name': 'Grace Hopper',
            'party_size': 4,
            'estimated_wait_minutes': 22,
        }
        defaults.update(overrides)
        return WaitlistEntry.objects.create(**defaults)

    def test_full_waiting_page_is_public_and_shows_guest_facing_information(self):
        entry = self.create_entry()

        response = self.client.get(
            reverse(
                'restaurant:guest_check_in_status',
                args=[entry.public_identifier],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="guest-check-in-status-marker"')
        self.assertContains(response, 'Grace Hopper')
        self.assertContains(response, '4')
        self.assertContains(response, 'Waiting')
        self.assertContains(response, '22 minutes')
        self.assertContains(response, 'hx-get=')
        self.assertContains(response, 'hx-trigger="load, every 15s"')
        self.assertContains(response, 'hx-swap="innerHTML"')
        self.assertNotContains(response, 'Queue position')
        self.assertNotContains(response, 'priority_metadata')
        self.assertNotContains(response, 'admin/')
        self.assertNotContains(response, reverse('login'))

    def test_partial_refresh_renders_current_status_eta_and_actions(self):
        entry = self.create_entry(status=WaitlistEntry.Status.ARRIVED)

        response = self.client.get(
            reverse(
                'restaurant:guest_check_in_status_partial',
                args=[entry.public_identifier],
            ),
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="guest-waiting-status-content"')
        self.assertContains(response, 'Arrived')
        self.assertContains(response, '22 minutes')
        self.assertContains(response, 'Cancel waitlist spot')
        self.assertNotContains(response, 'Guest name')

    def test_partial_refresh_returns_not_found_for_unknown_identifier(self):
        unknown_identifier = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

        response = self.client.get(
            reverse(
                'restaurant:guest_check_in_status_partial',
                args=[unknown_identifier],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_malformed_status_identifier_returns_not_found(self):
        response = self.client.get('/check-in/status/not-a-uuid/')

        self.assertEqual(response.status_code, 404)

    def test_cancellation_action_is_visible_only_for_cancellable_statuses(self):
        cancellable_statuses = [
            WaitlistEntry.Status.WAITING,
            WaitlistEntry.Status.ARRIVED,
            WaitlistEntry.Status.LATE_DEMOTED,
        ]
        blocked_statuses = [
            WaitlistEntry.Status.NOTIFIED,
            WaitlistEntry.Status.SEATED,
            WaitlistEntry.Status.CANCELLED,
            WaitlistEntry.Status.NO_SHOW,
            WaitlistEntry.Status.LEFT,
        ]

        for status in cancellable_statuses:
            with self.subTest(status=status):
                entry = self.create_entry(status=status)
                response = self.client.get(
                    reverse(
                        'restaurant:guest_check_in_status',
                        args=[entry.public_identifier],
                    )
                )

                self.assertContains(response, 'Cancel waitlist spot')

        for status in blocked_statuses:
            with self.subTest(status=status):
                entry = self.create_entry(
                    guest_name=f'Blocked {status}',
                    status=status,
                )
                response = self.client.get(
                    reverse(
                        'restaurant:guest_check_in_status',
                        args=[entry.public_identifier],
                    )
                )

                self.assertNotContains(response, 'Cancel waitlist spot')
                self.assertContains(response, 'Cancellation is not available')

    def test_cancel_get_shows_confirmation_without_changing_entry(self):
        entry = self.create_entry()

        response = self.client.get(
            reverse(
                'restaurant:guest_check_in_cancel',
                args=[entry.public_identifier],
            )
        )

        entry.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="guest-cancel-confirm-marker"')
        self.assertContains(response, 'Confirm cancellation')
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)
        self.assertIsNone(entry.cancelled_at)

    def test_confirming_cancellation_updates_allowed_statuses(self):
        allowed_statuses = [
            WaitlistEntry.Status.WAITING,
            WaitlistEntry.Status.ARRIVED,
            WaitlistEntry.Status.LATE_DEMOTED,
        ]

        for status in allowed_statuses:
            with self.subTest(status=status):
                entry = self.create_entry(
                    guest_name=f'Cancellable {status}',
                    status=status,
                )

                response = self.client.post(
                    reverse(
                        'restaurant:guest_check_in_cancel',
                        args=[entry.public_identifier],
                    )
                )

                entry.refresh_from_db()
                self.assertRedirects(
                    response,
                    reverse(
                        'restaurant:guest_check_in_status',
                        args=[entry.public_identifier],
                    ),
                )
                self.assertEqual(entry.status, WaitlistEntry.Status.CANCELLED)
                self.assertIsNotNone(entry.cancelled_at)
                self.assertEqual(entry.guest_name, f'Cancellable {status}')
                self.assertEqual(entry.party_size, 4)

    def test_successful_cancellation_page_shows_cancelled_without_action(self):
        entry = self.create_entry()

        self.client.post(
            reverse(
                'restaurant:guest_check_in_cancel',
                args=[entry.public_identifier],
            )
        )
        response = self.client.get(
            reverse(
                'restaurant:guest_check_in_status',
                args=[entry.public_identifier],
            )
        )

        self.assertContains(response, 'Cancelled')
        self.assertContains(response, 'Cancellation is not available')
        self.assertNotContains(response, 'Cancel waitlist spot')

    def test_confirming_cancellation_is_blocked_for_disallowed_statuses(self):
        blocked_statuses = [
            WaitlistEntry.Status.NOTIFIED,
            WaitlistEntry.Status.SEATED,
            WaitlistEntry.Status.CANCELLED,
            WaitlistEntry.Status.NO_SHOW,
            WaitlistEntry.Status.LEFT,
        ]

        for status in blocked_statuses:
            with self.subTest(status=status):
                entry = self.create_entry(
                    guest_name=f'Blocked {status}',
                    status=status,
                )

                response = self.client.post(
                    reverse(
                        'restaurant:guest_check_in_cancel',
                        args=[entry.public_identifier],
                    )
                )

                entry.refresh_from_db()
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'can no longer be cancelled')
                self.assertEqual(entry.status, status)
                self.assertIsNone(entry.cancelled_at)

    def test_table_ready_message_only_shows_for_notified_status(self):
        notified_entry = self.create_entry(status=WaitlistEntry.Status.NOTIFIED)
        waiting_entry = self.create_entry(
            guest_name='Waiting Guest',
            status=WaitlistEntry.Status.WAITING,
        )

        notified_response = self.client.get(
            reverse(
                'restaurant:guest_check_in_status',
                args=[notified_entry.public_identifier],
            )
        )
        waiting_response = self.client.get(
            reverse(
                'restaurant:guest_check_in_status',
                args=[waiting_entry.public_identifier],
            )
        )

        self.assertContains(notified_response, 'id="table-ready-message"')
        self.assertContains(notified_response, 'approach the host stand')
        self.assertNotContains(waiting_response, 'id="table-ready-message"')
        self.assertNotContains(waiting_response, 'approach the host stand')

    def test_unknown_status_identifier_returns_not_found(self):
        unknown_identifier = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

        response = self.client.get(
            reverse(
                'restaurant:guest_check_in_status',
                args=[unknown_identifier],
            )
        )

        self.assertEqual(response.status_code, 404)


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


class RestaurantTableModelTests(TestCase):
    def test_can_create_valid_table(self):
        table = RestaurantTable.objects.create(
            identifier='Table 1',
            capacity=4,
            status=RestaurantTable.Status.OCCUPIED,
        )

        self.assertEqual(table.identifier, 'Table 1')
        self.assertEqual(table.capacity, 4)
        self.assertEqual(table.status, RestaurantTable.Status.OCCUPIED)
        self.assertIsNotNone(table.created_at)
        self.assertIsNotNone(table.updated_at)
        self.assertEqual(str(table), 'Table 1 (4)')

    def test_new_table_defaults_to_free_status(self):
        table = RestaurantTable.objects.create(identifier='Patio 2', capacity=2)

        self.assertEqual(table.status, RestaurantTable.Status.FREE)

    def test_rejects_non_positive_capacity(self):
        invalid_capacities = [0, -1]

        for capacity in invalid_capacities:
            with self.subTest(capacity=capacity):
                table = RestaurantTable(identifier='Counter', capacity=capacity)
                with self.assertRaises(ValidationError) as context:
                    table.full_clean()

                self.assertIn('capacity', context.exception.message_dict)

    def test_rejects_invalid_status(self):
        table = RestaurantTable(
            identifier='Window 1',
            capacity=2,
            status='maintenance',
        )

        with self.assertRaises(ValidationError) as context:
            table.full_clean()

        self.assertIn('status', context.exception.message_dict)

    def test_prevents_duplicate_table_identifiers(self):
        RestaurantTable.objects.create(identifier='Booth 1', capacity=4)

        duplicate = RestaurantTable(identifier='Booth 1', capacity=6)
        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn('identifier', context.exception.message_dict)
        with self.assertRaises(IntegrityError):
            RestaurantTable.objects.create(identifier='Booth 1', capacity=6)


class WaitlistEntryModelTests(TestCase):
    def test_valid_entry_with_default_status_passes_validation(self):
        entry = WaitlistEntry(
            guest_name='Ada Lovelace',
            party_size=3,
        )

        entry.full_clean()

        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)

    def test_can_create_with_required_fields_and_defaults(self):
        entry = WaitlistEntry.objects.create(
            guest_name='Ada Lovelace',
            party_size=3,
        )

        self.assertEqual(entry.guest_name, 'Ada Lovelace')
        self.assertEqual(entry.party_size, 3)
        self.assertEqual(entry.contact_text, '')
        self.assertEqual(entry.preference_notes, '')
        self.assertEqual(entry.priority_metadata, {})
        self.assertIsNone(entry.assigned_table)
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)
        self.assertIsNotNone(entry.checked_in_at)
        self.assertIsNone(entry.notified_at)
        self.assertIsNone(entry.arrived_at)
        self.assertIsNone(entry.seated_at)
        self.assertIsNone(entry.cancelled_at)
        self.assertIsNone(entry.no_show_at)
        self.assertIsNone(entry.left_at)
        self.assertIsNotNone(entry.created_at)
        self.assertIsNotNone(entry.updated_at)

    def test_rejects_missing_guest_name(self):
        entry = WaitlistEntry(party_size=2)

        with self.assertRaises(ValidationError) as context:
            entry.full_clean()

        self.assertIn('guest_name', context.exception.message_dict)

    def test_rejects_blank_guest_name(self):
        for guest_name in ['', '   ']:
            with self.subTest(guest_name=repr(guest_name)):
                entry = WaitlistEntry(guest_name=guest_name, party_size=2)

                with self.assertRaises(ValidationError) as context:
                    entry.full_clean()

                self.assertIn('guest_name', context.exception.message_dict)

    def test_rejects_missing_party_size(self):
        entry = WaitlistEntry(guest_name='Missing Party Size')

        with self.assertRaises(ValidationError) as context:
            entry.full_clean()

        self.assertIn('party_size', context.exception.message_dict)

    def test_checked_in_at_is_automatic_but_can_be_explicitly_set(self):
        explicit_check_in = timezone.now() - timezone.timedelta(days=1)

        entry = WaitlistEntry.objects.create(
            guest_name='Grace Hopper',
            party_size=2,
            checked_in_at=explicit_check_in,
        )

        self.assertEqual(entry.checked_in_at, explicit_check_in)

    def test_lifecycle_timestamps_can_be_set_when_needed(self):
        timestamp = timezone.now()

        entry = WaitlistEntry.objects.create(
            guest_name='Katherine Johnson',
            party_size=4,
            notified_at=timestamp,
            arrived_at=timestamp,
            seated_at=timestamp,
            cancelled_at=timestamp,
            no_show_at=timestamp,
            left_at=timestamp,
        )

        self.assertEqual(entry.notified_at, timestamp)
        self.assertEqual(entry.arrived_at, timestamp)
        self.assertEqual(entry.seated_at, timestamp)
        self.assertEqual(entry.cancelled_at, timestamp)
        self.assertEqual(entry.no_show_at, timestamp)
        self.assertEqual(entry.left_at, timestamp)

    def test_rejects_non_positive_party_size(self):
        for party_size in [0, -1]:
            with self.subTest(party_size=party_size):
                entry = WaitlistEntry(
                    guest_name='Invalid Party',
                    party_size=party_size,
                )

                with self.assertRaises(ValidationError) as context:
                    entry.full_clean()

                self.assertIn('party_size', context.exception.message_dict)

    def test_rejects_invalid_status(self):
        entry = WaitlistEntry(
            guest_name='Invalid Status',
            party_size=2,
            status='paused',
        )

        with self.assertRaises(ValidationError) as context:
            entry.full_clean()

        self.assertIn('status', context.exception.message_dict)

    def test_optional_text_fields_may_be_blank(self):
        entry = WaitlistEntry(
            guest_name='Optional Fields',
            party_size=2,
            contact_text='',
            preference_notes='',
        )

        entry.full_clean()

    def test_priority_metadata_defaults_are_independent_dicts(self):
        first = WaitlistEntry(guest_name='First Guest', party_size=2)
        second = WaitlistEntry(guest_name='Second Guest', party_size=4)

        self.assertEqual(first.priority_metadata, {})
        self.assertEqual(second.priority_metadata, {})
        self.assertIsNot(first.priority_metadata, second.priority_metadata)

        first.priority_metadata['score'] = 10

        self.assertEqual(second.priority_metadata, {})

    def test_all_status_choices_validate(self):
        for status in WaitlistEntry.Status.values:
            with self.subTest(status=status):
                entry = WaitlistEntry(
                    guest_name='Valid Status',
                    party_size=2,
                    status=status,
                )

                entry.full_clean()

    def test_assigned_table_links_to_restaurant_table(self):
        table = RestaurantTable.objects.create(
            identifier='Window 4',
            capacity=4,
        )

        entry = WaitlistEntry.objects.create(
            guest_name='Alan Turing',
            party_size=2,
            assigned_table=table,
        )

        self.assertEqual(entry.assigned_table, table)
        self.assertEqual(list(table.waitlist_entries.all()), [entry])

    def test_deleting_assigned_table_clears_reference_without_deleting_entry(self):
        table = RestaurantTable.objects.create(
            identifier='Patio 8',
            capacity=6,
        )
        entry = WaitlistEntry.objects.create(
            guest_name='Mary Jackson',
            party_size=5,
            assigned_table=table,
        )

        table.delete()
        entry.refresh_from_db()

        self.assertIsNone(entry.assigned_table)
        self.assertEqual(
            WaitlistEntry.objects.filter(guest_name='Mary Jackson').count(),
            1,
        )

    def test_status_choices_cover_guest_lifecycle(self):
        self.assertEqual(
            set(WaitlistEntry.Status.values),
            {
                'waiting',
                'notified',
                'arrived',
                'seated',
                'late_demoted',
                'cancelled',
                'no_show',
                'left',
            },
        )
        self.assertEqual(
            dict(WaitlistEntry.Status.choices),
            {
                'waiting': 'Waiting',
                'notified': 'Notified',
                'arrived': 'Arrived',
                'seated': 'Seated',
                'late_demoted': 'Late/Demoted',
                'cancelled': 'Cancelled',
                'no_show': 'No-show',
                'left': 'Left',
            },
        )

    def test_string_representation_includes_guest_name_and_party_size(self):
        entry = WaitlistEntry(guest_name='Dorothy Vaughan', party_size=7)

        self.assertEqual(str(entry), 'Dorothy Vaughan (7)')


class WorkerAuthorizationTests(TestCase):
    password = 'usable-test-password-123'

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff_user = user_model.objects.create_user(
            username='staff',
            password=cls.password,
        )
        WorkerProfile.objects.create(
            user=cls.staff_user,
            role=WorkerProfile.Role.STAFF,
        )
        cls.manager_user = user_model.objects.create_user(
            username='manager',
            password=cls.password,
        )
        WorkerProfile.objects.create(
            user=cls.manager_user,
            role=WorkerProfile.Role.MANAGER,
        )
        cls.no_role_user = user_model.objects.create_user(
            username='plain',
            password=cls.password,
        )

    def test_staff_or_manager_check_allows_staff_and_manager_only(self):
        self.assertTrue(user_is_staff_or_manager(self.staff_user))
        self.assertTrue(user_is_staff_or_manager(self.manager_user))
        self.assertFalse(user_is_staff_or_manager(self.no_role_user))
        self.assertFalse(user_is_staff_or_manager(self.client.get('/').wsgi_request.user))

    def test_manager_check_allows_manager_only(self):
        self.assertFalse(user_is_manager(self.staff_user))
        self.assertTrue(user_is_manager(self.manager_user))
        self.assertFalse(user_is_manager(self.no_role_user))
        self.assertFalse(user_is_manager(self.client.get('/').wsgi_request.user))

    def test_auth_urls_can_be_reversed(self):
        self.assertEqual(reverse('login'), '/accounts/login/')
        self.assertEqual(reverse('logout'), '/accounts/logout/')

    def test_valid_login_redirects_to_staff_landing(self):
        response = self.client.post(
            reverse('login'),
            {'username': 'staff', 'password': self.password},
        )

        self.assertRedirects(response, reverse('restaurant:staff_landing'))

    def test_valid_login_redirects_to_next_url_when_provided(self):
        next_url = reverse('restaurant:manager_landing')
        response = self.client.post(
            f'{reverse("login")}?next={next_url}',
            {'username': 'manager', 'password': self.password},
        )

        self.assertRedirects(response, next_url)

    def test_logout_ends_session_and_redirects_to_non_error_page(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(reverse('logout'))

        self.assertRedirects(response, reverse('placeholder'))
        follow_up = self.client.get(reverse('restaurant:staff_landing'))
        self.assertEqual(follow_up.status_code, 302)
        self.assertIn(reverse('login'), follow_up['Location'])

    def test_anonymous_user_is_redirected_from_staff_landing_to_login(self):
        response = self.client.get(reverse('restaurant:staff_landing'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])
        self.assertIn('next=/staff/', response['Location'])

    def test_staff_user_can_view_staff_landing(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:staff_landing'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="staff-landing-marker"')

    def test_manager_user_can_view_staff_landing(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:staff_landing'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="staff-landing-marker"')

    def test_no_role_user_is_denied_staff_landing(self):
        self.client.force_login(self.no_role_user)

        response = self.client.get(reverse('restaurant:staff_landing'))

        self.assertEqual(response.status_code, 403)

    def test_staff_landing_displays_logged_in_user_and_logout_action(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:staff_landing'))

        self.assertContains(response, self.staff_user.get_username())
        self.assertContains(response, reverse('logout'))

    def test_staff_landing_renders_navigation_to_waitlist_and_table_status(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:staff_landing'))

        self.assertContains(response, 'id="staff-dashboard-nav"')
        self.assertContains(response, reverse('restaurant:waitlist'))
        self.assertContains(response, reverse('restaurant:table_status'))

    def test_anonymous_user_is_redirected_from_waitlist_to_login(self):
        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_staff_user_can_view_waitlist_placeholder(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertEqual(response.status_code, 200)

    def test_manager_user_can_view_waitlist_placeholder(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertEqual(response.status_code, 200)

    def test_waitlist_links_back_to_staff_dashboard(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertContains(response, reverse('restaurant:staff_landing'))

    def test_no_role_user_is_denied_waitlist_placeholder(self):
        self.client.force_login(self.no_role_user)

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_from_table_status_to_login(self):
        response = self.client.get(reverse('restaurant:table_status'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_staff_user_can_view_table_status_placeholder(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:table_status'))

        self.assertEqual(response.status_code, 200)

    def test_manager_user_can_view_table_status_placeholder(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:table_status'))

        self.assertEqual(response.status_code, 200)

    def test_no_role_user_is_denied_table_status_placeholder(self):
        self.client.force_login(self.no_role_user)

        response = self.client.get(reverse('restaurant:table_status'))

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_from_manager_landing_to_login(self):
        response = self.client.get(reverse('restaurant:manager_landing'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])
        self.assertIn('next=/manager/', response['Location'])

    def test_staff_user_is_denied_manager_landing(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:manager_landing'))

        self.assertEqual(response.status_code, 403)

    def test_manager_user_can_view_manager_landing(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:manager_landing'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="manager-landing-marker"')

    def test_no_role_user_is_denied_manager_landing(self):
        self.client.force_login(self.no_role_user)

        response = self.client.get(reverse('restaurant:manager_landing'))

        self.assertEqual(response.status_code, 403)


class WorkerAccountManagementTests(TestCase):
    password = 'usable-test-password-123'

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.manager_user = user_model.objects.create_user(
            username='manager',
            password=cls.password,
            first_name='Mina',
            last_name='Manager',
            email='manager@example.com',
        )
        WorkerProfile.objects.create(
            user=cls.manager_user,
            role=WorkerProfile.Role.MANAGER,
        )
        cls.staff_user = user_model.objects.create_user(
            username='staff',
            password=cls.password,
            first_name='Sam',
            last_name='Staff',
            email='staff@example.com',
        )
        WorkerProfile.objects.create(
            user=cls.staff_user,
            role=WorkerProfile.Role.STAFF,
        )

    def test_manager_can_view_worker_account_list(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:worker_account_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="worker-account-list-marker"')
        self.assertContains(response, 'manager')
        self.assertContains(response, 'Mina Manager')
        self.assertContains(response, 'manager@example.com')
        self.assertContains(response, 'Manager')
        self.assertContains(response, 'Active')
        self.assertContains(
            response,
            reverse('restaurant:worker_account_edit', args=[self.staff_user.pk]),
        )

    def test_staff_user_is_denied_worker_account_management_pages(self):
        self.client.force_login(self.staff_user)

        urls = [
            reverse('restaurant:worker_account_list'),
            reverse('restaurant:worker_account_create'),
            reverse('restaurant:worker_account_edit', args=[self.staff_user.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_from_worker_account_management_pages(self):
        urls = [
            reverse('restaurant:worker_account_list'),
            reverse('restaurant:worker_account_create'),
            reverse('restaurant:worker_account_edit', args=[self.staff_user.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response['Location'])
                self.assertIn(f'next={url}', response['Location'])

    def test_manager_can_create_worker_account(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:worker_account_create'),
            {
                'username': 'newstaff',
                'first_name': 'New',
                'last_name': 'Staffer',
                'email': 'newstaff@example.com',
                'password1': 'strong-new-password-123',
                'password2': 'strong-new-password-123',
                'is_active': 'on',
                'role': WorkerProfile.Role.STAFF,
            },
        )

        self.assertRedirects(response, reverse('restaurant:worker_account_list'))
        user = get_user_model().objects.get(username='newstaff')
        self.assertTrue(user.check_password('strong-new-password-123'))
        self.assertEqual(user.first_name, 'New')
        self.assertEqual(user.last_name, 'Staffer')
        self.assertEqual(user.email, 'newstaff@example.com')
        self.assertTrue(user.is_active)
        self.assertEqual(user.worker_profile.role, WorkerProfile.Role.STAFF)
        self.assertEqual(WorkerProfile.objects.filter(user=user).count(), 1)

    def test_create_worker_account_rejects_invalid_role_and_preserves_safe_values(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:worker_account_create'),
            {
                'username': 'badrole',
                'first_name': 'Bad',
                'last_name': 'Role',
                'email': 'badrole@example.com',
                'password1': 'strong-new-password-123',
                'password2': 'strong-new-password-123',
                'is_active': 'on',
                'role': 'owner',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertContains(response, 'badrole')
        self.assertContains(response, 'Bad')
        self.assertContains(response, 'badrole@example.com')
        self.assertFalse(get_user_model().objects.filter(username='badrole').exists())

    def test_create_worker_account_rejects_duplicate_username(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:worker_account_create'),
            {
                'username': 'staff',
                'first_name': 'Other',
                'last_name': 'Person',
                'email': 'other@example.com',
                'password1': 'strong-new-password-123',
                'password2': 'strong-new-password-123',
                'role': WorkerProfile.Role.STAFF,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A user with that username already exists.')
        self.assertEqual(get_user_model().objects.filter(username='staff').count(), 1)

    def test_create_worker_account_rejects_mismatched_passwords(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:worker_account_create'),
            {
                'username': 'mismatch',
                'password1': 'strong-new-password-123',
                'password2': 'different-strong-password-123',
                'role': WorkerProfile.Role.STAFF,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The two password fields did not match.')
        self.assertFalse(get_user_model().objects.filter(username='mismatch').exists())

    def test_manager_can_edit_worker_account_without_creating_duplicate_profile(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:worker_account_edit', args=[self.staff_user.pk]),
            {
                'username': 'leadstaff',
                'first_name': 'Lead',
                'last_name': 'Worker',
                'email': 'lead@example.com',
                'is_active': '',
                'role': WorkerProfile.Role.MANAGER,
            },
        )

        self.assertRedirects(response, reverse('restaurant:worker_account_list'))
        self.staff_user.refresh_from_db()
        self.staff_user.worker_profile.refresh_from_db()
        self.assertEqual(self.staff_user.username, 'leadstaff')
        self.assertEqual(self.staff_user.first_name, 'Lead')
        self.assertEqual(self.staff_user.last_name, 'Worker')
        self.assertEqual(self.staff_user.email, 'lead@example.com')
        self.assertFalse(self.staff_user.is_active)
        self.assertEqual(self.staff_user.worker_profile.role, WorkerProfile.Role.MANAGER)
        self.assertEqual(WorkerProfile.objects.filter(user=self.staff_user).count(), 1)

    def test_edit_worker_account_rejects_invalid_role(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:worker_account_edit', args=[self.staff_user.pk]),
            {
                'username': 'staff',
                'first_name': 'Sam',
                'last_name': 'Staff',
                'email': 'staff@example.com',
                'is_active': 'on',
                'role': 'owner',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.staff_user.worker_profile.refresh_from_db()
        self.assertEqual(self.staff_user.worker_profile.role, WorkerProfile.Role.STAFF)

    def test_manager_cannot_demote_or_deactivate_self(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:worker_account_edit', args=[self.manager_user.pk]),
            {
                'username': 'manager',
                'first_name': 'Mina',
                'last_name': 'Manager',
                'email': 'manager@example.com',
                'role': WorkerProfile.Role.STAFF,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You cannot remove your own Manager access.')
        self.assertContains(response, 'You cannot deactivate your own account.')
        self.manager_user.refresh_from_db()
        self.manager_user.worker_profile.refresh_from_db()
        self.assertTrue(self.manager_user.is_active)
        self.assertEqual(
            self.manager_user.worker_profile.role,
            WorkerProfile.Role.MANAGER,
        )


class TableConfigurationTests(TestCase):
    password = 'usable-test-password-123'

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.manager_user = user_model.objects.create_user(
            username='manager',
            password=cls.password,
        )
        WorkerProfile.objects.create(
            user=cls.manager_user,
            role=WorkerProfile.Role.MANAGER,
        )
        cls.staff_user = user_model.objects.create_user(
            username='staff',
            password=cls.password,
        )
        WorkerProfile.objects.create(
            user=cls.staff_user,
            role=WorkerProfile.Role.STAFF,
        )
        cls.table = RestaurantTable.objects.create(
            identifier='Window 1',
            capacity=4,
            status=RestaurantTable.Status.FREE,
        )

    def test_manager_can_view_table_config_list(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:table_config_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="table-config-list-marker"')
        self.assertContains(response, 'Window 1')
        self.assertContains(response, '4')
        self.assertContains(response, 'Free')
        self.assertContains(response, reverse('restaurant:table_config_create'))
        self.assertContains(
            response,
            reverse('restaurant:table_config_edit', args=[self.table.pk]),
        )
        self.assertContains(
            response,
            reverse('restaurant:table_config_remove', args=[self.table.pk]),
        )

    def test_manager_landing_links_to_table_config_list(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:manager_landing'))

        self.assertContains(response, reverse('restaurant:table_config_list'))

    def test_staff_user_is_denied_table_config_pages(self):
        self.client.force_login(self.staff_user)

        urls = [
            reverse('restaurant:table_config_list'),
            reverse('restaurant:table_config_create'),
            reverse('restaurant:table_config_edit', args=[self.table.pk]),
            reverse('restaurant:table_config_remove', args=[self.table.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

                post_response = self.client.post(url, {})
                self.assertEqual(post_response.status_code, 403)

    def test_anonymous_user_is_redirected_from_table_config_pages(self):
        urls = [
            reverse('restaurant:table_config_list'),
            reverse('restaurant:table_config_create'),
            reverse('restaurant:table_config_edit', args=[self.table.pk]),
            reverse('restaurant:table_config_remove', args=[self.table.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response['Location'])
                self.assertIn(f'next={url}', response['Location'])

    def test_manager_can_create_table(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:table_config_create'),
            {
                'identifier': 'Patio 2',
                'capacity': '6',
                'status': RestaurantTable.Status.RESERVED,
            },
        )

        self.assertRedirects(response, reverse('restaurant:table_config_list'))
        table = RestaurantTable.objects.get(identifier='Patio 2')
        self.assertEqual(table.capacity, 6)
        self.assertEqual(table.status, RestaurantTable.Status.RESERVED)

    def test_create_table_rejects_invalid_values_and_preserves_safe_values(self):
        self.client.force_login(self.manager_user)
        RestaurantTable.objects.create(
            identifier='Duplicate',
            capacity=2,
            status=RestaurantTable.Status.FREE,
        )

        cases = [
            (
                {
                    'identifier': '',
                    'capacity': '4',
                    'status': RestaurantTable.Status.FREE,
                },
                'This field is required.',
            ),
            (
                {
                    'identifier': 'Duplicate',
                    'capacity': '4',
                    'status': RestaurantTable.Status.FREE,
                },
                'Restaurant table with this Identifier already exists.',
            ),
            (
                {
                    'identifier': 'Zero',
                    'capacity': '0',
                    'status': RestaurantTable.Status.FREE,
                },
                'Capacity must be greater than zero.',
            ),
            (
                {
                    'identifier': 'Words',
                    'capacity': 'many',
                    'status': RestaurantTable.Status.FREE,
                },
                'Enter a whole number.',
            ),
            (
                {
                    'identifier': 'Invalid Status',
                    'capacity': '4',
                    'status': 'maintenance',
                },
                'Select a valid choice',
            ),
        ]

        for data, error in cases:
            with self.subTest(data=data):
                response = self.client.post(
                    reverse('restaurant:table_config_create'),
                    data,
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error)
                if data['identifier']:
                    self.assertContains(response, data['identifier'])

        self.assertFalse(RestaurantTable.objects.filter(identifier='Zero').exists())
        self.assertFalse(RestaurantTable.objects.filter(identifier='Words').exists())
        self.assertFalse(
            RestaurantTable.objects.filter(identifier='Invalid Status').exists()
        )

    def test_manager_can_edit_table_without_creating_duplicate(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:table_config_edit', args=[self.table.pk]),
            {
                'identifier': 'Window 2',
                'capacity': '8',
                'status': RestaurantTable.Status.CLEANING,
            },
        )

        self.assertRedirects(response, reverse('restaurant:table_config_list'))
        self.table.refresh_from_db()
        self.assertEqual(self.table.identifier, 'Window 2')
        self.assertEqual(self.table.capacity, 8)
        self.assertEqual(self.table.status, RestaurantTable.Status.CLEANING)
        self.assertEqual(RestaurantTable.objects.count(), 1)

    def test_edit_table_rejects_invalid_status(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:table_config_edit', args=[self.table.pk]),
            {
                'identifier': 'Window 1',
                'capacity': '4',
                'status': 'maintenance',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, RestaurantTable.Status.FREE)

    def test_remove_table_requires_confirmation_post(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(
            reverse('restaurant:table_config_remove', args=[self.table.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="table-config-remove-marker"')
        self.assertTrue(RestaurantTable.objects.filter(pk=self.table.pk).exists())

    def test_manager_can_remove_allowed_table_with_post(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:table_config_remove', args=[self.table.pk])
        )

        self.assertRedirects(response, reverse('restaurant:table_config_list'))
        self.assertFalse(RestaurantTable.objects.filter(pk=self.table.pk).exists())

    def test_manager_cannot_remove_reserved_or_occupied_tables(self):
        self.client.force_login(self.manager_user)

        for status in [
            RestaurantTable.Status.RESERVED,
            RestaurantTable.Status.OCCUPIED,
        ]:
            with self.subTest(status=status):
                table = RestaurantTable.objects.create(
                    identifier=f'Blocked {status}',
                    capacity=2,
                    status=status,
                )

                response = self.client.post(
                    reverse('restaurant:table_config_remove', args=[table.pk]),
                    follow=True,
                )

                self.assertRedirects(response, reverse('restaurant:table_config_list'))
                self.assertContains(
                    response,
                    'Reserved or occupied tables cannot be removed.',
                )
                self.assertContains(response, table.identifier)
                self.assertTrue(RestaurantTable.objects.filter(pk=table.pk).exists())


class DefaultEtaConfigurationTests(TestCase):
    def test_default_eta_configuration_is_available_after_migrations(self):
        self.assertEqual(RestaurantSettings.get_active().grace_period_minutes, 30)
        self.assertTrue(
            EtaRule.objects.filter(
                min_party_size=1,
                max_party_size=2,
                estimated_wait_minutes=15,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            EtaRule.objects.filter(
                min_party_size=3,
                max_party_size=4,
                estimated_wait_minutes=25,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            EtaRule.objects.filter(
                min_party_size=5,
                max_party_size=None,
                estimated_wait_minutes=35,
                is_active=True,
            ).exists()
        )


class EtaConfigurationTests(TestCase):
    password = 'usable-test-password-123'

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.manager_user = user_model.objects.create_user(
            username='eta-manager',
            password=cls.password,
        )
        WorkerProfile.objects.create(
            user=cls.manager_user,
            role=WorkerProfile.Role.MANAGER,
        )
        cls.staff_user = user_model.objects.create_user(
            username='eta-staff',
            password=cls.password,
        )
        WorkerProfile.objects.create(
            user=cls.staff_user,
            role=WorkerProfile.Role.STAFF,
        )

    def setUp(self):
        EtaRule.objects.all().delete()
        self.rule = EtaRule.objects.create(
            min_party_size=1,
            max_party_size=2,
            estimated_wait_minutes=15,
        )

    def eta_urls(self):
        return [
            reverse('restaurant:eta_config'),
            reverse('restaurant:eta_rule_create'),
            reverse('restaurant:eta_rule_edit', args=[self.rule.pk]),
            reverse('restaurant:eta_grace_period_edit'),
        ]

    def test_manager_can_view_eta_config(self):
        settings = RestaurantSettings.get_active()
        settings.grace_period_minutes = 30
        settings.save()
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:eta_config'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="eta-config-marker"')
        self.assertContains(response, '1')
        self.assertContains(response, '2')
        self.assertContains(response, '15 minutes')
        self.assertContains(response, 'Active')
        self.assertContains(response, '30 minutes')
        self.assertContains(response, reverse('restaurant:eta_rule_create'))
        self.assertContains(
            response,
            reverse('restaurant:eta_rule_edit', args=[self.rule.pk]),
        )
        self.assertContains(response, reverse('restaurant:eta_grace_period_edit'))

    def test_manager_landing_links_to_eta_config(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse('restaurant:manager_landing'))

        self.assertContains(response, reverse('restaurant:eta_config'))

    def test_staff_user_is_denied_eta_config_pages(self):
        self.client.force_login(self.staff_user)

        for url in self.eta_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

                post_response = self.client.post(url, {})
                self.assertEqual(post_response.status_code, 403)

    def test_anonymous_user_is_redirected_from_eta_config_pages(self):
        for url in self.eta_urls():
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response['Location'])
                self.assertIn(f'next={url}', response['Location'])

    def test_manager_can_create_bounded_eta_rule(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:eta_rule_create'),
            {
                'min_party_size': '3',
                'max_party_size': '4',
                'estimated_wait_minutes': '25',
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('restaurant:eta_config'))
        rule = EtaRule.objects.get(min_party_size=3)
        self.assertEqual(rule.max_party_size, 4)
        self.assertEqual(rule.estimated_wait_minutes, 25)
        self.assertTrue(rule.is_active)

    def test_manager_can_create_open_ended_eta_rule(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:eta_rule_create'),
            {
                'min_party_size': '5',
                'max_party_size': '',
                'estimated_wait_minutes': '35',
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('restaurant:eta_config'))
        rule = EtaRule.objects.get(min_party_size=5)
        self.assertIsNone(rule.max_party_size)
        self.assertEqual(rule.estimated_wait_minutes, 35)

    def test_manager_can_edit_eta_rule(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:eta_rule_edit', args=[self.rule.pk]),
            {
                'min_party_size': '2',
                'max_party_size': '3',
                'estimated_wait_minutes': '20',
                'is_active': '',
            },
        )

        self.assertRedirects(response, reverse('restaurant:eta_config'))
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.min_party_size, 2)
        self.assertEqual(self.rule.max_party_size, 3)
        self.assertEqual(self.rule.estimated_wait_minutes, 20)
        self.assertFalse(self.rule.is_active)
        self.assertEqual(EtaRule.objects.count(), 1)

    def test_eta_rule_rejects_required_and_non_positive_values(self):
        self.client.force_login(self.manager_user)
        cases = [
            (
                {
                    'min_party_size': '',
                    'max_party_size': '2',
                    'estimated_wait_minutes': '15',
                    'is_active': 'on',
                },
                'This field is required.',
            ),
            (
                {
                    'min_party_size': '0',
                    'max_party_size': '2',
                    'estimated_wait_minutes': '15',
                    'is_active': 'on',
                },
                'Minimum party size must be greater than zero.',
            ),
            (
                {
                    'min_party_size': '3',
                    'max_party_size': '0',
                    'estimated_wait_minutes': '15',
                    'is_active': 'on',
                },
                'Maximum party size must be greater than zero.',
            ),
            (
                {
                    'min_party_size': '4',
                    'max_party_size': '3',
                    'estimated_wait_minutes': '15',
                    'is_active': 'on',
                },
                'Maximum party size must be greater than or equal to minimum party size.',
            ),
            (
                {
                    'min_party_size': '3',
                    'max_party_size': '4',
                    'estimated_wait_minutes': '',
                    'is_active': 'on',
                },
                'This field is required.',
            ),
            (
                {
                    'min_party_size': '3',
                    'max_party_size': '4',
                    'estimated_wait_minutes': '0',
                    'is_active': 'on',
                },
                'Estimated wait minutes must be greater than zero.',
            ),
        ]

        for data, error in cases:
            with self.subTest(data=data):
                response = self.client.post(
                    reverse('restaurant:eta_rule_create'),
                    data,
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error)

        self.assertEqual(EtaRule.objects.count(), 1)

    def test_eta_rule_rejects_overlapping_active_ranges(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:eta_rule_create'),
            {
                'min_party_size': '2',
                'max_party_size': '4',
                'estimated_wait_minutes': '25',
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active party-size ETA rules cannot overlap.')
        self.assertEqual(EtaRule.objects.count(), 1)

    def test_eta_rule_permits_adjacent_non_overlapping_ranges(self):
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:eta_rule_create'),
            {
                'min_party_size': '3',
                'max_party_size': '4',
                'estimated_wait_minutes': '25',
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('restaurant:eta_config'))
        self.assertTrue(
            EtaRule.objects.filter(min_party_size=3, max_party_size=4).exists()
        )

    def test_eta_rule_rejects_overlap_with_open_ended_rule(self):
        EtaRule.objects.create(
            min_party_size=5,
            max_party_size=None,
            estimated_wait_minutes=35,
        )
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:eta_rule_create'),
            {
                'min_party_size': '6',
                'max_party_size': '8',
                'estimated_wait_minutes': '45',
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active party-size ETA rules cannot overlap.')
        self.assertFalse(EtaRule.objects.filter(min_party_size=6).exists())

    def test_eta_rule_permits_inactive_overlapping_and_second_open_ended_rule(self):
        EtaRule.objects.create(
            min_party_size=5,
            max_party_size=None,
            estimated_wait_minutes=35,
        )
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:eta_rule_create'),
            {
                'min_party_size': '6',
                'max_party_size': '',
                'estimated_wait_minutes': '45',
                'is_active': '',
            },
        )

        self.assertRedirects(response, reverse('restaurant:eta_config'))
        inactive_rule = EtaRule.objects.get(min_party_size=6)
        self.assertIsNone(inactive_rule.max_party_size)
        self.assertFalse(inactive_rule.is_active)

    def test_grace_period_update_and_validation(self):
        settings = RestaurantSettings.get_active()
        settings.grace_period_minutes = 30
        settings.save()
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse('restaurant:eta_grace_period_edit'),
            {'grace_period_minutes': '45'},
        )

        self.assertRedirects(response, reverse('restaurant:eta_config'))
        settings.refresh_from_db()
        self.assertEqual(settings.grace_period_minutes, 45)

        invalid_cases = [
            ('', 'This field is required.'),
            ('0', 'Grace period must be greater than zero minutes.'),
            ('-1', 'Grace period must be greater than zero minutes.'),
            ('241', 'Grace period cannot exceed 240 minutes.'),
        ]
        for value, error in invalid_cases:
            with self.subTest(value=value):
                response = self.client.post(
                    reverse('restaurant:eta_grace_period_edit'),
                    {'grace_period_minutes': value},
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error)

        settings.refresh_from_db()
        self.assertEqual(settings.grace_period_minutes, 45)


class WaitEstimateCalculationTests(TestCase):
    """Tests for the calculate_estimated_wait_minutes service function."""

    def setUp(self):
        """Set up test ETA rules and clean up any existing entries."""
        EtaRule.objects.all().delete()
        WaitlistEntry.objects.all().delete()
        RestaurantTable.objects.all().delete()

        # Create standard rules for testing
        self.rule_1_2 = EtaRule.objects.create(
            min_party_size=1,
            max_party_size=2,
            estimated_wait_minutes=15,
            is_active=True,
        )
        self.rule_3_4 = EtaRule.objects.create(
            min_party_size=3,
            max_party_size=4,
            estimated_wait_minutes=25,
            is_active=True,
        )
        self.rule_5_plus = EtaRule.objects.create(
            min_party_size=5,
            max_party_size=None,
            estimated_wait_minutes=35,
            is_active=True,
        )

    def test_validates_party_size(self):
        """Party size must be positive."""
        with self.assertRaises(ValidationError):
            calculate_estimated_wait_minutes(0)
        with self.assertRaises(ValidationError):
            calculate_estimated_wait_minutes(-1)
        with self.assertRaises(ValidationError):
            calculate_estimated_wait_minutes('not a number')

    def test_returns_base_estimate_with_empty_queue(self):
        """With no queue, estimate should be base * (0 + 1) = base."""
        estimate = calculate_estimated_wait_minutes(2)
        self.assertEqual(estimate, 15)

    def test_matches_party_size_to_correct_rule(self):
        """Estimate should use the correct rule for each party size."""
        self.assertEqual(calculate_estimated_wait_minutes(1), 15)
        self.assertEqual(calculate_estimated_wait_minutes(2), 15)
        self.assertEqual(calculate_estimated_wait_minutes(3), 25)
        self.assertEqual(calculate_estimated_wait_minutes(4), 25)
        self.assertEqual(calculate_estimated_wait_minutes(5), 35)
        self.assertEqual(calculate_estimated_wait_minutes(10), 35)

    def test_estimate_multiplies_with_queue_size(self):
        """Estimate should be base * (queue_position + 1)."""
        base_estimate = calculate_estimated_wait_minutes(2)
        self.assertEqual(base_estimate, 15)  # base * (0 + 1) = 15

        # Add one waiting party
        WaitlistEntry.objects.create(
            guest_name='Guest 1', party_size=2, status=WaitlistEntry.Status.WAITING
        )
        estimate_with_one = calculate_estimated_wait_minutes(2)
        self.assertEqual(estimate_with_one, 30)  # 15 * (1 + 1) = 30

        # Add another waiting party
        WaitlistEntry.objects.create(
            guest_name='Guest 2', party_size=1, status=WaitlistEntry.Status.WAITING
        )
        estimate_with_two = calculate_estimated_wait_minutes(2)
        self.assertEqual(estimate_with_two, 45)  # 15 * (2 + 1) = 45

    def test_notified_guests_not_in_queue(self):
        """Notified guests should not be counted in queue calculation."""
        WaitlistEntry.objects.create(
            guest_name='Waiting Guest', party_size=2, status=WaitlistEntry.Status.WAITING
        )
        WaitlistEntry.objects.create(
            guest_name='Notified Guest', party_size=2, status=WaitlistEntry.Status.NOTIFIED
        )

        estimate = calculate_estimated_wait_minutes(2)
        # Only waiting guest counted: 15 * (1 + 1) = 30
        self.assertEqual(estimate, 30)

    def test_seated_guests_not_in_queue(self):
        """Seated and other completed statuses should not affect queue."""
        excluded_statuses = [
            WaitlistEntry.Status.SEATED,
            WaitlistEntry.Status.ARRIVED,
            WaitlistEntry.Status.CANCELLED,
            WaitlistEntry.Status.NO_SHOW,
            WaitlistEntry.Status.LEFT,
            WaitlistEntry.Status.NOTIFIED,
        ]

        for status in excluded_statuses:
            WaitlistEntry.objects.create(
                guest_name=f'Guest {status}',
                party_size=2,
                status=status,
            )

        estimate = calculate_estimated_wait_minutes(2)
        # Queue should be empty (no WAITING or LATE_DEMOTED), so just the base estimate
        self.assertEqual(estimate, 15)

    def test_late_demoted_guests_counted_in_queue(self):
        """Late/demoted guests should be counted in queue like waiting guests."""
        WaitlistEntry.objects.create(
            guest_name='Waiting Guest', party_size=2, status=WaitlistEntry.Status.WAITING
        )
        WaitlistEntry.objects.create(
            guest_name='Demoted Guest', party_size=2, status=WaitlistEntry.Status.LATE_DEMOTED
        )

        estimate = calculate_estimated_wait_minutes(2)
        # Two parties in queue: 15 * (2 + 1) = 45
        self.assertEqual(estimate, 45)

    def test_table_availability_not_used_in_calculation(self):
        """Table availability is considered for future optimization but not used in MVP."""
        # With or without tables, the calculation is the same
        estimate_no_tables = calculate_estimated_wait_minutes(2)
        self.assertEqual(estimate_no_tables, 15)

        RestaurantTable.objects.create(
            identifier='Table 1', capacity=2, status=RestaurantTable.Status.FREE
        )
        estimate_with_table = calculate_estimated_wait_minutes(2)
        # Still the same - table availability doesn't affect MVP algorithm
        self.assertEqual(estimate_with_table, 15)

    def test_no_applicable_rule_returns_default(self):
        """If no ETA rule matches, return the default estimate."""
        EtaRule.objects.all().delete()
        # No rules at all
        estimate = calculate_estimated_wait_minutes(5)
        self.assertEqual(estimate, WaitlistEntry.DEFAULT_INITIAL_ESTIMATED_WAIT_MINUTES)

    def test_inactive_rule_not_used(self):
        """Inactive ETA rules should not be used in calculation."""
        self.rule_3_4.is_active = False
        self.rule_3_4.save()

        # Now party of 3-4 has no active rule
        estimate = calculate_estimated_wait_minutes(3)
        self.assertEqual(estimate, WaitlistEntry.DEFAULT_INITIAL_ESTIMATED_WAIT_MINUTES)

    def test_calculation_at_rule_boundaries(self):
        """Test party sizes at the boundaries of rule ranges."""
        # Test lower boundary
        estimate_1 = calculate_estimated_wait_minutes(1)
        self.assertEqual(estimate_1, 15)  # min_party_size=1

        # Test upper boundary of first rule
        estimate_2 = calculate_estimated_wait_minutes(2)
        self.assertEqual(estimate_2, 15)  # max_party_size=2

        # Test lower boundary of second rule
        estimate_3 = calculate_estimated_wait_minutes(3)
        self.assertEqual(estimate_3, 25)  # min_party_size=3

        # Test upper boundary of second rule
        estimate_4 = calculate_estimated_wait_minutes(4)
        self.assertEqual(estimate_4, 25)  # max_party_size=4

        # Test lower boundary of open-ended rule
        estimate_5 = calculate_estimated_wait_minutes(5)
        self.assertEqual(estimate_5, 35)  # min_party_size=5

        # Test higher value in open-ended rule
        estimate_20 = calculate_estimated_wait_minutes(20)
        self.assertEqual(estimate_20, 35)  # max_party_size=None


class GuestCheckInFormIntegrationTests(TestCase):
    """Tests that the wait estimate calculation is properly integrated."""

    def setUp(self):
        """Set up test ETA rules."""
        EtaRule.objects.all().delete()
        WaitlistEntry.objects.all().delete()
        RestaurantTable.objects.all().delete()

        self.rule = EtaRule.objects.create(
            min_party_size=1,
            max_party_size=2,
            estimated_wait_minutes=15,
            is_active=True,
        )

    def test_check_in_form_uses_calculated_estimate_not_default(self):
        """The form should use the calculated estimate, not the default."""
        token = get_current_check_in_token()

        # Manually create a queue by adding waiting guests
        WaitlistEntry.objects.create(
            guest_name='Queue 1', party_size=2, status=WaitlistEntry.Status.WAITING
        )
        WaitlistEntry.objects.create(
            guest_name='Queue 2', party_size=2, status=WaitlistEntry.Status.WAITING
        )

        response = self.client.post(
            reverse('restaurant:guest_check_in_submit', args=[token]),
            {
                'guest_name': 'Test Guest',
                'party_size': '2',
                'phone_number': '',
                'location_preference': 'no_preference',
                'seating_preference': 'no_preference',
                'accessibility_requirements': '',
                'high_chair_needed': 'no',
                'notes': '',
            },
        )

        entry = WaitlistEntry.objects.get(guest_name='Test Guest')
        # 2 waiting guests ahead: 15 * (2 + 1) = 45
        self.assertEqual(entry.estimated_wait_minutes, 45)

    def test_check_in_with_empty_queue_uses_base_estimate(self):
        """With no queue, the base estimate should be used."""
        token = get_current_check_in_token()

        response = self.client.post(
            reverse('restaurant:guest_check_in_submit', args=[token]),
            {
                'guest_name': 'Solo Guest',
                'party_size': '1',
                'phone_number': '',
                'location_preference': 'no_preference',
                'seating_preference': 'no_preference',
                'accessibility_requirements': '',
                'high_chair_needed': 'no',
                'notes': '',
            },
        )

        entry = WaitlistEntry.objects.get(guest_name='Solo Guest')
        self.assertEqual(entry.estimated_wait_minutes, 15)

    def test_different_party_sizes_use_different_rules(self):
        """Different party sizes should use their own ETA rules."""
        EtaRule.objects.create(
            min_party_size=3,
            max_party_size=4,
            estimated_wait_minutes=25,
            is_active=True,
        )

        token = get_current_check_in_token()

        # Check in a party of 2
        self.client.post(
            reverse('restaurant:guest_check_in_submit', args=[token]),
            {
                'guest_name': 'Two Guests',
                'party_size': '2',
                'phone_number': '',
                'location_preference': 'no_preference',
                'seating_preference': 'no_preference',
                'accessibility_requirements': '',
                'high_chair_needed': 'no',
                'notes': '',
            },
        )

        # Check in a party of 4
        self.client.post(
            reverse('restaurant:guest_check_in_submit', args=[token]),
            {
                'guest_name': 'Four Guests',
                'party_size': '4',
                'phone_number': '',
                'location_preference': 'no_preference',
                'seating_preference': 'no_preference',
                'accessibility_requirements': '',
                'high_chair_needed': 'no',
                'notes': '',
            },
        )

        two_party = WaitlistEntry.objects.get(guest_name='Two Guests')
        four_party = WaitlistEntry.objects.get(guest_name='Four Guests')

        # Two party: base 15 * (0 + 1) = 15 (they're first)
        self.assertEqual(two_party.estimated_wait_minutes, 15)
        # Four party: base 25 * (1 + 1) = 50 (one party of 2 ahead)
        self.assertEqual(four_party.estimated_wait_minutes, 50)


class TableCompatibilityTests(TestCase):
    """Tests for the check_table_compatibility service function."""

    def setUp(self):
        """Set up test tables and waitlist entries."""
        WaitlistEntry.objects.all().delete()
        RestaurantTable.objects.all().delete()

        # Create a standard compatible table
        self.standard_table = RestaurantTable.objects.create(
            identifier='Standard Table',
            capacity=4,
            location=RestaurantTable.Location.ANY,
            seating_type=RestaurantTable.SeatingType.STANDARD,
            has_accessibility=False,
            can_accommodate_high_chair=False,
        )

        # Create an accessible table
        self.accessible_table = RestaurantTable.objects.create(
            identifier='Accessible Table',
            capacity=4,
            location=RestaurantTable.Location.ANY,
            seating_type=RestaurantTable.SeatingType.STANDARD,
            has_accessibility=True,
            can_accommodate_high_chair=False,
        )

        # Create a booth
        self.booth = RestaurantTable.objects.create(
            identifier='Booth 1',
            capacity=4,
            location=RestaurantTable.Location.ANY,
            seating_type=RestaurantTable.SeatingType.BOOTH,
            has_accessibility=False,
            can_accommodate_high_chair=False,
        )

        # Create an indoor-only table
        self.indoor_table = RestaurantTable.objects.create(
            identifier='Indoor Table',
            capacity=4,
            location=RestaurantTable.Location.INDOOR,
            seating_type=RestaurantTable.SeatingType.STANDARD,
            has_accessibility=False,
            can_accommodate_high_chair=False,
        )

        # Create an outdoor-only table
        self.outdoor_table = RestaurantTable.objects.create(
            identifier='Outdoor Table',
            capacity=4,
            location=RestaurantTable.Location.OUTDOOR,
            seating_type=RestaurantTable.SeatingType.STANDARD,
            has_accessibility=False,
            can_accommodate_high_chair=False,
        )

        # Create a high-chair-capable table
        self.high_chair_table = RestaurantTable.objects.create(
            identifier='High Chair Table',
            capacity=4,
            location=RestaurantTable.Location.ANY,
            seating_type=RestaurantTable.SeatingType.STANDARD,
            has_accessibility=False,
            can_accommodate_high_chair=True,
        )

    def test_type_checking_rejects_non_table_argument(self):
        """Function should raise TypeError if table is not RestaurantTable."""
        entry = WaitlistEntry.objects.create(guest_name='Test', party_size=2)
        with self.assertRaises(TypeError):
            check_table_compatibility('not a table', entry)

    def test_type_checking_rejects_non_entry_argument(self):
        """Function should raise TypeError if entry is not WaitlistEntry."""
        with self.assertRaises(TypeError):
            check_table_compatibility(self.standard_table, 'not an entry')

    def test_capacity_sufficient_returns_compatible(self):
        """Compatible table should return True."""
        entry = WaitlistEntry.objects.create(guest_name='Test', party_size=2)
        self.assertTrue(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_capacity_mismatch_party_too_large(self):
        """Party larger than table capacity should return False."""
        entry = WaitlistEntry.objects.create(guest_name='Test', party_size=5)
        self.assertFalse(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_capacity_equal_to_table_capacity_is_compatible(self):
        """Party size equal to capacity should be compatible."""
        entry = WaitlistEntry.objects.create(guest_name='Test', party_size=4)
        self.assertTrue(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_accessibility_requirement_satisfied(self):
        """Guest with accessibility needs should match accessible table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Accessibility requirements: Wheelchair access',
        )
        self.assertTrue(
            check_table_compatibility(self.accessible_table, entry)
        )

    def test_accessibility_requirement_not_satisfied(self):
        """Guest with accessibility needs should not match non-accessible table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Accessibility requirements: Wheelchair access',
        )
        self.assertFalse(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_no_accessibility_preference_works_with_any_table(self):
        """Guest without accessibility needs should work with any table."""
        entry = WaitlistEntry.objects.create(guest_name='Test', party_size=2)
        self.assertTrue(
            check_table_compatibility(self.standard_table, entry)
        )
        self.assertTrue(
            check_table_compatibility(self.accessible_table, entry)
        )

    def test_indoor_preference_satisfied_by_indoor_table(self):
        """Guest preferring indoor should match indoor table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Indoor/outdoor preference: indoor',
        )
        self.assertTrue(
            check_table_compatibility(self.indoor_table, entry)
        )

    def test_indoor_preference_not_satisfied_by_outdoor_table(self):
        """Guest preferring indoor should not match outdoor table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Indoor/outdoor preference: indoor',
        )
        self.assertFalse(
            check_table_compatibility(self.outdoor_table, entry)
        )

    def test_outdoor_preference_satisfied_by_outdoor_table(self):
        """Guest preferring outdoor should match outdoor table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Indoor/outdoor preference: outdoor',
        )
        self.assertTrue(
            check_table_compatibility(self.outdoor_table, entry)
        )

    def test_outdoor_preference_not_satisfied_by_indoor_table(self):
        """Guest preferring outdoor should not match indoor table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Indoor/outdoor preference: outdoor',
        )
        self.assertFalse(
            check_table_compatibility(self.indoor_table, entry)
        )

    def test_no_location_preference_works_with_any_location(self):
        """Guest with no location preference should work with any location."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Indoor/outdoor preference: no_preference',
        )
        self.assertTrue(
            check_table_compatibility(self.indoor_table, entry)
        )
        self.assertTrue(
            check_table_compatibility(self.outdoor_table, entry)
        )
        self.assertTrue(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_location_any_matches_any_preference(self):
        """Table with 'any' location should match any guest preference."""
        for preference in ['indoor', 'outdoor', 'no_preference']:
            with self.subTest(preference=preference):
                entry = WaitlistEntry.objects.create(
                    guest_name=f'Test {preference}',
                    party_size=2,
                    preference_notes=(
                        f'Indoor/outdoor preference: {preference}'
                    ),
                )
                self.assertTrue(
                    check_table_compatibility(self.standard_table, entry)
                )

    def test_seating_preference_booth_satisfied(self):
        """Guest preferring booth should match booth seating."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Seating preference: Booth',
        )
        self.assertTrue(
            check_table_compatibility(self.booth, entry)
        )

    def test_seating_preference_booth_not_satisfied_by_standard(self):
        """Guest preferring booth should not match standard table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Seating preference: Booth',
        )
        self.assertFalse(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_seating_preference_standard_satisfied(self):
        """Guest preferring standard table should match standard seating."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Seating preference: Standard table',
        )
        self.assertTrue(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_no_seating_preference_works_with_any_seating(self):
        """Guest with no seating preference should work with any seating."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Seating preference: No preference',
        )
        self.assertTrue(
            check_table_compatibility(self.standard_table, entry)
        )
        self.assertTrue(
            check_table_compatibility(self.booth, entry)
        )

    def test_high_chair_requirement_satisfied(self):
        """Guest needing high chair should match high-chair table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='High chair need: yes',
        )
        self.assertTrue(
            check_table_compatibility(self.high_chair_table, entry)
        )

    def test_high_chair_requirement_not_satisfied(self):
        """Guest needing high chair should not match non-high-chair table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='High chair need: yes',
        )
        self.assertFalse(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_no_high_chair_needed_works_with_any_table(self):
        """Guest not needing high chair should work with any table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='High chair need: no',
        )
        self.assertTrue(
            check_table_compatibility(self.standard_table, entry)
        )
        self.assertTrue(
            check_table_compatibility(self.high_chair_table, entry)
        )

    def test_combined_requirements_all_satisfied(self):
        """Table satisfying all requirements should be compatible."""
        # Create a premium table with all features
        premium_table = RestaurantTable.objects.create(
            identifier='Premium',
            capacity=6,
            location=RestaurantTable.Location.INDOOR,
            seating_type=RestaurantTable.SeatingType.BOOTH,
            has_accessibility=True,
            can_accommodate_high_chair=True,
        )

        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=4,
            preference_notes=(
                'Indoor/outdoor preference: indoor\n'
                'Seating preference: Booth\n'
                'Accessibility requirements: Wheelchair access\n'
                'High chair need: yes'
            ),
        )
        self.assertTrue(
            check_table_compatibility(premium_table, entry)
        )

    def test_combined_requirements_capacity_fails(self):
        """Table failing on capacity should be incompatible even with other features."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=5,
            preference_notes=(
                'Indoor/outdoor preference: indoor\n'
                'Seating preference: Booth'
            ),
        )
        # Booth has capacity 4, insufficient for party of 5
        self.assertFalse(
            check_table_compatibility(self.booth, entry)
        )

    def test_combined_requirements_accessibility_fails(self):
        """Table failing on accessibility should be incompatible."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes=(
                'Indoor/outdoor preference: indoor\n'
                'Accessibility requirements: Wheelchair access'
            ),
        )
        # Indoor table is not accessible
        self.assertFalse(
            check_table_compatibility(self.indoor_table, entry)
        )

    def test_combined_requirements_location_fails(self):
        """Table failing on location should be incompatible."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Indoor/outdoor preference: outdoor',
        )
        # Indoor table doesn't match outdoor preference
        self.assertFalse(
            check_table_compatibility(self.indoor_table, entry)
        )

    def test_combined_requirements_seating_fails(self):
        """Table failing on seating should be incompatible."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Seating preference: Booth',
        )
        # Standard table doesn't have booth seating
        self.assertFalse(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_combined_requirements_high_chair_fails(self):
        """Table failing on high chair should be incompatible."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='High chair need: yes',
        )
        # Standard table has no high chair
        self.assertFalse(
            check_table_compatibility(self.standard_table, entry)
        )

    def test_empty_preference_notes_is_compatible(self):
        """Entry with no preference notes should be compatible with any table."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='',
        )
        self.assertTrue(
            check_table_compatibility(self.standard_table, entry)
        )
        self.assertTrue(
            check_table_compatibility(self.accessible_table, entry)
        )
        self.assertTrue(
            check_table_compatibility(self.booth, entry)
        )

    def test_deterministic_function(self):
        """Function should return same result for same inputs."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Indoor/outdoor preference: indoor',
        )

        result1 = check_table_compatibility(self.indoor_table, entry)
        result2 = check_table_compatibility(self.indoor_table, entry)
        result3 = check_table_compatibility(self.indoor_table, entry)

        self.assertEqual(result1, result2)
        self.assertEqual(result2, result3)
        self.assertTrue(result1)

    def test_function_does_not_modify_inputs(self):
        """Function should not modify table or entry objects."""
        entry = WaitlistEntry.objects.create(
            guest_name='Test',
            party_size=2,
            preference_notes='Indoor/outdoor preference: indoor',
        )

        original_preference_notes = entry.preference_notes
        original_party_size = entry.party_size
        original_table_capacity = self.indoor_table.capacity
        original_table_location = self.indoor_table.location

        check_table_compatibility(self.indoor_table, entry)

        self.assertEqual(entry.preference_notes, original_preference_notes)
        self.assertEqual(entry.party_size, original_party_size)
        self.assertEqual(self.indoor_table.capacity, original_table_capacity)
        self.assertEqual(self.indoor_table.location, original_table_location)


class SelectNextGuestForTableTests(TestCase):
    """Tests for the select_next_guest_for_table service function."""

    def setUp(self):
        """Set up a clean table and waitlist state for each test."""
        WaitlistEntry.objects.all().delete()
        RestaurantTable.objects.all().delete()

        self.table = RestaurantTable.objects.create(
            identifier='Standard Table',
            capacity=4,
            location=RestaurantTable.Location.ANY,
            seating_type=RestaurantTable.SeatingType.STANDARD,
            has_accessibility=False,
            can_accommodate_high_chair=False,
        )

    def _make_entry(self, name, minutes_ago, status=WaitlistEntry.Status.WAITING,
                     party_size=2, preference_notes=''):
        checked_in_at = timezone.now() - timezone.timedelta(minutes=minutes_ago)
        return WaitlistEntry.objects.create(
            guest_name=name,
            party_size=party_size,
            status=status,
            checked_in_at=checked_in_at,
            preference_notes=preference_notes,
        )

    def test_type_checking_rejects_non_table_argument(self):
        """Function should raise TypeError if table is not RestaurantTable."""
        with self.assertRaises(TypeError):
            select_next_guest_for_table('not a table')

    def test_single_eligible_guest_is_returned(self):
        """A single eligible waiting guest should be selected."""
        entry = self._make_entry('Alice', minutes_ago=10)
        result = select_next_guest_for_table(self.table)
        self.assertEqual(result, entry)

    def test_no_eligible_guests_returns_none(self):
        """No waitlist entries at all should return None."""
        self.assertIsNone(select_next_guest_for_table(self.table))

    def test_multiple_waiting_guests_ranked_by_check_in_time(self):
        """Among waiting guests, the earliest checked_in_at wins."""
        newer = self._make_entry('Bob', minutes_ago=5)
        older = self._make_entry('Alice', minutes_ago=20)
        middle = self._make_entry('Carol', minutes_ago=10)

        result = select_next_guest_for_table(self.table)

        self.assertEqual(result, older)
        self.assertNotEqual(result, newer)
        self.assertNotEqual(result, middle)

    def test_late_demoted_ranked_behind_all_waiting_guests(self):
        """A late_demoted guest is ranked behind waiting guests even if
        the late_demoted guest checked in much earlier."""
        very_old_late_demoted = self._make_entry(
            'Dave', minutes_ago=100, status=WaitlistEntry.Status.LATE_DEMOTED
        )
        recent_waiting = self._make_entry('Eve', minutes_ago=1)

        result = select_next_guest_for_table(self.table)

        self.assertEqual(result, recent_waiting)
        self.assertNotEqual(result, very_old_late_demoted)

    def test_among_late_demoted_oldest_check_in_wins(self):
        """When only late_demoted guests are eligible, the oldest wins."""
        older_late_demoted = self._make_entry(
            'Frank', minutes_ago=50, status=WaitlistEntry.Status.LATE_DEMOTED
        )
        newer_late_demoted = self._make_entry(
            'Grace', minutes_ago=10, status=WaitlistEntry.Status.LATE_DEMOTED
        )

        result = select_next_guest_for_table(self.table)

        self.assertEqual(result, older_late_demoted)
        self.assertNotEqual(result, newer_late_demoted)

    def test_incompatible_guests_are_excluded(self):
        """Guests incompatible with the table (e.g. party too large) are
        excluded even if they would otherwise rank first."""
        incompatible = self._make_entry(
            'Huge Party', minutes_ago=100, party_size=10
        )
        compatible = self._make_entry('Small Party', minutes_ago=5, party_size=2)

        result = select_next_guest_for_table(self.table)

        self.assertEqual(result, compatible)
        self.assertNotEqual(result, incompatible)

    def test_other_statuses_are_excluded(self):
        """Entries with statuses other than waiting/late_demoted are
        excluded entirely."""
        self._make_entry('Seated', minutes_ago=100, status=WaitlistEntry.Status.SEATED)
        self._make_entry('Cancelled', minutes_ago=100, status=WaitlistEntry.Status.CANCELLED)
        self._make_entry('Notified', minutes_ago=100, status=WaitlistEntry.Status.NOTIFIED)

        result = select_next_guest_for_table(self.table)

        self.assertIsNone(result)

    def test_function_does_not_mutate_or_assign(self):
        """Function should not change the table or entry statuses/fields."""
        entry = self._make_entry('Alice', minutes_ago=10)
        original_status = entry.status
        original_assigned_table = entry.assigned_table
        original_table_status = self.table.status

        select_next_guest_for_table(self.table)

        entry.refresh_from_db()
        self.table.refresh_from_db()

        self.assertEqual(entry.status, original_status)
        self.assertEqual(entry.assigned_table, original_assigned_table)
        self.assertIsNone(entry.assigned_table)
        self.assertEqual(self.table.status, original_table_status)


class MatchTableAutomaticallyTests(TestCase):
    """Tests for the match_table_automatically service function."""

    def setUp(self):
        """Set up a clean table and waitlist state for each test."""
        WaitlistEntry.objects.all().delete()
        RestaurantTable.objects.all().delete()

        self.table = RestaurantTable.objects.create(
            identifier='Standard Table',
            capacity=4,
            status=RestaurantTable.Status.FREE,
            location=RestaurantTable.Location.ANY,
            seating_type=RestaurantTable.SeatingType.STANDARD,
            has_accessibility=False,
            can_accommodate_high_chair=False,
        )

    def _make_entry(self, name, minutes_ago, status=WaitlistEntry.Status.WAITING,
                     party_size=2, preference_notes=''):
        checked_in_at = timezone.now() - timezone.timedelta(minutes=minutes_ago)
        return WaitlistEntry.objects.create(
            guest_name=name,
            party_size=party_size,
            status=status,
            checked_in_at=checked_in_at,
            preference_notes=preference_notes,
        )

    def test_type_checking_rejects_non_table_argument(self):
        """Function should raise TypeError if table is not RestaurantTable."""
        with self.assertRaises(TypeError):
            match_table_automatically('not a table')

    def test_successful_match_assigns_guest_and_reserves_table(self):
        """A compatible waiting guest is assigned to the table, notified,
        and the table becomes reserved."""
        entry = self._make_entry('Alice', minutes_ago=10)

        result = match_table_automatically(self.table)

        self.assertEqual(result, entry)

        entry.refresh_from_db()
        self.table.refresh_from_db()

        self.assertEqual(entry.assigned_table, self.table)
        self.assertEqual(entry.status, WaitlistEntry.Status.NOTIFIED)
        self.assertIsNotNone(entry.notified_at)
        self.assertEqual(self.table.status, RestaurantTable.Status.RESERVED)

    def test_no_eligible_guest_leaves_table_free(self):
        """When no compatible guest exists, the table remains free and
        nothing is mutated."""
        incompatible = self._make_entry('Huge Party', minutes_ago=5, party_size=10)

        result = match_table_automatically(self.table)

        self.assertIsNone(result)

        incompatible.refresh_from_db()
        self.table.refresh_from_db()

        self.assertEqual(self.table.status, RestaurantTable.Status.FREE)
        self.assertIsNone(incompatible.assigned_table)
        self.assertEqual(incompatible.status, WaitlistEntry.Status.WAITING)
        self.assertIsNone(incompatible.notified_at)

    def test_table_not_free_is_not_matched(self):
        """If the table's status is not free, no matching logic runs even
        if a compatible guest is waiting."""
        self.table.status = RestaurantTable.Status.OCCUPIED
        self.table.save(update_fields=['status'])
        entry = self._make_entry('Alice', minutes_ago=10)

        result = match_table_automatically(self.table)

        self.assertIsNone(result)

        entry.refresh_from_db()
        self.table.refresh_from_db()

        self.assertIsNone(entry.assigned_table)
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)
        self.assertEqual(self.table.status, RestaurantTable.Status.OCCUPIED)

    def test_correct_guest_selected_among_multiple_candidates(self):
        """The highest-priority compatible guest (per
        select_next_guest_for_table) is the one matched."""
        newer = self._make_entry('Bob', minutes_ago=5)
        older = self._make_entry('Alice', minutes_ago=20)
        incompatible_but_older_still = self._make_entry(
            'Huge Party', minutes_ago=100, party_size=10
        )
        late_demoted = self._make_entry(
            'Dave', minutes_ago=200, status=WaitlistEntry.Status.LATE_DEMOTED
        )

        result = match_table_automatically(self.table)

        self.assertEqual(result, older)

        older.refresh_from_db()
        self.table.refresh_from_db()
        newer.refresh_from_db()
        late_demoted.refresh_from_db()

        self.assertEqual(older.status, WaitlistEntry.Status.NOTIFIED)
        self.assertEqual(older.assigned_table, self.table)
        self.assertEqual(self.table.status, RestaurantTable.Status.RESERVED)

        # Others remain untouched.
        self.assertEqual(newer.status, WaitlistEntry.Status.WAITING)
        self.assertIsNone(newer.assigned_table)
        self.assertEqual(late_demoted.status, WaitlistEntry.Status.LATE_DEMOTED)
        self.assertIsNone(late_demoted.assigned_table)


class StaffWaitlistViewTests(TestCase):
    password = 'usable-test-password-123'

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff_user = user_model.objects.create_user(
            username='waitlist-staff',
            password=cls.password,
        )
        WorkerProfile.objects.create(
            user=cls.staff_user,
            role=WorkerProfile.Role.STAFF,
        )
        cls.no_role_user = user_model.objects.create_user(
            username='waitlist-plain',
            password=cls.password,
        )
        cls.table = RestaurantTable.objects.create(
            identifier='T1',
            capacity=4,
        )

    def _create_entry(self, **kwargs):
        defaults = {
            'guest_name': 'Guest',
            'party_size': 2,
        }
        defaults.update(kwargs)
        return WaitlistEntry.objects.create(**defaults)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_staff_or_manager_required_denies_no_role_user(self):
        self.client.force_login(self.no_role_user)

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_view_page(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="waitlist-marker"')

    def test_active_statuses_are_shown_with_expected_fields(self):
        self.client.force_login(self.staff_user)
        entry = self._create_entry(
            guest_name='Alice Waiting',
            party_size=3,
            estimated_wait_minutes=25,
            preference_notes='Window seat please',
            status=WaitlistEntry.Status.WAITING,
            assigned_table=self.table,
        )

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertContains(response, entry.guest_name)
        self.assertContains(response, '25')
        self.assertContains(response, 'Window seat please')
        self.assertContains(response, entry.get_status_display())
        self.assertContains(response, self.table.identifier)

    def test_inactive_statuses_are_excluded_by_default(self):
        self.client.force_login(self.staff_user)
        visible = self._create_entry(
            guest_name='Visible Guest',
            status=WaitlistEntry.Status.NOTIFIED,
        )
        excluded_statuses = [
            WaitlistEntry.Status.SEATED,
            WaitlistEntry.Status.CANCELLED,
            WaitlistEntry.Status.NO_SHOW,
            WaitlistEntry.Status.LEFT,
        ]
        excluded_entries = [
            self._create_entry(
                guest_name=f'Excluded {status}',
                status=status,
            )
            for status in excluded_statuses
        ]

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertContains(response, visible.guest_name)
        for excluded_entry in excluded_entries:
            self.assertNotContains(response, excluded_entry.guest_name)

    def test_all_active_statuses_are_shown(self):
        self.client.force_login(self.staff_user)
        active_statuses = [
            WaitlistEntry.Status.WAITING,
            WaitlistEntry.Status.NOTIFIED,
            WaitlistEntry.Status.ARRIVED,
            WaitlistEntry.Status.LATE_DEMOTED,
        ]
        entries = [
            self._create_entry(guest_name=f'Guest {status}', status=status)
            for status in active_statuses
        ]

        response = self.client.get(reverse('restaurant:waitlist'))

        for entry in entries:
            self.assertContains(response, entry.guest_name)

    def test_waiting_and_late_demoted_are_ordered_first_by_checked_in_at(self):
        self.client.force_login(self.staff_user)
        now = timezone.now()

        notified = self._create_entry(
            guest_name='Notified Early',
            status=WaitlistEntry.Status.NOTIFIED,
            checked_in_at=now - timezone.timedelta(minutes=50),
        )
        late_demoted = self._create_entry(
            guest_name='Late Demoted',
            status=WaitlistEntry.Status.LATE_DEMOTED,
            checked_in_at=now - timezone.timedelta(minutes=40),
        )
        oldest_waiting = self._create_entry(
            guest_name='Oldest Waiting',
            status=WaitlistEntry.Status.WAITING,
            checked_in_at=now - timezone.timedelta(minutes=30),
        )
        newest_waiting = self._create_entry(
            guest_name='Newest Waiting',
            status=WaitlistEntry.Status.WAITING,
            checked_in_at=now - timezone.timedelta(minutes=10),
        )

        response = self.client.get(reverse('restaurant:waitlist'))

        ordered_names = [entry.guest_name for entry in response.context['entries']]

        self.assertEqual(
            ordered_names,
            [
                late_demoted.guest_name,
                oldest_waiting.guest_name,
                newest_waiting.guest_name,
                notified.guest_name,
            ],
        )

    def test_filter_waiting_only_shows_waiting_entries(self):
        self.client.force_login(self.staff_user)
        waiting = self._create_entry(
            guest_name='Waiting Guest',
            status=WaitlistEntry.Status.WAITING,
        )
        notified = self._create_entry(
            guest_name='Notified Guest',
            status=WaitlistEntry.Status.NOTIFIED,
        )

        response = self.client.get(reverse('restaurant:waitlist'), {'status': 'waiting'})

        self.assertContains(response, waiting.guest_name)
        self.assertNotContains(response, notified.guest_name)

    def test_page_links_back_to_staff_dashboard(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('restaurant:waitlist'))

        self.assertContains(response, reverse('restaurant:staff_landing'))


class GuestStatusTransitionServiceTests(TestCase):
    """Tests for the guest status transition service functions."""

    def setUp(self):
        self.table = RestaurantTable.objects.create(
            identifier='T-Status',
            capacity=4,
            status=RestaurantTable.Status.RESERVED,
        )

    def _make_entry(self, status, assigned_table=None, **kwargs):
        defaults = {
            'guest_name': 'Guest',
            'party_size': 2,
            'status': status,
            'assigned_table': assigned_table,
        }
        defaults.update(kwargs)
        return WaitlistEntry.objects.create(**defaults)

    # -- mark_guest_arrived --

    def test_mark_guest_arrived_from_waiting_sets_status_and_timestamp(self):
        entry = self._make_entry(WaitlistEntry.Status.WAITING)

        result = mark_guest_arrived(entry)

        entry.refresh_from_db()
        self.assertEqual(result, entry)
        self.assertEqual(entry.status, WaitlistEntry.Status.ARRIVED)
        self.assertIsNotNone(entry.arrived_at)

    def test_mark_guest_arrived_from_notified_succeeds(self):
        entry = self._make_entry(WaitlistEntry.Status.NOTIFIED)

        mark_guest_arrived(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.ARRIVED)

    def test_mark_guest_arrived_from_late_demoted_succeeds(self):
        entry = self._make_entry(WaitlistEntry.Status.LATE_DEMOTED)

        mark_guest_arrived(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.ARRIVED)

    def test_mark_guest_arrived_from_seated_is_rejected(self):
        entry = self._make_entry(
            WaitlistEntry.Status.SEATED, assigned_table=self.table
        )

        with self.assertRaises(InvalidStatusTransitionError):
            mark_guest_arrived(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.SEATED)
        self.assertIsNone(entry.arrived_at)

    # -- mark_guest_seated --

    def test_mark_guest_seated_requires_assigned_table(self):
        entry = self._make_entry(WaitlistEntry.Status.ARRIVED, assigned_table=None)

        with self.assertRaises(InvalidStatusTransitionError):
            mark_guest_seated(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.ARRIVED)
        self.assertIsNone(entry.seated_at)

    def test_mark_guest_seated_sets_status_timestamp_and_occupies_table(self):
        entry = self._make_entry(
            WaitlistEntry.Status.ARRIVED, assigned_table=self.table
        )

        result = mark_guest_seated(entry)

        entry.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(result, entry)
        self.assertEqual(entry.status, WaitlistEntry.Status.SEATED)
        self.assertIsNotNone(entry.seated_at)
        self.assertEqual(self.table.status, RestaurantTable.Status.OCCUPIED)

    def test_mark_guest_seated_from_notified_succeeds(self):
        entry = self._make_entry(
            WaitlistEntry.Status.NOTIFIED, assigned_table=self.table
        )

        mark_guest_seated(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.SEATED)

    def test_mark_guest_seated_from_waiting_is_rejected(self):
        entry = self._make_entry(
            WaitlistEntry.Status.WAITING, assigned_table=self.table
        )

        with self.assertRaises(InvalidStatusTransitionError):
            mark_guest_seated(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)

    # -- mark_guest_left --

    def test_mark_guest_left_from_seated_sets_status_timestamp_and_cleans_table(self):
        entry = self._make_entry(
            WaitlistEntry.Status.SEATED, assigned_table=self.table
        )
        self.table.status = RestaurantTable.Status.OCCUPIED
        self.table.save(update_fields=['status'])

        result = mark_guest_left(entry)

        entry.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(result, entry)
        self.assertEqual(entry.status, WaitlistEntry.Status.LEFT)
        self.assertIsNotNone(entry.left_at)
        self.assertEqual(self.table.status, RestaurantTable.Status.CLEANING)
        # assigned_table and history are preserved for record-keeping.
        self.assertEqual(entry.assigned_table, self.table)

    def test_mark_guest_left_from_waiting_is_rejected(self):
        entry = self._make_entry(
            WaitlistEntry.Status.WAITING, assigned_table=self.table
        )

        with self.assertRaises(InvalidStatusTransitionError):
            mark_guest_left(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)

    def test_mark_guest_left_from_arrived_is_rejected(self):
        entry = self._make_entry(
            WaitlistEntry.Status.ARRIVED, assigned_table=self.table
        )

        with self.assertRaises(InvalidStatusTransitionError):
            mark_guest_left(entry)

    # -- mark_guest_cancelled --

    def test_mark_guest_cancelled_without_table_does_not_touch_any_table(self):
        entry = self._make_entry(WaitlistEntry.Status.WAITING, assigned_table=None)
        self.table.status = RestaurantTable.Status.RESERVED
        self.table.save(update_fields=['status'])

        result = mark_guest_cancelled(entry)

        entry.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(result, entry)
        self.assertEqual(entry.status, WaitlistEntry.Status.CANCELLED)
        self.assertIsNotNone(entry.cancelled_at)
        self.assertEqual(self.table.status, RestaurantTable.Status.RESERVED)

    def test_mark_guest_cancelled_with_assigned_table_frees_it(self):
        entry = self._make_entry(
            WaitlistEntry.Status.NOTIFIED, assigned_table=self.table
        )
        self.table.status = RestaurantTable.Status.RESERVED
        self.table.save(update_fields=['status'])

        mark_guest_cancelled(entry)

        entry.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.CANCELLED)
        self.assertEqual(self.table.status, RestaurantTable.Status.FREE)

    def test_mark_guest_cancelled_from_seated_is_rejected(self):
        entry = self._make_entry(
            WaitlistEntry.Status.SEATED, assigned_table=self.table
        )

        with self.assertRaises(InvalidStatusTransitionError):
            mark_guest_cancelled(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.SEATED)

    def test_mark_guest_cancelled_from_arrived_succeeds(self):
        entry = self._make_entry(WaitlistEntry.Status.ARRIVED, assigned_table=None)

        mark_guest_cancelled(entry)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.CANCELLED)

    # -- mark_guest_no_show --

    def test_mark_guest_no_show_without_table_does_not_touch_any_table(self):
        entry = self._make_entry(WaitlistEntry.Status.WAITING, assigned_table=None)
        self.table.status = RestaurantTable.Status.RESERVED
        self.table.save(update_fields=['status'])

        result = mark_guest_no_show(entry)

        entry.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(result, entry)
        self.assertEqual(entry.status, WaitlistEntry.Status.NO_SHOW)
        self.assertIsNotNone(entry.no_show_at)
        self.assertEqual(self.table.status, RestaurantTable.Status.RESERVED)

    def test_mark_guest_no_show_with_assigned_table_frees_it(self):
        entry = self._make_entry(
            WaitlistEntry.Status.NOTIFIED, assigned_table=self.table
        )
        self.table.status = RestaurantTable.Status.RESERVED
        self.table.save(update_fields=['status'])

        mark_guest_no_show(entry)

        entry.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.NO_SHOW)
        self.assertEqual(self.table.status, RestaurantTable.Status.FREE)

    def test_mark_guest_no_show_from_seated_is_rejected(self):
        entry = self._make_entry(
            WaitlistEntry.Status.SEATED, assigned_table=self.table
        )

        with self.assertRaises(InvalidStatusTransitionError):
            mark_guest_no_show(entry)

    def test_transition_functions_reject_non_waitlist_entry_argument(self):
        with self.assertRaises(TypeError):
            mark_guest_arrived('not an entry')
        with self.assertRaises(TypeError):
            mark_guest_seated('not an entry')
        with self.assertRaises(TypeError):
            mark_guest_left('not an entry')
        with self.assertRaises(TypeError):
            mark_guest_cancelled('not an entry')
        with self.assertRaises(TypeError):
            mark_guest_no_show('not an entry')


class WaitlistEntryActionViewTests(TestCase):
    """Tests for the staff waitlist entry status action view."""

    password = 'usable-test-password-123'

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff_user = user_model.objects.create_user(
            username='action-staff',
            password=cls.password,
        )
        WorkerProfile.objects.create(
            user=cls.staff_user,
            role=WorkerProfile.Role.STAFF,
        )
        cls.no_role_user = user_model.objects.create_user(
            username='action-plain',
            password=cls.password,
        )

    def setUp(self):
        self.table = RestaurantTable.objects.create(
            identifier='T-Action',
            capacity=4,
            status=RestaurantTable.Status.RESERVED,
        )

    def _action_url(self, entry, action):
        return reverse(
            'restaurant:waitlist_entry_action', args=[entry.pk, action]
        )

    def test_anonymous_user_is_redirected_to_login(self):
        entry = WaitlistEntry.objects.create(
            guest_name='Guest', party_size=2,
            status=WaitlistEntry.Status.WAITING,
        )

        response = self.client.post(self._action_url(entry, 'arrived'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)

    def test_no_role_user_is_denied(self):
        self.client.force_login(self.no_role_user)
        entry = WaitlistEntry.objects.create(
            guest_name='Guest', party_size=2,
            status=WaitlistEntry.Status.WAITING,
        )

        response = self.client.post(self._action_url(entry, 'arrived'))

        self.assertEqual(response.status_code, 403)

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)

    def test_staff_user_can_mark_guest_arrived(self):
        self.client.force_login(self.staff_user)
        entry = WaitlistEntry.objects.create(
            guest_name='Guest', party_size=2,
            status=WaitlistEntry.Status.WAITING,
        )

        response = self.client.post(self._action_url(entry, 'arrived'))

        self.assertRedirects(response, reverse('restaurant:waitlist'))
        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.ARRIVED)
        self.assertIsNotNone(entry.arrived_at)

    def test_staff_user_can_mark_guest_seated_with_assigned_table(self):
        self.client.force_login(self.staff_user)
        entry = WaitlistEntry.objects.create(
            guest_name='Guest', party_size=2,
            status=WaitlistEntry.Status.ARRIVED,
            assigned_table=self.table,
        )

        response = self.client.post(self._action_url(entry, 'seated'))

        self.assertRedirects(response, reverse('restaurant:waitlist'))
        entry.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.SEATED)
        self.assertEqual(self.table.status, RestaurantTable.Status.OCCUPIED)

    def test_invalid_transition_shows_error_and_does_not_change_state(self):
        self.client.force_login(self.staff_user)
        entry = WaitlistEntry.objects.create(
            guest_name='Guest', party_size=2,
            status=WaitlistEntry.Status.SEATED,
            assigned_table=self.table,
        )

        response = self.client.post(
            self._action_url(entry, 'arrived'), follow=True
        )

        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.SEATED)
        messages_list = list(response.context['messages'])
        self.assertTrue(any(
            'Cannot transition' in str(message) for message in messages_list
        ))

    def test_unknown_action_returns_404(self):
        self.client.force_login(self.staff_user)
        entry = WaitlistEntry.objects.create(
            guest_name='Guest', party_size=2,
            status=WaitlistEntry.Status.WAITING,
        )

        response = self.client.post(self._action_url(entry, 'bogus'))

        self.assertEqual(response.status_code, 404)

    def test_get_request_does_not_mutate_state(self):
        self.client.force_login(self.staff_user)
        entry = WaitlistEntry.objects.create(
            guest_name='Guest', party_size=2,
            status=WaitlistEntry.Status.WAITING,
        )

        self.client.get(self._action_url(entry, 'arrived'))

        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.WAITING)
