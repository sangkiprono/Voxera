from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Membership, Organization

User = get_user_model()


class OrganizationApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", password="secure-test-password"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="secure-test-password"
        )

    def test_creator_becomes_owner_and_other_users_cannot_access_workspace(self):
        self.client.force_authenticate(self.owner)
        created = self.client.post(
            "/api/v1/organizations/",
            {"name": "Northstar", "slug": "northstar", "description": "A workspace"},
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["role"], Membership.Role.OWNER)
        self.assertEqual(created.data["member_count"], 1)
        self.assertTrue(
            Membership.objects.filter(
                organization__slug="northstar",
                user=self.owner,
                role=Membership.Role.OWNER,
            ).exists()
        )

        self.client.force_authenticate(self.other_user)
        self.assertEqual(
            self.client.get("/api/v1/organizations/northstar/").status_code, 404
        )

    def test_owner_can_add_existing_member_but_member_cannot_manage_members(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        Membership.objects.create(
            organization=organization, user=self.owner, role=Membership.Role.OWNER
        )
        self.client.force_authenticate(self.owner)
        added = self.client.post(
            "/api/v1/organizations/northstar/members/",
            {"email": self.other_user.email, "role": Membership.Role.MEMBER},
            format="json",
        )
        self.assertEqual(added.status_code, 201)

        self.client.force_authenticate(self.other_user)
        denied = self.client.post(
            "/api/v1/organizations/northstar/members/",
            {"email": self.owner.email, "role": Membership.Role.ADMIN},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_workspace_with_activities_cannot_be_deleted(self):
        from surveys.models import Survey

        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        Membership.objects.create(
            organization=organization, user=self.owner, role=Membership.Role.OWNER
        )
        Survey.objects.create(
            title="Team feedback",
            created_by=self.owner,
            organization=organization,
        )
        self.client.force_authenticate(self.owner)

        response = self.client.delete("/api/v1/organizations/northstar/")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Organization.objects.filter(pk=organization.pk).exists())
