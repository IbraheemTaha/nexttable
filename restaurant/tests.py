from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .auth import user_is_manager, user_is_staff_or_manager
from .models import SINGLETON_PK, RestaurantSettings, WorkerProfile


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
