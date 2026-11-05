from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from organizations.models import Organization

from .models import Notification

User = get_user_model()


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", password="Test-password-42!"
        )
        self.member = User.objects.create_user(
            email="member@example.com", password="Test-password-42!"
        )
        self.organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        self.notification = Notification.objects.create(
            recipient=self.owner,
            actor=self.member,
            kind=Notification.Kind.WORKSPACE_ADDED,
            message="You were added to Northstar",
            organization=self.organization,
        )

    def test_notifications_and_unread_count_are_limited_to_the_recipient(self):
        self.client.force_authenticate(self.owner)
        inbox = self.client.get("/api/v1/notifications/")
        count = self.client.get("/api/v1/notifications/unread-count/")

        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(len(inbox.data), 1)
        self.assertEqual(inbox.data[0]["organization_slug"], "northstar")
        self.assertEqual(inbox.data[0]["actor_name"], "Voxera member")
        self.assertEqual(count.data["unread_count"], 1)

        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/v1/notifications/").data, [])
        self.assertEqual(
            self.client.post(
                f"/api/v1/notifications/{self.notification.id}/read/"
            ).status_code,
            404,
        )

    def test_recipient_can_mark_one_or_all_notifications_as_read(self):
        another = Notification.objects.create(
            recipient=self.owner,
            actor=self.member,
            kind=Notification.Kind.WORKSPACE_ADDED,
            message="Another update",
            organization=self.organization,
        )
        self.client.force_authenticate(self.owner)

        marked = self.client.post(
            f"/api/v1/notifications/{self.notification.id}/read/"
        )
        mark_all = self.client.post("/api/v1/notifications/read-all/")
        count = self.client.get("/api/v1/notifications/unread-count/")

        self.assertEqual(marked.status_code, 200)
        self.assertIsNotNone(marked.data["read_at"])
        self.assertEqual(mark_all.data["updated_count"], 1)
        self.assertEqual(count.data["unread_count"], 0)
        self.assertIsNotNone(
            Notification.objects.get(pk=another.pk).read_at
        )
