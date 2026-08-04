"""Web admin views.

M0 delivers login, logout and a placeholder shell. Business screens arrive from M1.
"""

from __future__ import annotations

from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from core.exceptions import DomainError
from core.permissions import Role, has_role, role_codes
from core.services import client_ip
from identity.services import authenticate_password


@csrf_protect
@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("webadmin:dashboard")

    error = ""
    if request.method == "POST":
        try:
            user = authenticate_password(
                phone=request.POST.get("phone", ""),
                password=request.POST.get("password", ""),
                ip_address=client_ip(request),
            )
        except DomainError as exc:
            error = exc.detail
        else:
            if not has_role(user, *Role.INTERNAL):
                # Retailers use the app, not the admin (05 §8).
                error = "This account cannot sign in here."
            else:
                django_login(request, user, backend="identity.backends.PhoneBackend")
                return redirect("webadmin:dashboard")

    return render(request, "webadmin/login.html", {"error": error})


@require_http_methods(["POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    django_logout(request)
    return redirect("webadmin:login")


@login_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    # request.user is User | AnonymousUser at the type level. core.permissions does the
    # narrowing once, so the view neither casts nor imports the model (N-02).
    return render(
        request,
        "webadmin/dashboard.html",
        {"roles": role_codes(request.user)},
    )
