from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction

from .mfa import consume_mfa_code
from .models import MFADevice


class MFAAdminAuthenticationForm(AdminAuthenticationForm):
    otp_code = forms.CharField(
        label="Authenticator or recovery code",
        max_length=40,
        strip=True,
    )

    def clean(self):
        cleaned_data = super().clean()
        user = self.get_user()
        if user is None:
            return cleaned_data
        with transaction.atomic():
            if not MFADevice.objects.filter(
                user=user, confirmed_at__isnull=False
            ).exists():
                raise ValidationError(
                    "Set up an authenticator through the Voxera application before using admin."
                )
            if not consume_mfa_code(user, cleaned_data["otp_code"]):
                raise ValidationError(
                    "The authenticator or recovery code is invalid."
                )
            self.request.session["voxera_admin_mfa_user_id"] = user.pk
        return cleaned_data
