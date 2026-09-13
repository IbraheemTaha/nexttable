from django.shortcuts import render

from .auth import manager_required, staff_or_manager_required


@staff_or_manager_required
def staff_landing(request):
    return render(request, 'restaurant/staff_landing.html')


@manager_required
def manager_landing(request):
    return render(request, 'restaurant/manager_landing.html')
