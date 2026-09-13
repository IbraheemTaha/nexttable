"""Business logic services for the restaurant waitlist app.

This module provides service functions for complex business logic that
spans multiple models or enforces important rules. These functions use
the Django ORM directly and are kept separate from models and views
to support unit testing and reusability.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import EtaRule, RestaurantSettings, RestaurantTable, WaitlistEntry


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


def select_next_guest_for_table(table):
    """Select the highest-priority eligible waiting guest for a table.

    Considers only WaitlistEntry rows with status ``waiting`` or
    ``late_demoted`` that are compatible with the given table (per
    `check_table_compatibility`). Normal waiting guests are ranked ahead
    of late_demoted guests regardless of check-in time; within each
    group, the earliest checked_in_at wins.

    This function is read-only: it does not mutate any waitlist or table
    rows, assign a table, or change any statuses. Actually assigning the
    table and transitioning statuses is out of scope (see #18).

    Args:
        table: RestaurantTable instance to find a guest for.

    Returns:
        The highest-priority compatible WaitlistEntry, or None if no
        eligible guest exists.

    Raises:
        TypeError: If table is not a RestaurantTable instance.
    """
    if not isinstance(table, RestaurantTable):
        raise TypeError('table must be a RestaurantTable instance')

    candidates = WaitlistEntry.objects.filter(
        Q(status=WaitlistEntry.Status.WAITING)
        | Q(status=WaitlistEntry.Status.LATE_DEMOTED)
    ).order_by('checked_in_at')

    best_entry = None
    best_rank = None
    for entry in candidates:
        if not check_table_compatibility(table, entry):
            continue

        # Rank 0 for normal waiting guests, 1 for late_demoted, so that
        # waiting guests always sort ahead of late_demoted guests.
        rank = (
            0 if entry.status == WaitlistEntry.Status.WAITING else 1,
            entry.checked_in_at,
        )

        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_entry = entry

    return best_entry


def match_table_automatically(table):
    """Automatically assign the best waiting guest to a newly-free table.

    Uses `select_next_guest_for_table` to find the highest-priority
    compatible waiting guest for the given table. If a match is found,
    the guest is assigned to the table and notified, and the table is
    marked reserved. If no compatible guest exists, or the table is not
    currently free, nothing is mutated.

    Args:
        table: RestaurantTable instance to match a guest to.

    Returns:
        The matched WaitlistEntry if a guest was assigned, or None if
        no match was made.

    Raises:
        TypeError: If table is not a RestaurantTable instance.
    """
    if not isinstance(table, RestaurantTable):
        raise TypeError('table must be a RestaurantTable instance')

    if table.status != RestaurantTable.Status.FREE:
        return None

    matched_entry = select_next_guest_for_table(table)
    if matched_entry is None:
        return None

    with transaction.atomic():
        matched_entry.assigned_table = table
        matched_entry.status = WaitlistEntry.Status.NOTIFIED
        matched_entry.notified_at = timezone.now()
        matched_entry.save(
            update_fields=['assigned_table', 'status', 'notified_at', 'updated_at']
        )

        table.status = RestaurantTable.Status.RESERVED
        table.save(update_fields=['status', 'updated_at'])

    return matched_entry


def demote_late_guests():
    """Demote notified guests whose grace period has expired.

    Finds every WaitlistEntry whose status is ``notified`` and whose
    `notified_at` timestamp is more than
    `RestaurantSettings.get_active().grace_period_minutes` minutes in the
    past, and transitions each one to `late_demoted`. No other fields on
    the entry (guest_name, party_size, checked_in_at, notified_at, etc.)
    are modified, so the guest keeps their place in line per #17.

    If a demoted guest had an `assigned_table`, that table is freed (its
    `assigned_table` reference on the entry is cleared and the table's
    status is set to free) and `match_table_automatically` (#18) is
    invoked for it immediately so another eligible guest can be matched
    to it right away.

    This function only ever acts on guests currently in the `notified`
    status, so it is safe to call repeatedly (e.g. on a schedule or on
    each dashboard load): guests already demoted, or still within their
    grace period, are left untouched.

    Returns:
        A list of the WaitlistEntry instances that were demoted.
    """
    grace_period_minutes = RestaurantSettings.get_active().grace_period_minutes
    cutoff = timezone.now() - timezone.timedelta(minutes=grace_period_minutes)

    late_entries = WaitlistEntry.objects.filter(
        status=WaitlistEntry.Status.NOTIFIED,
        notified_at__lt=cutoff,
    )

    demoted_entries = []
    for entry in late_entries:
        with transaction.atomic():
            freed_table = entry.assigned_table

            entry.status = WaitlistEntry.Status.LATE_DEMOTED
            entry.assigned_table = None
            entry.save(update_fields=['status', 'assigned_table', 'updated_at'])

            if freed_table is not None:
                freed_table.status = RestaurantTable.Status.FREE
                freed_table.save(update_fields=['status', 'updated_at'])
                match_table_automatically(freed_table)

        demoted_entries.append(entry)

    return demoted_entries


class InvalidStatusTransitionError(ValidationError):
    """Raised when a requested WaitlistEntry status transition is not allowed."""


class ManualAssignmentError(ValidationError):
    """Raised when a manual table assignment override cannot be performed."""


_MANUAL_ASSIGNMENT_ELIGIBLE_STATUSES = {
    WaitlistEntry.Status.WAITING,
    WaitlistEntry.Status.LATE_DEMOTED,
}


def assign_table_manually(table, waitlist_entry):
    """Manually assign (or reassign) a specific table to a waiting guest.

    This overrides automatic matching (see `match_table_automatically`),
    allowing staff to pick a specific table/guest pair. Table
    compatibility preferences (see `check_table_compatibility`) are not
    strictly enforced, but under-capacity assignments are always
    rejected.

    Args:
        table: RestaurantTable instance to assign.
        waitlist_entry: WaitlistEntry instance to assign the table to.

    Returns:
        The updated WaitlistEntry instance.

    Raises:
        TypeError: If arguments are not the expected model instances.
        ManualAssignmentError: If the guest is not in an eligible
            status, the table is not free, or the table's capacity is
            too small for the guest's party size.
    """
    if not isinstance(table, RestaurantTable):
        raise TypeError('table must be a RestaurantTable instance')
    if not isinstance(waitlist_entry, WaitlistEntry):
        raise TypeError('waitlist_entry must be a WaitlistEntry instance')

    if waitlist_entry.status not in _MANUAL_ASSIGNMENT_ELIGIBLE_STATUSES:
        raise ManualAssignmentError(
            f'Cannot manually assign a table to a guest with status '
            f'"{waitlist_entry.status}". Guest must be waiting or '
            f'late_demoted.'
        )

    if table.status != RestaurantTable.Status.FREE:
        raise ManualAssignmentError(
            f'Cannot manually assign table "{table.identifier}" because '
            f'it is not free (current status: "{table.status}").'
        )

    if waitlist_entry.party_size > table.capacity:
        raise ManualAssignmentError(
            f'Table "{table.identifier}" (capacity {table.capacity}) is '
            f'too small for a party of {waitlist_entry.party_size}.'
        )

    with transaction.atomic():
        previous_table = waitlist_entry.assigned_table
        if previous_table is not None and previous_table.pk != table.pk:
            previous_table.status = RestaurantTable.Status.FREE
            previous_table.save(update_fields=['status', 'updated_at'])

        waitlist_entry.assigned_table = table
        waitlist_entry.status = WaitlistEntry.Status.NOTIFIED
        waitlist_entry.notified_at = timezone.now()
        waitlist_entry.save(
            update_fields=['assigned_table', 'status', 'notified_at', 'updated_at']
        )

        table.status = RestaurantTable.Status.RESERVED
        table.save(update_fields=['status', 'updated_at'])

    return waitlist_entry


# Maps each manual table-status transition target to the set of statuses
# it may be entered from via `set_table_status`.
_ALLOWED_TABLE_TRANSITIONS = {
    RestaurantTable.Status.FREE: {
        RestaurantTable.Status.CLEANING,
        RestaurantTable.Status.RESERVED,
    },
    RestaurantTable.Status.CLEANING: {
        RestaurantTable.Status.OCCUPIED,
    },
    RestaurantTable.Status.OCCUPIED: {
        RestaurantTable.Status.FREE,
    },
}


def set_table_status(table, target_status):
    """Manually transition a RestaurantTable to a new status.

    Valid manual transitions are:
    - cleaning -> free
    - occupied -> cleaning
    - reserved -> free
    - free -> occupied (for walk-ins with no waitlist entry)

    Whenever a table is manually set to free, `match_table_automatically`
    is invoked immediately for that table. If a compatible waiting guest
    is found, the table ends up reserved (not free) and the guest is
    notified; otherwise the table remains free.

    Args:
        table: RestaurantTable instance to transition.
        target_status: One of RestaurantTable.Status to transition to.

    Returns:
        The updated RestaurantTable instance.

    Raises:
        TypeError: If table is not a RestaurantTable instance.
        InvalidStatusTransitionError: If the current status cannot
            manually transition to target_status.
    """
    if not isinstance(table, RestaurantTable):
        raise TypeError('table must be a RestaurantTable instance')

    allowed_from = _ALLOWED_TABLE_TRANSITIONS.get(target_status, set())
    if table.status not in allowed_from:
        raise InvalidStatusTransitionError(
            f'Cannot transition a table from "{table.status}" to '
            f'"{target_status}".'
        )

    with transaction.atomic():
        table.status = target_status
        table.save(update_fields=['status', 'updated_at'])

        if target_status == RestaurantTable.Status.FREE:
            match_table_automatically(table)

    return table


# Maps each transition target status to the set of statuses it may be
# entered from. Any status not listed as a key here has no valid inbound
# transitions via the guest status action service functions.
_ALLOWED_TRANSITIONS = {
    WaitlistEntry.Status.ARRIVED: {
        WaitlistEntry.Status.WAITING,
        WaitlistEntry.Status.NOTIFIED,
        WaitlistEntry.Status.LATE_DEMOTED,
    },
    WaitlistEntry.Status.SEATED: {
        WaitlistEntry.Status.ARRIVED,
        WaitlistEntry.Status.NOTIFIED,
    },
    WaitlistEntry.Status.LEFT: {
        WaitlistEntry.Status.SEATED,
    },
    WaitlistEntry.Status.CANCELLED: {
        WaitlistEntry.Status.WAITING,
        WaitlistEntry.Status.NOTIFIED,
        WaitlistEntry.Status.ARRIVED,
        WaitlistEntry.Status.LATE_DEMOTED,
    },
    WaitlistEntry.Status.NO_SHOW: {
        WaitlistEntry.Status.WAITING,
        WaitlistEntry.Status.NOTIFIED,
        WaitlistEntry.Status.ARRIVED,
        WaitlistEntry.Status.LATE_DEMOTED,
    },
}

# Timestamp field to stamp with the current time for each target status.
_TRANSITION_TIMESTAMP_FIELD = {
    WaitlistEntry.Status.ARRIVED: 'arrived_at',
    WaitlistEntry.Status.SEATED: 'seated_at',
    WaitlistEntry.Status.LEFT: 'left_at',
    WaitlistEntry.Status.CANCELLED: 'cancelled_at',
    WaitlistEntry.Status.NO_SHOW: 'no_show_at',
}


def _validate_transition(waitlist_entry, target_status):
    if not isinstance(waitlist_entry, WaitlistEntry):
        raise TypeError('waitlist_entry must be a WaitlistEntry instance')

    allowed_from = _ALLOWED_TRANSITIONS.get(target_status, set())
    if waitlist_entry.status not in allowed_from:
        raise InvalidStatusTransitionError(
            f'Cannot transition a WaitlistEntry from '
            f'"{waitlist_entry.status}" to "{target_status}".'
        )


def mark_guest_arrived(waitlist_entry):
    """Transition a WaitlistEntry to arrived, stamping arrived_at.

    Valid from: waiting, notified, late_demoted.

    Args:
        waitlist_entry: WaitlistEntry instance to transition.

    Returns:
        The updated WaitlistEntry instance.

    Raises:
        TypeError: If waitlist_entry is not a WaitlistEntry instance.
        InvalidStatusTransitionError: If the current status cannot
            transition to arrived.
    """
    _validate_transition(waitlist_entry, WaitlistEntry.Status.ARRIVED)

    with transaction.atomic():
        waitlist_entry.status = WaitlistEntry.Status.ARRIVED
        waitlist_entry.arrived_at = timezone.now()
        waitlist_entry.save(
            update_fields=['status', 'arrived_at', 'updated_at']
        )

    return waitlist_entry


def mark_guest_seated(waitlist_entry):
    """Transition a WaitlistEntry to seated, stamping seated_at.

    Requires the entry to have an assigned_table; that table's status is
    set to occupied.

    Valid from: arrived, notified.

    Args:
        waitlist_entry: WaitlistEntry instance to transition.

    Returns:
        The updated WaitlistEntry instance.

    Raises:
        TypeError: If waitlist_entry is not a WaitlistEntry instance.
        InvalidStatusTransitionError: If the current status cannot
            transition to seated, or if there is no assigned_table.
    """
    _validate_transition(waitlist_entry, WaitlistEntry.Status.SEATED)

    if waitlist_entry.assigned_table_id is None:
        raise InvalidStatusTransitionError(
            'Cannot mark a guest seated without an assigned table.'
        )

    with transaction.atomic():
        waitlist_entry.status = WaitlistEntry.Status.SEATED
        waitlist_entry.seated_at = timezone.now()
        waitlist_entry.save(
            update_fields=['status', 'seated_at', 'updated_at']
        )

        table = waitlist_entry.assigned_table
        table.status = RestaurantTable.Status.OCCUPIED
        table.save(update_fields=['status', 'updated_at'])

    return waitlist_entry


def mark_guest_left(waitlist_entry):
    """Transition a seated WaitlistEntry to left, stamping left_at.

    Sets the assigned table's status to cleaning. The entry's
    assigned_table and history are left intact for record-keeping.

    Valid from: seated.

    Args:
        waitlist_entry: WaitlistEntry instance to transition.

    Returns:
        The updated WaitlistEntry instance.

    Raises:
        TypeError: If waitlist_entry is not a WaitlistEntry instance.
        InvalidStatusTransitionError: If the current status is not seated.
    """
    _validate_transition(waitlist_entry, WaitlistEntry.Status.LEFT)

    with transaction.atomic():
        waitlist_entry.status = WaitlistEntry.Status.LEFT
        waitlist_entry.left_at = timezone.now()
        waitlist_entry.save(
            update_fields=['status', 'left_at', 'updated_at']
        )

        table = waitlist_entry.assigned_table
        if table is not None:
            table.status = RestaurantTable.Status.CLEANING
            table.save(update_fields=['status', 'updated_at'])

    return waitlist_entry


def mark_guest_cancelled(waitlist_entry):
    """Transition a WaitlistEntry to cancelled, stamping cancelled_at.

    Does not require an assigned table. If a table was already assigned,
    it is freed (status set to free) since the guest will not occupy it.

    Valid from: waiting, notified, arrived, late_demoted.

    Args:
        waitlist_entry: WaitlistEntry instance to transition.

    Returns:
        The updated WaitlistEntry instance.

    Raises:
        TypeError: If waitlist_entry is not a WaitlistEntry instance.
        InvalidStatusTransitionError: If the current status cannot
            transition to cancelled.
    """
    return _mark_guest_not_occupying(
        waitlist_entry,
        target_status=WaitlistEntry.Status.CANCELLED,
        timestamp_field='cancelled_at',
    )


def mark_guest_no_show(waitlist_entry):
    """Transition a WaitlistEntry to no_show, stamping no_show_at.

    Does not require an assigned table. If a table was already assigned,
    it is freed (status set to free) since the guest will not occupy it.

    Valid from: waiting, notified, arrived, late_demoted.

    Args:
        waitlist_entry: WaitlistEntry instance to transition.

    Returns:
        The updated WaitlistEntry instance.

    Raises:
        TypeError: If waitlist_entry is not a WaitlistEntry instance.
        InvalidStatusTransitionError: If the current status cannot
            transition to no_show.
    """
    return _mark_guest_not_occupying(
        waitlist_entry,
        target_status=WaitlistEntry.Status.NO_SHOW,
        timestamp_field='no_show_at',
    )


def _mark_guest_not_occupying(waitlist_entry, target_status, timestamp_field):
    _validate_transition(waitlist_entry, target_status)

    with transaction.atomic():
        waitlist_entry.status = target_status
        setattr(waitlist_entry, timestamp_field, timezone.now())
        waitlist_entry.save(
            update_fields=['status', timestamp_field, 'updated_at']
        )

        table = waitlist_entry.assigned_table
        if table is not None:
            table.status = RestaurantTable.Status.FREE
            table.save(update_fields=['status', 'updated_at'])

    return waitlist_entry


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
