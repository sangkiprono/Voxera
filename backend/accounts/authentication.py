from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class MFAEnforcingTokenAuthentication(TokenAuthentication):
    setup_paths = {
        "/api/v1/auth/register/",
        "/api/v1/auth/login/",
        "/api/v1/auth/login/mfa/",
        "/api/v1/auth/me/",
        "/api/v1/auth/logout/",
        "/api/v1/auth/mfa/setup/",
        "/api/v1/auth/mfa/confirm/",
    }

    def authenticate(self, request):
        authenticated = super().authenticate(request)
        if authenticated is None:
            return None

        user, token = authenticated
        if request.path not in self.setup_paths:
            from .models import MFADevice

            if not MFADevice.objects.filter(
                user=user, confirmed_at__isnull=False
            ).exists():
                raise AuthenticationFailed(
                    "Complete authenticator setup before using Voxera.",
                    code="mfa_setup_required",
                )
        return user, token
