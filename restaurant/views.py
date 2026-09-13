from django.contrib.auth import get_user_model
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .auth import manager_required, staff_or_manager_required
from .check_in_tokens import is_valid_check_in_token
from .forms import (
    GuestCheckInForm,
    RestaurantTableForm,
    WorkerAccountCreateForm,
    WorkerAccountEditForm,
)
from .models import RestaurantTable, WaitlistEntry, WorkerProfile


@staff_or_manager_required
def staff_landing(request):
    return render(request, 'restaurant/staff_landing.html')


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
