from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db.models import Case, IntegerField, Value, When
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..auth import user_is_manager, user_is_staff_or_manager
from ..check_in_tokens import is_valid_check_in_token
from ..forms import (
    EtaRuleForm,
    GracePeriodForm,
    GuestCheckInForm,
    RestaurantTableForm,
    WorkerAccountCreateForm,
    WorkerAccountEditForm,
)
from ..models import EtaRule, RestaurantSettings, RestaurantTable, WaitlistEntry, WorkerProfile
from ..services import (
    InvalidStatusTransitionError,
    ManualAssignmentError,
    assign_table_manually,
    demote_late_guests,
    mark_guest_arrived,
    mark_guest_cancelled,
    mark_guest_left,
    mark_guest_no_show,
    mark_guest_seated,
    set_table_status,
)
from .permissions import IsManager, IsStaffOrManager
from .serializers import (
    EtaRuleSerializer,
    RestaurantSettingsSerializer,
    RestaurantTableSerializer,
    WaitlistEntrySerializer,
    WorkerSerializer,
)


# --- Auth -------------------------------------------------------------


def _serialize_current_user(user):
    try:
        role = user.worker_profile.role
    except WorkerProfile.DoesNotExist:
        role = None
    return {
        'id': user.id,
        'username': user.username,
        'role': role,
    }


@api_view(['GET'])
@permission_classes([AllowAny])
def csrf_view(request):
    # Forces Django to set the csrftoken cookie in the response, so the
    # frontend has something to echo back as X-CSRFToken on its first
    # unsafe request (e.g. login) - the cookie is otherwise only set as a
    # side effect of rendering {% csrf_token %} in a template, which this
    # API-only backend never does.
    return Response({'csrfToken': get_token(request)})


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username', '')
    password = request.data.get('password', '')
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({'detail': 'Invalid credentials.'}, status=400)
    login(request, user)
    return Response(_serialize_current_user(user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response(status=204)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user_view(request):
    return Response(_serialize_current_user(request.user))


# --- Guest check-in (public, HMAC-token gated / public UUID lookup) ---


def _check_in_token_state(token):
    if is_valid_check_in_token(token):
        return 'valid'

    previous_day = timezone.localdate() - timezone.timedelta(days=1)
    if is_valid_check_in_token(token, for_date=previous_day):
        return 'expired'

    return 'invalid'


def _entry_can_be_cancelled(entry):
    return entry.status in {
        WaitlistEntry.Status.WAITING,
        WaitlistEntry.Status.ARRIVED,
        WaitlistEntry.Status.LATE_DEMOTED,
    }


def _serialize_guest_status(entry):
    data = WaitlistEntrySerializer(entry).data
    data['can_cancel'] = _entry_can_be_cancelled(entry)
    data['show_table_ready_message'] = entry.status == WaitlistEntry.Status.NOTIFIED
    return data


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def guest_check_in_view(request, token):
    token_state = _check_in_token_state(token)
    if token_state != 'valid':
        return Response({'token_state': token_state}, status=403)

    if request.method == 'GET':
        return Response({'token_state': token_state})

    form = GuestCheckInForm(request.data)
    if not form.is_valid():
        return Response({'errors': form.errors}, status=400)

    entry = form.save()
    return Response(
        {'public_identifier': str(entry.public_identifier)}, status=201
    )


@api_view(['GET'])
@permission_classes([AllowAny])
def guest_check_in_status_view(request, public_identifier):
    entry = get_object_or_404(WaitlistEntry, public_identifier=public_identifier)
    return Response(_serialize_guest_status(entry))


@api_view(['POST'])
@permission_classes([AllowAny])
def guest_check_in_cancel_view(request, public_identifier):
    entry = get_object_or_404(WaitlistEntry, public_identifier=public_identifier)
    if not _entry_can_be_cancelled(entry):
        return Response(
            {**_serialize_guest_status(entry), 'cancellation_blocked': True},
            status=409,
        )

    entry.status = WaitlistEntry.Status.CANCELLED
    entry.cancelled_at = timezone.now()
    entry.save(update_fields=['status', 'cancelled_at', 'updated_at'])
    return Response(_serialize_guest_status(entry))


# --- Staff: waitlist ----------------------------------------------------

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

WAITLIST_ACTIONS = {
    'arrived': mark_guest_arrived,
    'seated': mark_guest_seated,
    'left': mark_guest_left,
    'cancelled': mark_guest_cancelled,
    'no_show': mark_guest_no_show,
}


class WaitlistView(APIView):
    permission_classes = [IsStaffOrManager]

    def get(self, request):
        demote_late_guests()

        status_filter = request.query_params.get('status', 'all')
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
        free_tables = RestaurantTable.objects.filter(
            status=RestaurantTable.Status.FREE
        ).order_by('identifier')
        eligible_entries = [
            entry for entry in entries if entry.status in PRIORITY_WAITLIST_STATUSES
        ]

        return Response({
            'status_filter': status_filter,
            'entries': WaitlistEntrySerializer(entries, many=True).data,
            'free_tables': RestaurantTableSerializer(free_tables, many=True).data,
            'eligible_entries': WaitlistEntrySerializer(eligible_entries, many=True).data,
        })


class WaitlistEntryActionView(APIView):
    permission_classes = [IsStaffOrManager]

    def post(self, request, entry_id, action):
        entry = get_object_or_404(WaitlistEntry, pk=entry_id)
        transition_fn = WAITLIST_ACTIONS.get(action)
        if transition_fn is None:
            return Response({'detail': 'Unknown waitlist action.'}, status=404)

        try:
            transition_fn(entry)
        except InvalidStatusTransitionError as exc:
            return Response({'detail': str(exc)}, status=400)

        return Response(WaitlistEntrySerializer(entry).data)


class ManualTableAssignmentView(APIView):
    permission_classes = [IsStaffOrManager]

    def post(self, request):
        entry = get_object_or_404(WaitlistEntry, pk=request.data.get('entry_id'))
        table = get_object_or_404(RestaurantTable, pk=request.data.get('table_id'))
        try:
            assign_table_manually(table, entry)
        except ManualAssignmentError as exc:
            return Response({'detail': str(exc)}, status=400)

        return Response(WaitlistEntrySerializer(entry).data)


# --- Staff: tables -------------------------------------------------------


class TableStatusView(APIView):
    permission_classes = [IsStaffOrManager]

    def get(self, request):
        guest_entries_by_table_id = {
            entry.assigned_table_id: entry
            for entry in WaitlistEntry.objects.filter(
                status__in=[
                    WaitlistEntry.Status.NOTIFIED,
                    WaitlistEntry.Status.ARRIVED,
                    WaitlistEntry.Status.SEATED,
                ],
                assigned_table__isnull=False,
            )
        }

        tables = RestaurantTable.objects.order_by('identifier')
        status_groups = {status: [] for status, _ in RestaurantTable.Status.choices}
        for table in tables:
            table_data = RestaurantTableSerializer(table).data
            current_entry = guest_entries_by_table_id.get(table.id)
            table_data['current_guest_entry'] = (
                WaitlistEntrySerializer(current_entry).data if current_entry else None
            )
            status_groups.setdefault(table.status, []).append(table_data)

        eligible_entries = WaitlistEntry.objects.filter(
            status__in=[
                WaitlistEntry.Status.WAITING,
                WaitlistEntry.Status.LATE_DEMOTED,
            ]
        ).order_by('checked_in_at')

        return Response({
            'status_groups': [
                {'status': status, 'label': label, 'tables': status_groups.get(status, [])}
                for status, label in RestaurantTable.Status.choices
            ],
            'eligible_entries': WaitlistEntrySerializer(eligible_entries, many=True).data,
            'free_tables': status_groups.get(RestaurantTable.Status.FREE, []),
        })


class TableStatusActionView(APIView):
    permission_classes = [IsStaffOrManager]

    def post(self, request, table_id, target_status):
        table = get_object_or_404(RestaurantTable, pk=table_id)
        valid_statuses = {status for status, _ in RestaurantTable.Status.choices}
        if target_status not in valid_statuses:
            return Response({'detail': 'Unknown table status.'}, status=404)

        try:
            set_table_status(table, target_status)
        except InvalidStatusTransitionError as exc:
            return Response({'detail': str(exc)}, status=400)

        return Response(RestaurantTableSerializer(table).data)


# --- Manager: workers ------------------------------------------------------


class WorkerListView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        workers = WorkerProfile.objects.select_related('user').order_by('user__username')
        return Response(WorkerSerializer([w.user for w in workers], many=True).data)

    def post(self, request):
        form = WorkerAccountCreateForm(request.data)
        if not form.is_valid():
            return Response({'errors': form.errors}, status=400)
        user = form.save()
        return Response(WorkerSerializer(user).data, status=201)


class WorkerDetailView(APIView):
    permission_classes = [IsManager]

    def put(self, request, user_id):
        user = get_object_or_404(
            get_user_model().objects.select_related('worker_profile'),
            pk=user_id,
            worker_profile__isnull=False,
        )
        form = WorkerAccountEditForm(request.data, user=user, current_user=request.user)
        if not form.is_valid():
            return Response({'errors': form.errors}, status=400)
        form.save()
        return Response(WorkerSerializer(user).data)


# --- Manager: table configuration -----------------------------------------


class TableConfigListView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        tables = RestaurantTable.objects.order_by('identifier')
        return Response(RestaurantTableSerializer(tables, many=True).data)

    def post(self, request):
        form = RestaurantTableForm(request.data)
        if not form.is_valid():
            return Response({'errors': form.errors}, status=400)
        table = form.save()
        return Response(RestaurantTableSerializer(table).data, status=201)


class TableConfigDetailView(APIView):
    permission_classes = [IsManager]

    def put(self, request, table_id):
        table = get_object_or_404(RestaurantTable, pk=table_id)
        form = RestaurantTableForm(request.data, instance=table)
        if not form.is_valid():
            return Response({'errors': form.errors}, status=400)
        form.save()
        return Response(RestaurantTableSerializer(table).data)

    def delete(self, request, table_id):
        table = get_object_or_404(RestaurantTable, pk=table_id)
        active_statuses = {RestaurantTable.Status.RESERVED, RestaurantTable.Status.OCCUPIED}
        if table.status in active_statuses:
            return Response(
                {'detail': 'Reserved or occupied tables cannot be removed.'},
                status=409,
            )
        table.delete()
        return Response(status=204)


# --- Manager: ETA configuration --------------------------------------------


class EtaConfigView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        settings_row = RestaurantSettings.get_active()
        rules = EtaRule.objects.order_by('min_party_size', 'max_party_size')
        return Response({
            'settings': RestaurantSettingsSerializer(settings_row).data,
            'rules': EtaRuleSerializer(rules, many=True).data,
        })


class EtaRuleListView(APIView):
    permission_classes = [IsManager]

    def post(self, request):
        form = EtaRuleForm(request.data)
        if not form.is_valid():
            return Response({'errors': form.errors}, status=400)
        rule = form.save()
        return Response(EtaRuleSerializer(rule).data, status=201)


class EtaRuleDetailView(APIView):
    permission_classes = [IsManager]

    def put(self, request, rule_id):
        rule = get_object_or_404(EtaRule, pk=rule_id)
        form = EtaRuleForm(request.data, instance=rule)
        if not form.is_valid():
            return Response({'errors': form.errors}, status=400)
        form.save()
        return Response(EtaRuleSerializer(rule).data)


class EtaGracePeriodView(APIView):
    permission_classes = [IsManager]

    def put(self, request):
        settings_row = RestaurantSettings.get_active()
        form = GracePeriodForm(request.data, instance=settings_row)
        if not form.is_valid():
            return Response({'errors': form.errors}, status=400)
        form.save()
        return Response(RestaurantSettingsSerializer(settings_row).data)
