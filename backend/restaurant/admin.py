from django.contrib import admin

from .models import (
    EtaRule,
    RestaurantSettings,
    RestaurantTable,
    WaitlistEntry,
    WorkerProfile,
)


@admin.register(RestaurantSettings)
class RestaurantSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'grace_period_minutes',
        'current_check_in_token',
        'check_in_token_generated_at',
        'updated_at',
    )
    readonly_fields = ('created_at', 'updated_at')

    def has_add_permission(self, request):
        # RestaurantSettings is a singleton (see restaurant/models.py); once
        # the row exists, prevent creating additional rows from the admin.
        return not RestaurantSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Never allow deleting the only settings row from the admin.
        return False


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'updated_at')
    list_filter = ('role',)
    search_fields = (
        'user__username',
        'user__email',
        'user__first_name',
        'user__last_name',
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RestaurantTable)
class RestaurantTableAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'capacity', 'status', 'updated_at')
    list_filter = ('status', 'capacity')
    search_fields = ('identifier',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(EtaRule)
class EtaRuleAdmin(admin.ModelAdmin):
    list_display = (
        'min_party_size',
        'max_party_size',
        'estimated_wait_minutes',
        'is_active',
        'updated_at',
    )
    list_filter = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = (
        'guest_name',
        'party_size',
        'status',
        'assigned_table',
        'checked_in_at',
        'updated_at',
    )
    list_filter = ('status', 'assigned_table', 'party_size')
    search_fields = (
        'guest_name',
        'contact_text',
        'preference_notes',
        'assigned_table__identifier',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'checked_in_at',
        'notified_at',
        'arrived_at',
        'seated_at',
        'cancelled_at',
        'no_show_at',
        'left_at',
    )
