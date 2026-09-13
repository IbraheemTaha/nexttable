from django.db import models
from django.conf import settings

# Fixed primary key used to enforce the RestaurantSettings singleton.
#
# NextTable manages a single restaurant (docs/plan.md section 3: no
# multi-tenancy), so there must only ever be one RestaurantSettings row.
# We enforce this by always saving the row under this fixed primary key
# instead of relying on application code to remember not to create a
# second row.
SINGLETON_PK = 1


class RestaurantSettings(models.Model):
    """The single restaurant's general configuration.

    This is a singleton model: only one row of this table should ever
    exist, and it always lives at primary key `SINGLETON_PK` (see
    `save()` below). Use `RestaurantSettings.get_active()` to fetch (and,
    on first use, lazily create) that row rather than querying or
    creating instances directly.
    """

    name = models.CharField(max_length=255)

    # docs/plan.md section 10 (Late Guest / Grace Period): default grace
    # period is 30 minutes, configurable by a Manager (configuration UI is
    # out of scope for this issue - see docs/tasks.md issue #14).
    grace_period_minutes = models.PositiveIntegerField(default=30)

    # docs/plan.md section 15 (Daily QR / URL): storage for the daily
    # check-in token. This issue only defines the fields; the generation/
    # rotation algorithm is implemented in docs/tasks.md issue #10.
    current_check_in_token = models.CharField(
        max_length=255, blank=True, null=True
    )
    check_in_token_generated_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Enforce the singleton pattern: always write to the same fixed
        # primary key so there can only ever be one RestaurantSettings row,
        # no matter how this instance was constructed.
        self.pk = SINGLETON_PK

        # If this instance was constructed directly (e.g.
        # RestaurantSettings(name=...)) rather than via get_active(), it
        # has no `created_at` set. Forcing the pk above means that, when a
        # row already exists, Django routes this save() to an UPDATE
        # (matching the existing pk) rather than an INSERT. `created_at`
        # is `auto_now_add`, which Django only populates on INSERT, so on
        # the UPDATE path it would stay None and the database would
        # reject the NULL write with an IntegrityError. Preserve the
        # existing row's `created_at` in that case so the UPDATE succeeds
        # and doesn't clobber the original creation timestamp.
        if self.created_at is None:
            existing_created_at = (
                RestaurantSettings.objects.filter(pk=SINGLETON_PK)
                .values_list('created_at', flat=True)
                .first()
            )
            if existing_created_at is not None:
                self.created_at = existing_created_at

        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Return the one active RestaurantSettings row.

        Lazily creates the row with sensible defaults on first call if it
        does not exist yet, so a fresh/empty database does not error or
        require a manual seed step. Subsequent calls return the same row
        (same primary key), never creating a second one.
        """
        settings, _created = cls.objects.get_or_create(
            pk=SINGLETON_PK,
            defaults={
                'name': 'My Restaurant',
                'grace_period_minutes': 30,
            },
        )
        return settings

    def __str__(self):
        return self.name


class WorkerProfile(models.Model):
    """MVP worker role for a Django auth user."""

    class Role(models.TextChoices):
        STAFF = 'staff', 'Staff'
        MANAGER = 'manager', 'Manager'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='worker_profile',
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user} ({self.get_role_display()})'
