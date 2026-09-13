from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from restaurant.models import EtaRule, RestaurantSettings, RestaurantTable, WorkerProfile

# Local-development-only credentials. These are intentionally simple and
# clearly marked as dev-only in the command output - never use these for a
# real deployment.
DEV_PASSWORD = 'devpassword123'

STAFF_USERS = [
    {
        'username': 'staff_demo',
        'first_name': 'Sam',
        'last_name': 'Staff',
        'role': WorkerProfile.Role.STAFF,
    },
    {
        'username': 'manager_demo',
        'first_name': 'Mary',
        'last_name': 'Manager',
        'role': WorkerProfile.Role.MANAGER,
    },
]

ETA_RULES = [
    {'min_party_size': 1, 'max_party_size': 2, 'estimated_wait_minutes': 10},
    {'min_party_size': 3, 'max_party_size': 4, 'estimated_wait_minutes': 20},
    {'min_party_size': 5, 'max_party_size': 6, 'estimated_wait_minutes': 30},
    {'min_party_size': 7, 'max_party_size': None, 'estimated_wait_minutes': 45},
]

TABLES = [
    {
        'identifier': 'T1',
        'capacity': 2,
        'location': RestaurantTable.Location.INDOOR,
        'seating_type': RestaurantTable.SeatingType.STANDARD,
        'has_accessibility': False,
        'can_accommodate_high_chair': False,
    },
    {
        'identifier': 'T2',
        'capacity': 2,
        'location': RestaurantTable.Location.INDOOR,
        'seating_type': RestaurantTable.SeatingType.BAR,
        'has_accessibility': False,
        'can_accommodate_high_chair': False,
    },
    {
        'identifier': 'T3',
        'capacity': 4,
        'location': RestaurantTable.Location.INDOOR,
        'seating_type': RestaurantTable.SeatingType.BOOTH,
        'has_accessibility': True,
        'can_accommodate_high_chair': True,
    },
    {
        'identifier': 'T4',
        'capacity': 4,
        'location': RestaurantTable.Location.OUTDOOR,
        'seating_type': RestaurantTable.SeatingType.STANDARD,
        'has_accessibility': False,
        'can_accommodate_high_chair': True,
    },
    {
        'identifier': 'T5',
        'capacity': 6,
        'location': RestaurantTable.Location.INDOOR,
        'seating_type': RestaurantTable.SeatingType.STANDARD,
        'has_accessibility': True,
        'can_accommodate_high_chair': False,
    },
    {
        'identifier': 'T6',
        'capacity': 8,
        'location': RestaurantTable.Location.ANY,
        'seating_type': RestaurantTable.SeatingType.STANDARD,
        'has_accessibility': False,
        'can_accommodate_high_chair': False,
    },
]


class Command(BaseCommand):
    help = (
        'Populate the local database with realistic sample data for demos '
        'and manual testing (restaurant settings, staff/manager users, ETA '
        'rules, and tables). Safe to run multiple times.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        settings_row = RestaurantSettings.get_active()
        if not settings_row.name or settings_row.name == 'My Restaurant':
            settings_row.name = 'NextTable Demo Restaurant'
            settings_row.grace_period_minutes = 30
            settings_row.save()
        self.stdout.write(self.style.SUCCESS(
            f'Restaurant settings ready: "{settings_row.name}"'
        ))

        created_usernames = []
        User = get_user_model()
        for spec in STAFF_USERS:
            user, created = User.objects.get_or_create(
                username=spec['username'],
                defaults={
                    'first_name': spec['first_name'],
                    'last_name': spec['last_name'],
                },
            )
            if created:
                user.set_password(DEV_PASSWORD)
                user.save()
            WorkerProfile.objects.update_or_create(
                user=user,
                defaults={'role': spec['role']},
            )
            created_usernames.append((spec['username'], spec['role']))

        for min_size, max_size, wait in [
            (r['min_party_size'], r['max_party_size'], r['estimated_wait_minutes'])
            for r in ETA_RULES
        ]:
            EtaRule.objects.update_or_create(
                min_party_size=min_size,
                max_party_size=max_size,
                defaults={
                    'estimated_wait_minutes': wait,
                    'is_active': True,
                },
            )

        for spec in TABLES:
            identifier = spec['identifier']
            defaults = {k: v for k, v in spec.items() if k != 'identifier'}
            RestaurantTable.objects.update_or_create(
                identifier=identifier,
                defaults=defaults,
            )

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(ETA_RULES)} ETA rule(s) and {len(TABLES)} table(s).'
        ))

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Seeded staff/manager accounts (LOCAL DEVELOPMENT ONLY - '
            'do not use in production):'
        ))
        for username, role in created_usernames:
            self.stdout.write(f'  - {username} (role={role}), password={DEV_PASSWORD}')
