from django.shortcuts import redirect


class AdminMFAMiddleware:
    exempt_paths = {
        "/admin/login/",
        "/admin/logout/",
        "/admin/mfa/",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path.startswith("/admin/")
            and request.path not in self.exempt_paths
            and request.user.is_authenticated
            and request.user.is_staff
            and request.session.get("voxera_admin_mfa_user_id") != request.user.pk
        ):
            return redirect("/admin/mfa/")
        return self.get_response(request)
