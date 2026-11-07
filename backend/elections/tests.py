from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from organizations.models import Membership, Organization

from .models import Election, ElectionCandidate, ElectionEligibleVoter

User = get_user_model()


class ElectionApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", password="Test-password-42!"
        )
        self.member = User.objects.create_user(
            email="member@example.com", password="Test-password-42!"
        )
        self.late_member = User.objects.create_user(
            email="late@example.com", password="Test-password-42!"
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com", password="Test-password-42!"
        )
        self.organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner,
            status=Organization.Status.APPROVED,
        )
        Membership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        Membership.objects.create(
            organization=self.organization,
            user=self.member,
            role=Membership.Role.MEMBER,
        )
        self.url = "/api/v1/elections/"

    def create_election(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            self.url,
            {
                "organization": self.organization.id,
                "title": "Community board",
                "description": "Choose the next board representatives.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return response.data["id"]

    def test_only_workspace_admins_can_create_and_elections_are_tenant_scoped(self):
        self.client.force_authenticate(self.member)
        denied = self.client.post(
            self.url,
            {"organization": self.organization.id, "title": "Not allowed"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        election_id = self.create_election()
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.url).data, [])
        self.assertEqual(self.client.get(f"{self.url}{election_id}/").status_code, 404)

    def test_opening_nominations_snapshots_members_and_member_can_self_nominate(self):
        election_id = self.create_election()
        self.client.force_authenticate(self.owner)
        opened = self.client.post(
            f"{self.url}{election_id}/open-nominations/"
        )

        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.data["status"], Election.Status.NOMINATIONS)
        self.assertEqual(opened.data["eligible_voter_count"], 2)
        self.assertEqual(
            ElectionEligibleVoter.objects.filter(election_id=election_id).count(), 2
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.late_member,
            role=Membership.Role.MEMBER,
        )
        self.client.force_authenticate(self.late_member)
        denied = self.client.post(
            f"{self.url}{election_id}/nominate/",
            {"statement": "I joined later."},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.member)
        nominated = self.client.post(
            f"{self.url}{election_id}/nominate/",
            {"statement": "I will listen and represent the team."},
            format="json",
        )
        duplicate = self.client.post(
            f"{self.url}{election_id}/nominate/",
            {"statement": "Updated statement."},
            format="json",
        )
        self.assertEqual(nominated.status_code, 201)
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(
            ElectionCandidate.objects.filter(election_id=election_id).count(), 1
        )

    def test_only_admins_can_open_or_close_nominations_and_no_ballot_route_exists(self):
        election_id = self.create_election()
        self.client.force_authenticate(self.member)
        denied = self.client.post(
            f"{self.url}{election_id}/open-nominations/"
        )
        self.assertEqual(denied.status_code, 404)

        self.client.force_authenticate(self.owner)
        self.client.post(f"{self.url}{election_id}/open-nominations/")
        self.client.force_authenticate(self.member)
        no_ballot = self.client.post(
            f"{self.url}{election_id}/ballots/",
            {"candidate_id": 1},
            format="json",
        )
        self.assertEqual(no_ballot.status_code, 404)
        self.client.force_authenticate(self.owner)
        closed = self.client.post(
            f"{self.url}{election_id}/close-nominations/"
        )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.data["status"], Election.Status.READY)
        self.assertEqual(
            self.client.post(f"{self.url}{election_id}/open-nominations/").status_code,
            400,
        )

    def test_members_cannot_read_draft_elections(self):
        election_id = self.create_election()
        self.client.force_authenticate(self.member)

        response = self.client.get(f"{self.url}{election_id}/")

        self.assertEqual(response.status_code, 404)
