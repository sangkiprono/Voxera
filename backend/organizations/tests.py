from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from polls.models import Poll, PollOption, PollResponse
from surveys.models import Survey, SurveyResponse
from notifications.models import Notification

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
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.other_user,
                kind=Notification.Kind.WORKSPACE_ADDED,
                organization__slug="northstar",
            ).exists()
        )

        self.client.force_authenticate(self.other_user)
        denied = self.client.post(
            "/api/v1/organizations/northstar/members/",
            {"email": self.owner.email, "role": Membership.Role.ADMIN},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_workspace_with_activities_cannot_be_deleted(self):
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

    def test_workspace_with_election_cannot_be_deleted(self):
        from elections.models import Election

        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        Membership.objects.create(
            organization=organization, user=self.owner, role=Membership.Role.OWNER
        )
        Election.objects.create(
            organization=organization,
            title="Board election",
            created_by=self.owner,
        )
        self.client.force_authenticate(self.owner)

        response = self.client.delete("/api/v1/organizations/northstar/")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Organization.objects.filter(pk=organization.pk).exists())

    def test_workspace_analytics_are_scoped_to_organization_administrators(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        Membership.objects.create(
            organization=organization, user=self.owner, role=Membership.Role.OWNER
        )
        poll = Poll.objects.create(
            title="Team lunch",
            question="Where should we go?",
            created_by=self.owner,
            organization=organization,
        )
        option = PollOption.objects.create(poll=poll, text="Cafe", position=0)
        PollResponse.objects.create(poll=poll, user=self.other_user, option=option)
        another_voter = User.objects.create_user(
            email="another-voter@example.com", password="test-pass-12345"
        )
        popular_poll = Poll.objects.create(
            title="Popular poll",
            question="Which option?",
            created_by=self.owner,
            organization=organization,
        )
        popular_option = PollOption.objects.create(
            poll=popular_poll, text="First", position=0
        )
        PollResponse.objects.create(
            poll=popular_poll, user=self.other_user, option=popular_option
        )
        PollResponse.objects.create(
            poll=popular_poll, user=another_voter, option=popular_option
        )
        Poll.objects.create(
            title="Outside poll",
            question="Not part of this workspace",
            created_by=self.owner,
        )
        survey = Survey.objects.create(
            title="Team feedback",
            created_by=self.owner,
            organization=organization,
        )
        SurveyResponse.objects.create(survey=survey, user=self.other_user)
        popular_survey = Survey.objects.create(
            title="Popular survey",
            created_by=self.owner,
            organization=organization,
        )
        SurveyResponse.objects.create(survey=popular_survey, user=self.other_user)
        SurveyResponse.objects.create(survey=popular_survey, user=another_voter)
        url = "/api/v1/organizations/northstar/analytics/"

        self.client.force_authenticate(self.owner)
        analytics = self.client.get(url)
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.data["member_count"], 1)
        self.assertEqual(analytics.data["poll_count"], 2)
        self.assertEqual(analytics.data["active_poll_count"], 2)
        self.assertEqual(analytics.data["poll_response_count"], 3)
        self.assertEqual(analytics.data["survey_count"], 2)
        self.assertEqual(analytics.data["active_survey_count"], 2)
        self.assertEqual(analytics.data["survey_response_count"], 3)
        self.assertEqual(
            analytics.data["top_polls"][0],
            {
                "id": popular_poll.id,
                "title": "Popular poll",
                "status": Poll.Status.ACTIVE,
                "response_count": 2,
            },
        )
        self.assertEqual(
            analytics.data["top_surveys"][0],
            {
                "id": popular_survey.id,
                "title": "Popular survey",
                "status": Survey.Status.ACTIVE,
                "response_count": 2,
            },
        )
        self.assertNotIn(
            "Outside poll", [item["title"] for item in analytics.data["top_polls"]]
        )
        self.assertEqual(len(analytics.data["daily_activity"]), 30)
        self.assertEqual(
            analytics.data["daily_activity"][-1]["date"],
            timezone.localdate().isoformat(),
        )
        self.assertEqual(
            analytics.data["daily_activity"][-1]["poll_responses"], 3
        )
        self.assertEqual(
            analytics.data["daily_activity"][-1]["survey_responses"], 3
        )

        Membership.objects.create(
            organization=organization,
            user=self.other_user,
            role=Membership.Role.MEMBER,
        )
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(url).status_code, 403)

        Membership.objects.filter(organization=organization, user=self.other_user).delete()
        self.assertEqual(self.client.get(url).status_code, 404)
