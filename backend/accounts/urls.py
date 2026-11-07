from django.urls import path

from .views import (
    CurrentUserView,
    LoginView,
    LogoutView,
    MFALoginView,
    MFASetupConfirmView,
    MFASetupView,
    RegisterView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("login/mfa/", MFALoginView.as_view(), name="mfa-login"),
    path("mfa/setup/", MFASetupView.as_view(), name="mfa-setup"),
    path("mfa/confirm/", MFASetupConfirmView.as_view(), name="mfa-confirm"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
]
