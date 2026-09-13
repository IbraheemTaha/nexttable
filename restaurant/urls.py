from django.urls import path

from . import views

app_name = 'restaurant'

urlpatterns = [
    path('staff/', views.staff_landing, name='staff_landing'),
    path('manager/', views.manager_landing, name='manager_landing'),
]
