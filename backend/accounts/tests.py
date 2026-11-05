from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


class AccountApiTests(APITestCase):
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
        self.assertTrue(
            User.objects.get(email="person@example.com").check_password(
                "secure-test-password-1"
            )
        )

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user(
            email="person@example.com", password="secure-test-password"
        )

        response = self.client.post(
            "/api/v1/auth/register/",
            {"email": "PERSON@example.com", "password": "another-secure-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_login_and_current_user_require_valid_credentials(self):
        user = User.objects.create_user(
            email="person@example.com", password="secure-test-password"
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
