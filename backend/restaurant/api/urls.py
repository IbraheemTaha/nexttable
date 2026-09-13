from django.urls import path

from . import views

app_name = 'restaurant_api'

urlpatterns = [
    path('auth/csrf/', views.csrf_view, name='csrf'),
    path('auth/login/', views.login_view, name='login'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/me/', views.current_user_view, name='me'),

    path('check-in/<str:token>/', views.guest_check_in_view, name='check_in'),
    path(
        'check-in/status/<uuid:public_identifier>/',
        views.guest_check_in_status_view,
        name='check_in_status',
    ),
    path(
        'check-in/status/<uuid:public_identifier>/cancel/',
        views.guest_check_in_cancel_view,
        name='check_in_cancel',
    ),

    path('waitlist/', views.WaitlistView.as_view(), name='waitlist'),
    path(
        'waitlist/<int:entry_id>/action/<str:action>/',
        views.WaitlistEntryActionView.as_view(),
        name='waitlist_entry_action',
    ),
    path('waitlist/assign/', views.ManualTableAssignmentView.as_view(), name='waitlist_assign'),

    path('tables/', views.TableStatusView.as_view(), name='tables'),
    path(
        'tables/<int:table_id>/status/<str:target_status>/',
        views.TableStatusActionView.as_view(),
        name='table_status_action',
    ),

    path('workers/', views.WorkerListView.as_view(), name='workers'),
    path('workers/<int:user_id>/', views.WorkerDetailView.as_view(), name='worker_detail'),

    path('table-config/', views.TableConfigListView.as_view(), name='table_config'),
    path(
        'table-config/<int:table_id>/',
        views.TableConfigDetailView.as_view(),
        name='table_config_detail',
    ),

    path('eta/', views.EtaConfigView.as_view(), name='eta_config'),
    path('eta/rules/', views.EtaRuleListView.as_view(), name='eta_rules'),
    path('eta/rules/<int:rule_id>/', views.EtaRuleDetailView.as_view(), name='eta_rule_detail'),
    path('eta/grace-period/', views.EtaGracePeriodView.as_view(), name='eta_grace_period'),
]
