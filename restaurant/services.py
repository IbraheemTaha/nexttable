"""Business logic services for the restaurant waitlist app.

This module provides service functions for complex business logic that
spans multiple models or enforces important rules. These functions use
the Django ORM directly and are kept separate from models and views
to support unit testing and reusability.
"""

from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import EtaRule, RestaurantTable, WaitlistEntry


def check_table_compatibility(table, waitlist_entry):
    """Check if a table can accommodate a waitlist entry's requirements.

    Determines whether a specific table is compatible with a waiting party
    based on:
    - Party size vs. table capacity
    - Accessibility requirements
    - Location preference (indoor/outdoor)
    - Seating preference (standard/booth/bar)
    - High chair requirements

    Args:
        table: RestaurantTable instance to evaluate
        waitlist_entry: WaitlistEntry instance with guest requirements

    Returns:
        True if the table is compatible with all guest requirements,
        False otherwise.

    Raises:
        TypeError: If arguments are not the expected model instances.
    """
    if not isinstance(table, RestaurantTable):
        raise TypeError('table must be a RestaurantTable instance')
    if not isinstance(waitlist_entry, WaitlistEntry):
        raise TypeError('waitlist_entry must be a WaitlistEntry instance')

    # Check 1: Party size must fit in table capacity
    if waitlist_entry.party_size > table.capacity:
        return False

    # Check 2: Accessibility requirements
    guest_has_accessibility_needs = _guest_needs_accessibility(waitlist_entry)
    if guest_has_accessibility_needs and not table.has_accessibility:
        return False

    # Check 3: Location preference (indoor/outdoor)
    guest_location_preference = _extract_location_preference(waitlist_entry)
    if not _location_compatible(guest_location_preference, table.location):
        return False

    # Check 4: Seating preference
    guest_seating_preference = _extract_seating_preference(waitlist_entry)
    if not _seating_compatible(guest_seating_preference, table.seating_type):
        return False

    # Check 5: High chair requirement
    guest_needs_high_chair = _guest_needs_high_chair(waitlist_entry)
    if guest_needs_high_chair and not table.can_accommodate_high_chair:
        return False

    return True


def _guest_needs_accessibility(waitlist_entry):
    """Check if guest has accessibility requirements.

    Args:
        waitlist_entry: WaitlistEntry instance

    Returns:
        True if guest has accessibility requirements, False otherwise.
    """
    if not waitlist_entry.preference_notes:
        return False

    # Check if accessibility_requirements field in preference_notes has a value
    # The form saves this with the label "Accessibility requirements: ..."
    return 'Accessibility requirements:' in waitlist_entry.preference_notes and \
           'Accessibility requirements: ' in waitlist_entry.preference_notes


def _extract_location_preference(waitlist_entry):
    """Extract guest's location preference (indoor/outdoor/no preference).

    Args:
        waitlist_entry: WaitlistEntry instance

    Returns:
        'indoor', 'outdoor', 'no_preference', or None if not specified.
    """
    if not waitlist_entry.preference_notes:
        return None

    # Parse preference_notes which is formatted as:
    # "Indoor/outdoor preference: <value>\n..."
    lines = waitlist_entry.preference_notes.split('\n')
    for line in lines:
        if line.startswith('Indoor/outdoor preference:'):
            # Extract value after the colon
            parts = line.split(':', 1)
            if len(parts) == 2:
                value = parts[1].strip().lower()
                if value in ['indoor', 'outdoor', 'no_preference']:
                    return value
    return None


def _extract_seating_preference(waitlist_entry):
    """Extract guest's seating preference (standard/booth/bar/no preference).

    Args:
        waitlist_entry: WaitlistEntry instance

    Returns:
        'standard', 'booth', 'bar', 'no_preference', or None if not specified.
    """
    if not waitlist_entry.preference_notes:
        return None

    # Parse preference_notes for seating preference
    lines = waitlist_entry.preference_notes.split('\n')
    for line in lines:
        if line.startswith('Seating preference:'):
            # Extract value after the colon
            parts = line.split(':', 1)
            if len(parts) == 2:
                value = parts[1].strip().lower()
                # Map form values to our stored values
                value_mapping = {
                    'standard table': 'standard',
                    'booth': 'booth',
                    'bar seating': 'bar',
                    'standard': 'standard',
                    'no_preference': 'no_preference',
                }
                return value_mapping.get(value)
    return None


def _guest_needs_high_chair(waitlist_entry):
    """Check if guest needs a high chair.

    Args:
        waitlist_entry: WaitlistEntry instance

    Returns:
        True if guest needs a high chair, False otherwise.
    """
    if not waitlist_entry.preference_notes:
        return False

    # Parse preference_notes for high chair need
    lines = waitlist_entry.preference_notes.split('\n')
    for line in lines:
        if line.startswith('High chair need:'):
            # Extract value after the colon
            parts = line.split(':', 1)
            if len(parts) == 2:
                value = parts[1].strip().lower()
                return value == 'yes'
    return False


def _location_compatible(guest_preference, table_location):
    """Check if guest location preference is compatible with table location.

    Args:
        guest_preference: 'indoor', 'outdoor', 'no_preference', or None
        table_location: 'indoor', 'outdoor', or 'any'

    Returns:
        True if compatible, False otherwise.
    """
    # If guest has no preference or unknown preference, any table works
    if guest_preference is None or guest_preference == 'no_preference':
        return True

    # If table accepts any location, it's compatible
    if table_location == 'any':
        return True

    # Guest preference must match table location exactly
    return guest_preference == table_location


def _seating_compatible(guest_preference, table_seating_type):
    """Check if guest seating preference is compatible with table type.

    Args:
        guest_preference: 'standard', 'booth', 'bar', 'no_preference', or None
        table_seating_type: 'standard', 'booth', or 'bar'

    Returns:
        True if compatible, False otherwise.
    """
    # If guest has no preference or unknown preference, any seating works
    if guest_preference is None or guest_preference == 'no_preference':
        return True

    # Guest preference must match table seating type exactly
    return guest_preference == table_seating_type


def calculate_estimated_wait_minutes(party_size, existing_entry=None):
    """Calculate the estimated wait time for a guest.

    The estimate is based on:
    1. Party size, which determines the base ETA rule
    2. Number of parties ahead in the queue
    3. Available table capacity (for future optimization)

    Algorithm:
    - Validate party size is positive
    - Find the active EtaRule that matches the party size
    - Count parties currently waiting or late/demoted (ahead in queue)
    - For new entries: queue_position = count of all waiting/late parties
    - For existing entries: queue_position = count of parties checked in before this one
    - Estimate = base * (queue_position + 1), never below base

    Args:
        party_size: The number of guests in the party (positive int)
        existing_entry: Optional WaitlistEntry instance for adjusting calculation
                       If provided, counts only parties ahead of this entry

    Returns:
        Estimated wait time in minutes (positive int). If no applicable
        EtaRule exists, returns a sensible default (15 minutes).

    Raises:
        ValidationError: If party_size is not positive
    """
    # Validate party size
    if not isinstance(party_size, int) or party_size <= 0:
        raise ValidationError('Party size must be a positive integer.')

    # Find the EtaRule matching this party size
    base_estimate = _get_base_eta_for_party_size(party_size)
    if base_estimate is None:
        # Fallback if no rule is configured
        return WaitlistEntry.DEFAULT_INITIAL_ESTIMATED_WAIT_MINUTES

    # Count parties in queue (waiting or late/demoted, not notified or seated)
    queue_query = WaitlistEntry.objects.filter(
        Q(status=WaitlistEntry.Status.WAITING)
        | Q(status=WaitlistEntry.Status.LATE_DEMOTED)
    )

    if existing_entry:
        # For existing entry, count only parties checked in before this one
        queue_position = queue_query.filter(
            checked_in_at__lt=existing_entry.checked_in_at
        ).count()
    else:
        # For new entry, count all waiting/demoted parties
        queue_position = queue_query.count()

    # Calculate estimate: base * (queue_position + 1)
    # This ensures: with no queue (queue_position=0), estimate = base * 1 = base
    estimate = base_estimate * (queue_position + 1)

    # Never go below the base estimate
    return max(base_estimate, estimate)


def _get_base_eta_for_party_size(party_size):
    """Find the base ETA rule for a given party size.

    Args:
        party_size: The number of guests (positive int)

    Returns:
        The estimated_wait_minutes from the matching active EtaRule,
        or None if no rule matches.
    """
    # Query for a rule that covers this party size
    # A rule matches if: min_party_size <= party_size AND
    # (max_party_size is None OR max_party_size >= party_size)
    matching_rule = EtaRule.objects.filter(
        is_active=True,
        min_party_size__lte=party_size,
    ).filter(
        Q(max_party_size__gte=party_size) | Q(max_party_size__isnull=True)
    ).first()

    if matching_rule:
        return matching_rule.estimated_wait_minutes
    return None
