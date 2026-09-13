from django.db import models

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
