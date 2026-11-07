import hashlib
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from polls.models import Poll, PollOption, PollResponse
from surveys.models import Survey, SurveyResponse
from notifications.models import Notification

from .models import Membership, Organization, OrganizationInvitation

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OrganizationApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", password="secure-test-password"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="secure-test-password"
        )

    def _approved_organization(self):
        organization = Organization.objects.create(
            name="Northstar",
            slug="northstar",
            created_by=self.owner,
            status=Organization.Status.APPROVED,
        )
        Membership.objects.create(
            organization=organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        return organization

    def _send_invitation(self, email="other@example.com", role="member"):
        response = self.client.post(
            "/api/v1/organizations/northstar/invitations/",
            {"email": email, "role": role},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        match = re.search(
            r"[?&]accept_invite=([A-Za-z0-9_-]+)", mail.outbox[-1].body
        )
        self.assertIsNotNone(match)
        return response, match.group(1)

    def test_invitation_is_hashed_expires_and_requires_matching_verified_account(self):
        self._approved_organization()
        self.client.force_authenticate(self.owner)
        invitation_response, raw_token = self._send_invitation(
            role=Membership.Role.CREATOR
        )
        invitation = OrganizationInvitation.objects.get()
        self.assertEqual(invitation.email, self.other_user.email)
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)
        self.assertEqual(
            invitation.token_digest,
            hashlib.sha256(raw_token.encode()).hexdigest(),
        )
        self.assertNotIn(raw_token, invitation.token_digest)
        self.assertEqual(invitation_response.data["status"], "pending")
        self.assertEqual(len(mail.outbox), 1)

        duplicate = self.client.post(
            "/api/v1/organizations/northstar/invitations/",
            {"email": self.other_user.email, "role": Membership.Role.MEMBER},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(len(mail.outbox), 1)

        listed = self.client.get("/api/v1/organizations/northstar/invitations/")
        self.assertEqual(len(listed.data), 1)
        self.assertNotIn("token_digest", listed.data[0])

        self.other_user.email_verified = False
        self.other_user.save(update_fields=["email_verified"])
        self.client.force_authenticate(self.other_user)
        unverified = self.client.post(
            "/api/v1/organizations/invitations/accept/",
            {"token": raw_token},
            format="json",
        )
        self.assertEqual(unverified.status_code, 403)
        self.other_user.email_verified = True
        self.other_user.save(update_fields=["email_verified"])

        self.client.force_authenticate(self.owner)
        mismatch = self.client.post(
            "/api/v1/organizations/invitations/accept/",
            {"token": raw_token},
            format="json",
        )
        self.assertEqual(mismatch.status_code, 403)
        self.client.force_authenticate(self.other_user)
        accepted = self.client.post(
            "/api/v1/organizations/invitations/accept/",
            {"token": raw_token},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data["organization_name"], "Northstar")
        self.assertEqual(accepted.data["membership"]["role"], Membership.Role.CREATOR)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.ACCEPTED)
        self.assertTrue(
            Membership.objects.filter(
                organization=invitation.organization, user=self.other_user
            ).exists()
        )
        replay = self.client.post(
            "/api/v1/organizations/invitations/accept/",
            {"token": raw_token},
            format="json",
        )
        self.assertEqual(replay.status_code, 404)

    def test_invitation_can_be_revoked_and_expired_invitation_replaced(self):
        self._approved_organization()
        self.client.force_authenticate(self.owner)
        response, raw_token = self._send_invitation()
        revoked = self.client.post(
            f"/api/v1/organizations/northstar/invitations/{response.data['id']}/revoke/",
            {},
            format="json",
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(revoked.data["status"], OrganizationInvitation.Status.REVOKED)
        self.client.force_authenticate(self.other_user)
        invalid = self.client.post(
            "/api/v1/organizations/invitations/accept/",
            {"token": raw_token},
            format="json",
        )
        self.assertEqual(invalid.status_code, 404)

        self.client.force_authenticate(self.owner)
        replacement, replacement_token = self._send_invitation()
        current = OrganizationInvitation.objects.get(pk=replacement.data["id"])
        current.expires_at = timezone.now() - timedelta(seconds=1)
        current.save(update_fields=["expires_at"])
        self.client.force_authenticate(self.other_user)
        expired = self.client.post(
            "/api/v1/organizations/invitations/accept/",
            {"token": replacement_token},
            format="json",
        )
        self.assertEqual(expired.status_code, 404)

        self.client.force_authenticate(self.owner)
        next_response, _ = self._send_invitation()
        self.assertEqual(next_response.status_code, 201)
        current.refresh_from_db()
        self.assertEqual(current.status, OrganizationInvitation.Status.REVOKED)
        self.assertNotEqual(raw_token, replacement_token)

    def test_workspace_request_is_pending_and_not_accessible_before_review(self):
        self.client.force_authenticate(self.owner)
        created = self.client.post(
            "/api/v1/organizations/",
            {"name": "Northstar", "slug": "northstar", "description": "A workspace"},
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["status"], Organization.Status.PENDING)
        self.assertIsNone(created.data["role"])
        self.assertEqual(created.data["member_count"], 0)
        self.assertFalse(Membership.objects.filter(organization__slug="northstar").exists())
        self.assertEqual(
            self.client.get("/api/v1/organizations/").data,
            [],
        )
        self.assertEqual(
            self.client.get("/api/v1/organizations/applications/").data[0]["slug"],
            "northstar",
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/polls/",
                {
                    "title": "Restricted poll",
                    "question": "Can I create this?",
                    "organization": created.data["id"],
                    "options": ["Yes", "No"],
                },
                format="json",
            ).status_code,
            403,
        )

        self.client.force_authenticate(self.other_user)
        self.assertEqual(
            self.client.get("/api/v1/organizations/northstar/").status_code, 404
        )
        self.assertEqual(
            self.client.get("/api/v1/organizations/applications/").data,
            [],
        )

    def test_only_staff_can_review_and_approval_grants_owner_access(self):
        application = Organization.objects.create(
            name="Northstar",
            slug="northstar",
            description="A workspace",
            created_by=self.owner,
        )
        self.client.force_authenticate(self.owner)
        denied = self.client.post(
            "/api/v1/organizations/northstar/review/",
            {"status": Organization.Status.APPROVED, "reason": "Looks good."},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            self.client.get("/api/v1/organizations/northstar/").status_code,
            404,
        )

        reviewer = User.objects.create_user(
            email="reviewer@example.com", password="secure-test-password", is_staff=True
        )
        self.client.force_authenticate(reviewer)
        pending = self.client.get("/api/v1/organizations/applications/")
        self.assertEqual([item["id"] for item in pending.data], [application.id])
        approved = self.client.post(
            "/api/v1/organizations/northstar/review/",
            {"status": Organization.Status.APPROVED, "reason": "Verified."},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.status, Organization.Status.APPROVED)
        self.assertEqual(application.reviewed_by, reviewer)
        self.assertTrue(
            Membership.objects.filter(
                organization=application,
                user=self.owner,
                role=Membership.Role.OWNER,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.owner,
                kind=Notification.Kind.ORGANIZATION_REVIEW,
                organization=application,
            ).exists()
        )
        self.client.force_authenticate(self.owner)
        self.assertEqual(
            self.client.get("/api/v1/organizations/northstar/").status_code,
            200,
        )

    def test_rejection_requires_a_reason_and_does_not_grant_membership(self):
        application = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        reviewer = User.objects.create_user(
            email="reviewer@example.com", password="secure-test-password", is_staff=True
        )
        self.client.force_authenticate(reviewer)
        missing_reason = self.client.post(
            "/api/v1/organizations/northstar/review/",
            {"status": Organization.Status.REJECTED, "reason": ""},
            format="json",
        )
        self.assertEqual(missing_reason.status_code, 400)
        rejected = self.client.post(
            "/api/v1/organizations/northstar/review/",
            {"status": Organization.Status.REJECTED, "reason": "Could not verify."},
            format="json",
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["review_reason"], "Could not verify.")
        self.assertFalse(Membership.objects.filter(organization=application).exists())
        second_review = self.client.post(
            "/api/v1/organizations/northstar/review/",
            {"status": Organization.Status.APPROVED, "reason": "Retry"},
            format="json",
        )
        self.assertEqual(second_review.status_code, 404)

    def test_owner_can_add_existing_member_but_member_cannot_manage_members(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner,
            status=Organization.Status.APPROVED,
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
            name="Northstar", slug="northstar", created_by=self.owner,
            status=Organization.Status.APPROVED,
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
            name="Northstar", slug="northstar", created_by=self.owner,
            status=Organization.Status.APPROVED,
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
            name="Northstar", slug="northstar", created_by=self.owner,
            status=Organization.Status.APPROVED,
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
