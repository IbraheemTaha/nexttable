from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db.models import Case, IntegerField, Value, When
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .auth import manager_required, staff_or_manager_required
from .check_in_tokens import is_valid_check_in_token
from .forms import (
    EtaRuleForm,
    GracePeriodForm,
    GuestCheckInForm,
    RestaurantTableForm,
    WorkerAccountCreateForm,
    WorkerAccountEditForm,
)
from .models import (
    EtaRule,
    RestaurantSettings,
    RestaurantTable,
    WaitlistEntry,
    WorkerProfile,
)
from .services import (
    InvalidStatusTransitionError,
    mark_guest_arrived,
    mark_guest_cancelled,
    mark_guest_left,
    mark_guest_no_show,
    mark_guest_seated,
    set_table_status,
)


@staff_or_manager_required
def staff_landing(request):
    return render(request, 'restaurant/staff_landing.html')


ACTIVE_WAITLIST_STATUSES = [
    WaitlistEntry.Status.WAITING,
    WaitlistEntry.Status.NOTIFIED,
    WaitlistEntry.Status.ARRIVED,
    WaitlistEntry.Status.LATE_DEMOTED,
]

PRIORITY_WAITLIST_STATUSES = [
    WaitlistEntry.Status.WAITING,
    WaitlistEntry.Status.LATE_DEMOTED,
]


@staff_or_manager_required
def waitlist(request):
    status_filter = request.GET.get('status', 'all')

    if status_filter == 'waiting':
        statuses = [WaitlistEntry.Status.WAITING]
    else:
        status_filter = 'all'
        statuses = ACTIVE_WAITLIST_STATUSES

    entries = (
        WaitlistEntry.objects.filter(status__in=statuses)
        .select_related('assigned_table')
        .annotate(
            is_priority=Case(
                When(status__in=PRIORITY_WAITLIST_STATUSES, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by('is_priority', 'checked_in_at')
    )

    return render(
        request,
        'restaurant/waitlist.html',
        {
            'entries': entries,
            'status_filter': status_filter,
        },
    )


WAITLIST_ACTIONS = {
    'arrived': mark_guest_arrived,
    'seated': mark_guest_seated,
    'left': mark_guest_left,
    'cancelled': mark_guest_cancelled,
    'no_show': mark_guest_no_show,
}


@staff_or_manager_required
def waitlist_entry_action(request, entry_id, action):
    entry = get_object_or_404(WaitlistEntry, pk=entry_id)

    transition_fn = WAITLIST_ACTIONS.get(action)
    if transition_fn is None:
        raise Http404('Unknown waitlist action.')

    if request.method == 'POST':
        try:
            transition_fn(entry)
        except InvalidStatusTransitionError as exc:
            messages.error(request, str(exc))

    return redirect('restaurant:waitlist')


TABLE_GUEST_WAITLIST_STATUSES = [
    WaitlistEntry.Status.NOTIFIED,
    WaitlistEntry.Status.ARRIVED,
    WaitlistEntry.Status.SEATED,
]


@staff_or_manager_required
def table_status(request):
    guest_entries_by_table_id = {
        entry.assigned_table_id: entry
        for entry in WaitlistEntry.objects.filter(
            status__in=TABLE_GUEST_WAITLIST_STATUSES,
            assigned_table__isnull=False,
        )
    }

    tables = RestaurantTable.objects.order_by('identifier')
    tables_by_status = {status: [] for status, _ in RestaurantTable.Status.choices}
    for table in tables:
        table.current_guest_entry = guest_entries_by_table_id.get(table.id)
        tables_by_status.setdefault(table.status, []).append(table)

    status_groups = [
        {
            'status': status,
            'label': label,
            'tables': tables_by_status.get(status, []),
        }
        for status, label in RestaurantTable.Status.choices
    ]

    return render(
        request,
        'restaurant/table_status.html',
        {'status_groups': status_groups},
    )


@staff_or_manager_required
def table_status_action(request, table_id, target_status):
    table = get_object_or_404(RestaurantTable, pk=table_id)

    valid_statuses = {status for status, _ in RestaurantTable.Status.choices}
    if target_status not in valid_statuses:
        raise Http404('Unknown table status.')

    if request.method == 'POST':
        try:
            set_table_status(table, target_status)
        except InvalidStatusTransitionError as exc:
            messages.error(request, str(exc))

    return redirect('restaurant:table_status')


@manager_required
def manager_landing(request):
    return render(request, 'restaurant/manager_landing.html')


def guest_check_in(request, token):
    token_state = _check_in_token_state(token)
    if token_state != 'valid':
        return render(
            request,
            'restaurant/guest_check_in.html',
            {'token_state': token_state},
        )

    return render(
        request,
        'restaurant/guest_check_in.html',
        {
            'form': GuestCheckInForm(),
            'token': token,
            'token_state': token_state,
        },
    )


def guest_check_in_submit(request, token):
    token_state = _check_in_token_state(token)
    if token_state != 'valid':
        return render(
            request,
            'restaurant/guest_check_in.html',
            {'token_state': token_state},
        )

    form = GuestCheckInForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        entry = form.save()
        return redirect(
            'restaurant:guest_check_in_status',
            public_identifier=entry.public_identifier,
        )

    return render(
        request,
        'restaurant/guest_check_in.html',
        {
            'form': form,
            'token': token,
            'token_state': token_state,
        },
    )


def guest_check_in_status(request, public_identifier):
    entry = get_object_or_404(
        WaitlistEntry,
        public_identifier=public_identifier,
    )
    return render(
        request,
        'restaurant/guest_check_in_status.html',
        _guest_status_context(entry),
    )


def guest_check_in_status_partial(request, public_identifier):
    entry = get_object_or_404(
        WaitlistEntry,
        public_identifier=public_identifier,
    )
    return render(
        request,
        'restaurant/_guest_waiting_status.html',
        _guest_status_context(entry),
    )


def guest_check_in_cancel(request, public_identifier):
    entry = get_object_or_404(
        WaitlistEntry,
        public_identifier=public_identifier,
    )
    if request.method == 'POST':
        if _entry_can_be_cancelled(entry):
            entry.status = WaitlistEntry.Status.CANCELLED
            entry.cancelled_at = timezone.now()
            entry.save(update_fields=['status', 'cancelled_at', 'updated_at'])
            return redirect(
                'restaurant:guest_check_in_status',
                public_identifier=entry.public_identifier,
            )

        return render(
            request,
            'restaurant/guest_check_in_cancel_confirm.html',
            _guest_status_context(
                entry,
                cancellation_blocked=True,
            ),
        )

    return render(
        request,
        'restaurant/guest_check_in_cancel_confirm.html',
        _guest_status_context(entry),
    )


def _entry_can_be_cancelled(entry):
    return entry.status in {
        WaitlistEntry.Status.WAITING,
        WaitlistEntry.Status.ARRIVED,
        WaitlistEntry.Status.LATE_DEMOTED,
    }


def _guest_status_context(entry, cancellation_blocked=False):
    return {
        'entry': entry,
        'can_cancel': _entry_can_be_cancelled(entry),
        'show_table_ready_message': (
            entry.status == WaitlistEntry.Status.NOTIFIED
        ),
        'status_partial_url': reverse(
            'restaurant:guest_check_in_status_partial',
            args=[entry.public_identifier],
        ),
        'cancel_url': reverse(
            'restaurant:guest_check_in_cancel',
            args=[entry.public_identifier],
        ),
        'cancellation_blocked': cancellation_blocked,
    }


def _check_in_token_state(token):
    if is_valid_check_in_token(token):
        return 'valid'

    previous_day = timezone.localdate() - timezone.timedelta(days=1)
    if is_valid_check_in_token(token, for_date=previous_day):
        return 'expired'

    return 'invalid'


@manager_required
def worker_account_list(request):
    workers = (
        WorkerProfile.objects.select_related('user')
        .order_by('user__username')
    )
    return render(
        request,
        'restaurant/worker_account_list.html',
        {'workers': workers},
    )


@manager_required
def worker_account_create(request):
    if request.method == 'POST':
        form = WorkerAccountCreateForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('restaurant:worker_account_list')
    else:
        form = WorkerAccountCreateForm()

    return render(
        request,
        'restaurant/worker_account_form.html',
        {
            'form': form,
            'title': 'Create Worker Account',
            'submit_label': 'Create account',
        },
    )


@manager_required
def worker_account_edit(request, user_id):
    user = get_object_or_404(
        get_user_model().objects.select_related('worker_profile'),
        pk=user_id,
        worker_profile__isnull=False,
    )
    if request.method == 'POST':
        form = WorkerAccountEditForm(
            request.POST,
            user=user,
            current_user=request.user,
        )
        if form.is_valid():
            form.save()
            return redirect('restaurant:worker_account_list')
    else:
        form = WorkerAccountEditForm(user=user, current_user=request.user)

    return render(
        request,
        'restaurant/worker_account_form.html',
        {
            'form': form,
            'title': 'Edit Worker Account',
            'submit_label': 'Save changes',
            'worker_user': user,
        },
    )


@manager_required
def table_config_list(request):
    tables = RestaurantTable.objects.order_by('identifier')
    return render(
        request,
        'restaurant/table_config_list.html',
        {'tables': tables},
    )


@manager_required
def table_config_create(request):
    if request.method == 'POST':
        form = RestaurantTableForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('restaurant:table_config_list')
    else:
        form = RestaurantTableForm()

    return render(
        request,
        'restaurant/table_config_form.html',
        {
            'form': form,
            'title': 'Create Table',
            'submit_label': 'Create table',
        },
    )


@manager_required
def table_config_edit(request, table_id):
    table = get_object_or_404(RestaurantTable, pk=table_id)
    if request.method == 'POST':
        form = RestaurantTableForm(request.POST, instance=table)
        if form.is_valid():
            form.save()
            return redirect('restaurant:table_config_list')
    else:
        form = RestaurantTableForm(instance=table)

    return render(
        request,
        'restaurant/table_config_form.html',
        {
            'form': form,
            'title': 'Edit Table',
            'submit_label': 'Save changes',
            'table': table,
        },
    )


@manager_required
def table_config_remove(request, table_id):
    table = get_object_or_404(RestaurantTable, pk=table_id)
    active_statuses = {
        RestaurantTable.Status.RESERVED,
        RestaurantTable.Status.OCCUPIED,
    }

    if request.method == 'POST':
        if table.status in active_statuses:
            messages.error(
                request,
                'Reserved or occupied tables cannot be removed.',
            )
            return redirect('restaurant:table_config_list')

        table.delete()
        return redirect('restaurant:table_config_list')

    return render(
        request,
        'restaurant/table_config_confirm_remove.html',
        {'table': table},
    )


@manager_required
def eta_config(request):
    settings = RestaurantSettings.get_active()
    rules = EtaRule.objects.order_by('min_party_size', 'max_party_size')
    return render(
        request,
        'restaurant/eta_config.html',
        {
            'rules': rules,
            'settings': settings,
        },
    )


@manager_required
def eta_rule_create(request):
    if request.method == 'POST':
        form = EtaRuleForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('restaurant:eta_config')
    else:
        form = EtaRuleForm(initial={'is_active': True})

    return render(
        request,
        'restaurant/eta_rule_form.html',
        {
            'form': form,
            'title': 'Create ETA Rule',
            'submit_label': 'Create rule',
        },
    )


@manager_required
def eta_rule_edit(request, rule_id):
    rule = get_object_or_404(EtaRule, pk=rule_id)
    if request.method == 'POST':
        form = EtaRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            return redirect('restaurant:eta_config')
    else:
        form = EtaRuleForm(instance=rule)

    return render(
        request,
        'restaurant/eta_rule_form.html',
        {
            'form': form,
            'title': 'Edit ETA Rule',
            'submit_label': 'Save changes',
            'rule': rule,
        },
    )


@manager_required
def eta_grace_period_edit(request):
    settings = RestaurantSettings.get_active()
    if request.method == 'POST':
        form = GracePeriodForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            return redirect('restaurant:eta_config')
    else:
        form = GracePeriodForm(instance=settings)

    return render(
        request,
        'restaurant/eta_grace_period_form.html',
        {
            'form': form,
            'title': 'Edit Grace Period',
            'submit_label': 'Save changes',
        },
    )
