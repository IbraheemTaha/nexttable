from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from .auth import user_is_manager, user_is_staff_or_manager
from .models import (
    SINGLETON_PK,
    RestaurantSettings,
    RestaurantTable,
    WaitlistEntry,
    WorkerProfile,
)


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
