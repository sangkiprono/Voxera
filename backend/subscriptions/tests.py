from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from organizations.models import Membership, Organization
from polls.models import Poll
from surveys.models import Survey

from .models import OrganizationSubscription, SubscriptionPlan

User = get_user_model()


class SubscriptionFoundationTests(APITestCase):
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
        Membership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        self.plan = SubscriptionPlan.objects.create(
            code="team",
            name="Team",
            monthly_price_minor=2500,
            currency="KES",
            max_members=2,
            max_active_polls=1,
            max_active_surveys=1,
        )
        OrganizationSubscription.objects.create(
            organization=self.organization, plan=self.plan
        )
        self.client.force_authenticate(self.owner)

    def test_owner_can_view_plan_and_usage_but_members_cannot(self):
        Poll.objects.create(
            title="Team poll",
            question="Where next?",
            created_by=self.owner,
            organization=self.organization,
        )
        response = self.client.get(
            "/api/v1/organizations/northstar/subscription/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subscription"]["plan_code"], "team")
        self.assertEqual(
            response.data["subscription"]["monthly_price_minor"], 2500
        )
        self.assertEqual(response.data["subscription"]["currency"], "KES")
        self.assertEqual(response.data["usage"]["members"], 1)
        self.assertEqual(response.data["usage"]["active_polls"], 1)

        Membership.objects.create(
            organization=self.organization,
            user=self.member,
            role=Membership.Role.MEMBER,
        )
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.get(
                "/api/v1/organizations/northstar/subscription/"
            ).status_code,
            403,
        )

    def test_member_and_activity_limits_apply_only_after_a_plan_is_assigned(self):
        member_request = self.client.post(
            "/api/v1/organizations/northstar/members/",
            {"email": self.member.email, "role": Membership.Role.MEMBER},
            format="json",
        )
        self.assertEqual(member_request.status_code, 201)
        other = User.objects.create_user(
            email="other@example.com", password="Test-password-42!"
        )
        over_limit_member = self.client.post(
            "/api/v1/organizations/northstar/members/",
            {"email": other.email, "role": Membership.Role.MEMBER},
            format="json",
        )
        self.assertEqual(over_limit_member.status_code, 400)

        Poll.objects.create(
            title="First poll",
            question="First?",
            created_by=self.owner,
            organization=self.organization,
        )
        poll = self.client.post(
            "/api/v1/polls/",
            {
                "title": "Second poll",
                "question": "Second?",
                "organization": self.organization.id,
                "options": ["Yes", "No"],
            },
            format="json",
        )
        self.assertEqual(poll.status_code, 400)

        Survey.objects.create(
            title="First survey",
            created_by=self.owner,
            organization=self.organization,
        )
        survey = self.client.post(
            "/api/v1/surveys/",
            {
                "title": "Second survey",
                "organization": self.organization.id,
                "questions": [
                    {
                        "text": "Feedback?",
                        "question_type": "short_text",
                        "is_required": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(survey.status_code, 400)

    def test_organizations_without_a_plan_have_no_artificial_member_cap(self):
        OrganizationSubscription.objects.filter(
            organization=self.organization
        ).delete()
        self.plan.max_members = 1
        self.plan.save(update_fields=["max_members"])
        response = self.client.post(
            "/api/v1/organizations/northstar/members/",
            {"email": self.member.email, "role": Membership.Role.MEMBER},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
