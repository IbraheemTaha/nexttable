"""
Project-level placeholder views.

This module only exists to prove the shared base template/static pipeline
works end to end (see issue #2). It intentionally contains no business
logic - the actual guest/staff/manager pages are built in later issues.
"""
from django.shortcuts import render


def placeholder(request):
    """Render the shared base layout with minimal placeholder content."""
    return render(request, 'placeholder.html')
