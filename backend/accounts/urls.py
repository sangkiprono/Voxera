from django.urls import path

from .views import (
    CurrentUserView,
    EmailVerificationView,
    LoginView,
    LogoutView,
    MFALoginView,
    MFASetupConfirmView,
    MFASetupView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    ResendEmailVerificationView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("login/mfa/", MFALoginView.as_view(), name="mfa-login"),
    path("mfa/setup/", MFASetupView.as_view(), name="mfa-setup"),
    path("mfa/confirm/", MFASetupConfirmView.as_view(), name="mfa-confirm"),
    path("email/verification/", EmailVerificationView.as_view(), name="email-verification"),
    path(
        "email/verification/resend/",
        ResendEmailVerificationView.as_view(),
        name="email-verification-resend",
    ),
    path("password/reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
]
