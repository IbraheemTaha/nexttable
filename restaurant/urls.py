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
    path('staff/', views.staff_landing, name='staff_landing'),
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
]
