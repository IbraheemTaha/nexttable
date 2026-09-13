from django.urls import path

from . import views

app_name = 'restaurant'

urlpatterns = [
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
]
