from django.contrib.auth import get_user_model
from rest_framework import serializers

from ..models import EtaRule, RestaurantSettings, RestaurantTable, WaitlistEntry, WorkerProfile


class RestaurantTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantTable
        fields = [
            'id',
            'identifier',
            'capacity',
            'status',
            'location',
            'seating_type',
            'has_accessibility',
            'can_accommodate_high_chair',
        ]


class WaitlistEntrySerializer(serializers.ModelSerializer):
    assigned_table = RestaurantTableSerializer(read_only=True)

    class Meta:
        model = WaitlistEntry
        fields = [
            'id',
            'guest_name',
            'party_size',
            'public_identifier',
            'estimated_wait_minutes',
            'contact_text',
            'preference_notes',
            'status',
            'assigned_table',
            'checked_in_at',
            'notified_at',
            'arrived_at',
            'seated_at',
            'cancelled_at',
            'no_show_at',
            'left_at',
        ]


class EtaRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = EtaRule
        fields = [
            'id',
            'min_party_size',
            'max_party_size',
            'estimated_wait_minutes',
            'is_active',
        ]


class RestaurantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantSettings
        fields = ['grace_period_minutes']


class WorkerSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(
        source='worker_profile.role', choices=WorkerProfile.Role.choices
    )

    class Meta:
        model = get_user_model()
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'role',
        ]
