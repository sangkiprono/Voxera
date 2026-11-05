from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from organizations.models import Membership, Organization

from .models import Poll, PollOption

User = get_user_model()


class PollApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", password="secure-test-password"
        )
        self.voter = User.objects.create_user(
            email="voter@example.com", password="secure-test-password"
        )
        self.poll = Poll.objects.create(
            title="Weekend plans",
            question="What should we do this weekend?",
            created_by=self.owner,
        )
        self.first_option = PollOption.objects.create(
            poll=self.poll, text="Hiking", position=0
        )
        self.second_option = PollOption.objects.create(
            poll=self.poll, text="Picnic", position=1
        )

    def test_public_poll_can_be_read_without_authentication(self):
        response = self.client.get("/api/v1/polls/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["question"], self.poll.question)
        self.assertEqual(response.data[0]["created_by_name"], "Voxera member")
        self.assertEqual(len(response.data[0]["options"]), 2)

    def test_authenticated_user_can_vote_once_and_see_accurate_results(self):
        self.client.force_authenticate(self.voter)
        url = f"/api/v1/polls/{self.poll.id}/responses/"
        first = self.client.post(
            url, {"option_id": self.first_option.id}, format="json"
        )
        duplicate = self.client.post(
            url, {"option_id": self.second_option.id}, format="json"
        )
        results = self.client.get(f"/api/v1/polls/{self.poll.id}/results/")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(results.data["total_responses"], 1)
        self.assertEqual(results.data["options"][0]["percentage"], 100)

    def test_results_export_is_csv_and_escapes_spreadsheet_formulas(self):
        self.poll.title = "=1+1"
        self.poll.save(update_fields=["title"])

        response = self.client.get(
            f"/api/v1/polls/{self.poll.id}/export-results/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn(b"'=1+1", response.content)

    def test_private_results_export_requires_workspace_access(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        Membership.objects.create(
            organization=organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        self.poll.organization = organization
        self.poll.visibility = Poll.Visibility.PRIVATE
        self.poll.save(update_fields=["organization", "visibility"])
        self.client.force_authenticate(self.voter)

        response = self.client.get(
            f"/api/v1/polls/{self.poll.id}/export-results/"
        )

        self.assertEqual(response.status_code, 404)

    def test_response_rejects_an_option_from_a_different_poll(self):
        another_poll = Poll.objects.create(
            title="Another poll", question="Choose one", created_by=self.owner
        )
        other_option = PollOption.objects.create(
            poll=another_poll, text="Other", position=0
        )
        self.client.force_authenticate(self.voter)

        response = self.client.post(
            f"/api/v1/polls/{self.poll.id}/responses/",
            {"option_id": other_option.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_only_workspace_creators_can_create_organization_polls(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        Membership.objects.create(
            organization=organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        payload = {
            "title": "Team lunch",
            "question": "Where should we go?",
            "organization": organization.id,
            "options": ["Cafe", "Market"],
        }

        self.client.force_authenticate(self.voter)
        denied = self.client.post("/api/v1/polls/", payload, format="json")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.owner)
        created = self.client.post("/api/v1/polls/", payload, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["organization"], organization.id)
        self.assertEqual(len(created.data["options"]), 2)

    def test_private_workspace_poll_is_only_visible_to_workspace_members(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner
        )
        Membership.objects.create(
            organization=organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        private_poll = Poll.objects.create(
            title="Private plans",
            question="Where should we meet?",
            visibility=Poll.Visibility.PRIVATE,
            created_by=self.owner,
            organization=organization,
        )
        self.client.force_authenticate(self.voter)
        hidden = self.client.get(f"/api/v1/polls/{private_poll.id}/")
        self.assertEqual(hidden.status_code, 404)

        Membership.objects.create(
            organization=organization,
            user=self.voter,
            role=Membership.Role.MEMBER,
        )
        visible = self.client.get(f"/api/v1/polls/{private_poll.id}/")
        self.assertEqual(visible.status_code, 200)
