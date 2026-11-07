import hashlib
import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core import mail
from django.utils import timezone
import pyotp
from django.test import Client
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import MFADevice, MFARecoveryCode
from .security import encrypt_totp_secret

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountApiTests(APITestCase):
    def setUp(self):
        cache.clear()

    def _email_token(self, query_name):
        match = re.search(rf"[?&]{query_name}=([A-Za-z0-9_-]+)", mail.outbox[-1].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_registration_creates_account_and_returns_token(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {
                "email": "Person@Example.com",
                "first_name": "Ari",
                "password": "secure-test-password-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user"]["email"], "person@example.com")
        self.assertTrue(response.data["token"])
        self.assertFalse(response.data["user"]["email_verified"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            User.objects.get(email="person@example.com").check_password(
                "secure-test-password-1"
            )
        )

    def test_email_verification_is_one_time_and_gates_protected_apis(self):
        registration = self.client.post(
            "/api/v1/auth/register/",
            {
                "email": "verify@example.com",
                "password": "secure-test-password-1",
            },
            format="json",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {registration.data['token']}"
        )
        self.assertEqual(self.client.get("/api/v1/organizations/").status_code, 401)

        token = self._email_token("verify_email")
        verified = self.client.post(
            "/api/v1/auth/email/verification/",
            {"token": token},
            format="json",
        )
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.data["email_verified"])
        self.assertTrue(User.objects.get(email="verify@example.com").email_verified)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/email/verification/",
                {"token": token},
                format="json",
            ).status_code,
            400,
        )

    def test_password_reset_is_generic_one_time_and_revokes_existing_tokens(self):
        user = User.objects.create_user(
            email="reset@example.com",
            password="secure-test-password",
        )
        old_token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {old_token.key}")

        unknown = self.client.post(
            "/api/v1/auth/password/reset/request/",
            {"email": "nobody@example.com"},
            format="json",
        )
        requested = self.client.post(
            "/api/v1/auth/password/reset/request/",
            {"email": user.email},
            format="json",
        )
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(unknown.data, requested.data)
        self.assertEqual(len(mail.outbox), 1)

        reset_token = self._email_token("reset_password")
        changed = self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {"token": reset_token, "password": "new-strong-password-2"},
            format="json",
        )
        self.assertEqual(changed.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("new-strong-password-2"))
        self.assertFalse(Token.objects.filter(key=old_token.key).exists())
        self.client.credentials()
        replay = self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {"token": reset_token, "password": "another-strong-password-3"},
            format="json",
        )
        self.assertEqual(replay.status_code, 400)
        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "new-strong-password-2"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user(email="person@example.com", password="secure-test-password")

        response = self.client.post(
            "/api/v1/auth/register/",
            {"email": "PERSON@example.com", "password": "another-secure-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_login_and_current_user_require_valid_credentials(self):
        user = User.objects.create_user(
            email="person@example.com",
            password="secure-test-password",
        )
        invalid = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 401)

        logged_in = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email.upper(), "password": "secure-test-password"},
            format="json",
        )
        self.assertEqual(logged_in.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {logged_in.data['token']}")
        current_user = self.client.get("/api/v1/auth/me/")
        self.assertEqual(current_user.status_code, 200)
        self.assertEqual(current_user.data["id"], user.id)
        updated = self.client.patch(
            "/api/v1/auth/me/", {"first_name": "Ari"}, format="json"
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["first_name"], "Ari")

    def test_registration_requires_mfa_setup_before_protected_api_access(self):
        registration = self.client.post(
            "/api/v1/auth/register/",
            {
                "email": "mfa@example.com",
                "first_name": "Mfa",
                "password": "secure-test-password-1",
            },
            format="json",
        )
        self.assertEqual(registration.status_code, 201)
        old_token = registration.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {old_token}")

        current_user = self.client.get("/api/v1/auth/me/")
        self.assertEqual(current_user.status_code, 200)
        self.assertFalse(current_user.data["mfa_enrolled"])
        self.assertEqual(self.client.get("/api/v1/organizations/").status_code, 401)

        setup = self.client.post("/api/v1/auth/mfa/setup/", {}, format="json")
        repeated_setup = self.client.post("/api/v1/auth/mfa/setup/", {}, format="json")
        self.assertEqual(setup.status_code, 200)
        self.assertEqual(repeated_setup.data["secret"], setup.data["secret"])
        device = MFADevice.objects.get(user__email="mfa@example.com")
        self.assertNotIn(setup.data["secret"], device.encrypted_secret)
        self.assertEqual(device.get_secret(), setup.data["secret"])

        confirmation = self.client.post(
            "/api/v1/auth/mfa/confirm/",
            {"code": pyotp.TOTP(setup.data["secret"]).now()},
            format="json",
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(confirmation.data["user"]["mfa_enrolled"])
        self.assertEqual(len(confirmation.data["recovery_codes"]), 10)
        self.assertFalse(Token.objects.filter(key=old_token).exists())

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {confirmation.data['token']}")
        self.assertEqual(self.client.get("/api/v1/organizations/").status_code, 401)
        verification_token = self._email_token("verify_email")
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/email/verification/",
                {"token": verification_token},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/v1/organizations/").status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {old_token}")
        self.assertEqual(self.client.get("/api/v1/organizations/").status_code, 401)

    def test_mfa_login_challenge_accepts_totp_once_and_prevents_replay(self):
        user = User.objects.create_user(
            email="mfa@example.com",
            password="secure-test-password",
        )
        secret = pyotp.random_base32()
        MFADevice.objects.create(
            user=user,
            encrypted_secret=encrypt_totp_secret(secret),
            confirmed_at=timezone.now(),
        )

        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "secure-test-password"},
            format="json",
        )
        self.assertEqual(login.status_code, 202)
        self.assertTrue(login.data["mfa_required"])

        verified = self.client.post(
            "/api/v1/auth/login/mfa/",
            {
                "challenge_id": login.data["challenge_id"],
                "code": pyotp.TOTP(secret).now(),
            },
            format="json",
        )
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.data["user"]["mfa_enrolled"])
        replay = self.client.post(
            "/api/v1/auth/login/mfa/",
            {
                "challenge_id": login.data["challenge_id"],
                "code": pyotp.TOTP(secret).now(),
            },
            format="json",
        )
        self.assertEqual(replay.status_code, 400)

        next_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "secure-test-password"},
            format="json",
        )
        reused_code = self.client.post(
            "/api/v1/auth/login/mfa/",
            {
                "challenge_id": next_login.data["challenge_id"],
                "code": pyotp.TOTP(secret).now(),
            },
            format="json",
        )
        self.assertEqual(reused_code.status_code, 401)

    def test_recovery_code_is_hashed_and_single_use(self):
        user = User.objects.create_user(
            email="mfa@example.com",
            password="secure-test-password",
        )
        secret = pyotp.random_base32()
        MFADevice.objects.create(
            user=user,
            encrypted_secret=encrypt_totp_secret(secret),
            confirmed_at=timezone.now(),
        )
        recovery_code = "01234567-89ABCDEF-01234567-89ABCDEF"
        stored_recovery = MFARecoveryCode.objects.create(
            user=user,
            code_hash=hashlib.sha256(
                recovery_code.replace("-", "").encode()
            ).hexdigest(),
        )

        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "secure-test-password"},
            format="json",
        )
        verified = self.client.post(
            "/api/v1/auth/login/mfa/",
            {
                "challenge_id": login.data["challenge_id"],
                "code": recovery_code,
            },
            format="json",
        )
        self.assertEqual(verified.status_code, 200)
        stored_recovery.refresh_from_db()
        self.assertIsNotNone(stored_recovery.used_at)
        self.assertNotIn(recovery_code, stored_recovery.code_hash)

        second_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "secure-test-password"},
            format="json",
        )
        reused = self.client.post(
            "/api/v1/auth/login/mfa/",
            {
                "challenge_id": second_login.data["challenge_id"],
                "code": recovery_code,
            },
            format="json",
        )
        self.assertEqual(reused.status_code, 401)

    def test_django_admin_requires_mfa_on_login_and_existing_sessions(self):
        user = User.objects.create_user(
            email="admin@example.com",
            password="secure-test-password",
            is_staff=True,
        )
        client = Client()
        missing_factor = client.post(
            "/admin/login/",
            {
                "username": user.email,
                "password": "secure-test-password",
                "otp_code": "123456",
            },
        )
        self.assertEqual(missing_factor.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

        secret = pyotp.random_base32()
        MFADevice.objects.create(
            user=user,
            encrypted_secret=encrypt_totp_secret(secret),
            confirmed_at=timezone.now(),
        )
        login = client.post(
            "/admin/login/",
            {
                "username": user.email,
                "password": "secure-test-password",
                "otp_code": pyotp.TOTP(secret).now(),
            },
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(client.get("/admin/").status_code, 200)

        recovery_code = "01234567-89ABCDEF-01234567-89ABCDEF"
        MFARecoveryCode.objects.create(
            user=user,
            code_hash=hashlib.sha256(
                recovery_code.replace("-", "").encode()
            ).hexdigest(),
        )
        old_session = Client()
        old_session.force_login(user)
        blocked = old_session.get("/admin/")
        self.assertRedirects(blocked, "/admin/mfa/", fetch_redirect_response=False)
        verified = old_session.post("/admin/mfa/", {"code": recovery_code})
        self.assertEqual(verified.status_code, 302)
        self.assertEqual(old_session.get("/admin/").status_code, 200)
