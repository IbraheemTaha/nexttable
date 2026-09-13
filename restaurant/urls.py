from django.urls import path

from . import views

app_name = 'restaurant'

urlpatterns = [
    path(
        'check-in/<str:token>/',
        views.guest_check_in,
        name='guest_check_in',
    ),
    path(
        'check-in/<str:token>/submit/',
        views.guest_check_in_submit,
        name='guest_check_in_submit',
    ),
    path(
        'check-in/status/<uuid:public_identifier>/',
        views.guest_check_in_status,
        name='guest_check_in_status',
    ),
    path(
        'check-in/status/<uuid:public_identifier>/partial/',
        views.guest_check_in_status_partial,
        name='guest_check_in_status_partial',
    ),
    path(
        'check-in/status/<uuid:public_identifier>/cancel/',
        views.guest_check_in_cancel,
        name='guest_check_in_cancel',
    ),
    path('staff/', views.staff_landing, name='staff_landing'),
    path('staff/waitlist/', views.waitlist, name='waitlist'),
    path(
        'staff/waitlist/<int:entry_id>/<str:action>/',
        views.waitlist_entry_action,
        name='waitlist_entry_action',
    ),
    path('staff/tables/', views.table_status, name='table_status'),
    path('manager/', views.manager_landing, name='manager_landing'),
    path(
        'manager/workers/',
        views.worker_account_list,
        name='worker_account_list',
    ),
    path(
        'manager/workers/new/',
        views.worker_account_create,
        name='worker_account_create',
    ),
    path(
        'manager/workers/<int:user_id>/edit/',
        views.worker_account_edit,
        name='worker_account_edit',
    ),
    path(
        'manager/tables/',
        views.table_config_list,
        name='table_config_list',
    ),
    path(
        'manager/tables/new/',
        views.table_config_create,
        name='table_config_create',
    ),
    path(
        'manager/tables/<int:table_id>/edit/',
        views.table_config_edit,
        name='table_config_edit',
    ),
    path(
        'manager/tables/<int:table_id>/remove/',
        views.table_config_remove,
        name='table_config_remove',
    ),
    path(
        'manager/eta/',
        views.eta_config,
        name='eta_config',
    ),
    path(
        'manager/eta/rules/new/',
        views.eta_rule_create,
        name='eta_rule_create',
    ),
    path(
        'manager/eta/rules/<int:rule_id>/edit/',
        views.eta_rule_edit,
        name='eta_rule_edit',
    ),
    path(
        'manager/eta/grace-period/',
        views.eta_grace_period_edit,
        name='eta_grace_period_edit',
    ),
]
