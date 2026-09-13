from django.contrib import admin

from .models import RestaurantSettings, WorkerProfile


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
