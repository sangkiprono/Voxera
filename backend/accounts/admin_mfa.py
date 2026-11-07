from django.contrib.auth import REDIRECT_FIELD_NAME
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views import View

from .mfa import consume_mfa_code
from .models import MFADevice


class AdminMFAVerifyView(View):
    template_name = "accounts/admin_mfa_verify.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/admin/login/?{REDIRECT_FIELD_NAME}=/admin/")
        if not request.user.is_staff:
            return HttpResponseForbidden("Staff access is required.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        enrolled = MFADevice.objects.filter(
            user=request.user, confirmed_at__isnull=False
        ).exists()
        return render(
            request,
            self.template_name,
            {"mfa_enrolled": enrolled, "error": ""},
        )

    def post(self, request):
        enrolled = MFADevice.objects.filter(
            user=request.user, confirmed_at__isnull=False
        ).exists()
        if not enrolled:
            return render(
                request,
                self.template_name,
                {
                    "mfa_enrolled": False,
                    "error": "Set up an authenticator in the Voxera app before returning here.",
                },
                status=403,
            )

        with transaction.atomic():
            if not consume_mfa_code(request.user, request.POST.get("code", "")):
                return render(
                    request,
                    self.template_name,
                    {
                        "mfa_enrolled": True,
                        "error": "The authenticator or recovery code is invalid.",
                    },
                    status=400,
                )
            request.session["voxera_admin_mfa_user_id"] = request.user.pk
        return redirect("/admin/")
