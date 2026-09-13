import uuid

from django.db import migrations, models


def populate_public_identifiers(apps, schema_editor):
    WaitlistEntry = apps.get_model('restaurant', 'WaitlistEntry')
    for entry in WaitlistEntry.objects.filter(public_identifier__isnull=True):
        entry.public_identifier = uuid.uuid4()
        entry.save(update_fields=['public_identifier'])


class Migration(migrations.Migration):

    dependencies = [
        ('restaurant', '0004_waitlistentry'),
    ]

    operations = [
        migrations.AddField(
            model_name='waitlistentry',
            name='estimated_wait_minutes',
            field=models.PositiveIntegerField(default=15),
        ),
        migrations.AddField(
            model_name='waitlistentry',
            name='public_identifier',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.RunPython(
            populate_public_identifiers,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='waitlistentry',
            name='public_identifier',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
    ]
