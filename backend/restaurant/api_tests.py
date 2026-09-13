from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .check_in_tokens import get_current_check_in_token, is_valid_check_in_token
from .models import EtaRule, RestaurantTable, WaitlistEntry, WorkerProfile


def _create_worker(username, role, password='pass12345!'):
    user = get_user_model().objects.create_user(username=username, password=password)
    WorkerProfile.objects.create(user=user, role=role)
    return user


class AuthApiTests(TestCase):
    def test_login_returns_role_and_sets_session(self):
        _create_worker('staffer', WorkerProfile.Role.STAFF)

        response = self.client.post(
            reverse('restaurant_api:login'),
            {'username': 'staffer', 'password': 'pass12345!'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['role'], 'staff')

    def test_login_rejects_bad_credentials(self):
        response = self.client.post(
            reverse('restaurant_api:login'),
            {'username': 'nope', 'password': 'wrong'},
        )
        self.assertEqual(response.status_code, 400)

    def test_me_requires_authentication(self):
        response = self.client.get(reverse('restaurant_api:me'))
        self.assertEqual(response.status_code, 403)


class WaitlistApiTests(TestCase):
    def setUp(self):
        self.staff = _create_worker('staffer2', WorkerProfile.Role.STAFF)
        self.client.force_login(self.staff)

    def test_waitlist_requires_staff_role(self):
        anon_client = self.client_class()
        response = anon_client.get(reverse('restaurant_api:waitlist'))
        self.assertEqual(response.status_code, 403)

    def test_current_check_in_token_is_public(self):
        anon_client = self.client_class()
        response = anon_client.get(reverse('restaurant_api:current_check_in_token'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(is_valid_check_in_token(response.json()['token']))

    def test_waitlist_lists_active_entries(self):
        WaitlistEntry.objects.create(guest_name='Ada', party_size=2)

        response = self.client.get(reverse('restaurant_api:waitlist'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['entries']), 1)
        self.assertEqual(response.json()['entries'][0]['guest_name'], 'Ada')

    def test_waitlist_entry_action_transitions_status(self):
        entry = WaitlistEntry.objects.create(guest_name='Bo', party_size=1)

        response = self.client.post(
            reverse(
                'restaurant_api:waitlist_entry_action',
                args=[entry.id, 'arrived'],
            )
        )

        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.ARRIVED)


class ManagerApiTests(TestCase):
    def setUp(self):
        self.manager = _create_worker('boss', WorkerProfile.Role.MANAGER)
        self.client.force_login(self.manager)

    def test_staff_cannot_access_manager_endpoints(self):
        staff = _create_worker('staffer3', WorkerProfile.Role.STAFF)
        client = self.client_class()
        client.force_login(staff)

        response = client.get(reverse('restaurant_api:table_config'))
        self.assertEqual(response.status_code, 403)

    def test_table_config_create_and_list(self):
        response = self.client.post(
            reverse('restaurant_api:table_config'),
            {'identifier': 'T1', 'capacity': 4, 'status': RestaurantTable.Status.FREE},
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.get(reverse('restaurant_api:table_config'))
        self.assertEqual(len(response.json()), 1)

    def test_eta_rule_create(self):
        # migration 0006 seeds default ETA rules covering party sizes 1+,
        # so use a range those defaults don't cover to avoid the "active
        # rules cannot overlap" validation in EtaRuleForm.
        before_count = EtaRule.objects.count()

        response = self.client.post(
            reverse('restaurant_api:eta_rules'),
            {
                'min_party_size': 1,
                'max_party_size': 4,
                'estimated_wait_minutes': 10,
                'is_active': False,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(EtaRule.objects.count(), before_count + 1)


class GuestCheckInApiTests(TestCase):
    def test_check_in_with_invalid_token_is_forbidden(self):
        response = self.client.get(
            reverse('restaurant_api:check_in', args=['bad-token'])
        )
        self.assertEqual(response.status_code, 403)

    def test_check_in_submit_creates_entry_and_status_is_fetchable(self):
        token = get_current_check_in_token()

        response = self.client.post(
            reverse('restaurant_api:check_in', args=[token]),
            {'guest_name': 'Cy', 'party_size': 2},
        )
        self.assertEqual(response.status_code, 201)
        public_identifier = response.json()['public_identifier']

        status_response = self.client.get(
            reverse('restaurant_api:check_in_status', args=[public_identifier])
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()['guest_name'], 'Cy')
        self.assertTrue(status_response.json()['can_cancel'])

    def test_check_in_cancel(self):
        token = get_current_check_in_token()
        self.client.post(
            reverse('restaurant_api:check_in', args=[token]),
            {'guest_name': 'Dee', 'party_size': 3},
        )
        entry = WaitlistEntry.objects.get(guest_name='Dee')

        response = self.client.post(
            reverse('restaurant_api:check_in_cancel', args=[entry.public_identifier])
        )
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.CANCELLED)
