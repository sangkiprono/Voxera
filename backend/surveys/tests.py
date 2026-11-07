from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from organizations.models import Membership, Organization

from .models import (
    Survey,
    SurveyAnswer,
    SurveyOption,
    SurveyQuestion,
    SurveyResponse,
)

User = get_user_model()


class SurveyApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", password="secure-test-password"
        )
        self.respondent = User.objects.create_user(
            email="respondent@example.com", password="secure-test-password"
        )
        self.survey = Survey.objects.create(
            title="Community check-in",
            description="Help us plan the next meetup.",
            created_by=self.owner,
        )
        self.choice_question = SurveyQuestion.objects.create(
            survey=self.survey,
            text="Where should we meet?",
            question_type=SurveyQuestion.QuestionType.SINGLE_CHOICE,
            position=0,
        )
        self.cafe = SurveyOption.objects.create(
            question=self.choice_question, text="Cafe", position=0
        )
        self.park = SurveyOption.objects.create(
            question=self.choice_question, text="Park", position=1
        )
        self.rating_question = SurveyQuestion.objects.create(
            survey=self.survey,
            text="How excited are you?",
            question_type=SurveyQuestion.QuestionType.RATING,
            position=1,
        )
        self.feedback_question = SurveyQuestion.objects.create(
            survey=self.survey,
            text="Anything else?",
            question_type=SurveyQuestion.QuestionType.LONG_TEXT,
            is_required=False,
            position=2,
        )

    def test_public_survey_is_discoverable_and_question_details_are_read_only(self):
        response = self.client.get("/api/v1/surveys/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["title"], self.survey.title)
        self.assertEqual(len(response.data[0]["questions"]), 3)
        self.assertEqual(len(response.data[0]["questions"][0]["options"]), 2)
        self.assertFalse(response.data[0]["has_responded"])

    def test_owner_can_create_survey_with_multiple_question_types(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/v1/surveys/",
            {
                "title": "Product feedback",
                "description": "Help us improve.",
                "visibility": "public",
                "questions": [
                    {
                        "text": "Which feature matters most?",
                        "question_type": "single_choice",
                        "is_required": True,
                        "options": ["Speed", "Accessibility"],
                    },
                    {
                        "text": "How useful is the app?",
                        "question_type": "rating",
                        "is_required": True,
                    },
                    {
                        "text": "What could be better?",
                        "question_type": "long_text",
                        "is_required": False,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["questions"]), 3)
        self.assertEqual(response.data["questions"][1]["question_type"], "rating")

    def test_choice_questions_require_two_distinct_options(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/v1/surveys/",
            {
                "title": "Broken survey",
                "questions": [
                    {
                        "text": "Pick one",
                        "question_type": "single_choice",
                        "options": ["Yes", " yes "],
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Survey.objects.filter(title="Broken survey").exists())

    def test_response_is_saved_once_and_report_summarizes_each_answer_type(self):
        self.client.force_authenticate(self.respondent)
        response = self.client.post(
            f"/api/v1/surveys/{self.survey.id}/responses/",
            {
                "answers": [
                    {"question_id": self.choice_question.id, "option_id": self.cafe.id},
                    {"question_id": self.rating_question.id, "rating": 4},
                    {
                        "question_id": self.feedback_question.id,
                        "text": "A later afternoon would be great.",
                    },
                ]
            },
            format="json",
        )
        duplicate = self.client.post(
            f"/api/v1/surveys/{self.survey.id}/responses/",
            {"answers": [{"invalid": "repeat"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(SurveyResponse.objects.filter(survey=self.survey).count(), 1)
        self.assertEqual(SurveyAnswer.objects.filter(response__survey=self.survey).count(), 3)

        self.client.force_authenticate(self.owner)
        report = self.client.get(f"/api/v1/surveys/{self.survey.id}/report/")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data["total_responses"], 1)
        self.assertEqual(report.data["questions"][0]["options"][0]["responses"], 1)
        self.assertEqual(report.data["questions"][1]["average_rating"], 4)
        self.assertEqual(
            report.data["questions"][2]["answers"][0]["text"],
            "A later afternoon would be great.",
        )

    def test_manager_can_export_csv_without_respondent_identity(self):
        response_record = SurveyResponse.objects.create(
            survey=self.survey, user=self.respondent
        )
        SurveyAnswer.objects.create(
            response=response_record,
            question=self.feedback_question,
            text="=1+1",
        )
        self.client.force_authenticate(self.owner)

        export = self.client.get(
            f"/api/v1/surveys/{self.survey.id}/export-report/"
        )

        self.assertEqual(export.status_code, 200)
        self.assertTrue(export["Content-Type"].startswith("text/csv"))
        self.assertIn(b"'=1+1", export.content)
        self.assertNotIn(self.respondent.email.encode(), export.content)

        self.client.force_authenticate(self.respondent)
        denied = self.client.get(
            f"/api/v1/surveys/{self.survey.id}/export-report/"
        )
        self.assertEqual(denied.status_code, 403)

    def test_survey_comments_are_moderated_and_hidden_from_the_public(self):
        comment_url = f"/api/v1/surveys/{self.survey.id}/comments/"
        self.client.force_authenticate(self.respondent)
        created = self.client.post(
            comment_url, {"body": "Please add evening sessions."}, format="json"
        )
        self.assertEqual(created.status_code, 201)

        self.client.force_authenticate(self.owner)
        hidden = self.client.patch(
            f"{comment_url}{created.data['id']}/moderate/",
            {"is_hidden": True},
            format="json",
        )
        self.assertEqual(hidden.status_code, 200)
        self.assertEqual(hidden.data["is_hidden"], True)

        self.client.force_authenticate(self.respondent)
        self.assertEqual(self.client.get(comment_url).data, [])

    def test_required_answers_and_answers_from_another_survey_are_rejected(self):
        other_survey = Survey.objects.create(
            title="Other survey", created_by=self.owner
        )
        other_question = SurveyQuestion.objects.create(
            survey=other_survey,
            text="An unrelated question",
            question_type=SurveyQuestion.QuestionType.SHORT_TEXT,
            position=0,
        )
        self.client.force_authenticate(self.respondent)
        missing_required = self.client.post(
            f"/api/v1/surveys/{self.survey.id}/responses/",
            {
                "answers": [
                    {"question_id": self.rating_question.id, "rating": 3},
                    {"question_id": other_question.id, "text": "No"},
                ]
            },
            format="json",
        )
        cross_survey = self.client.post(
            f"/api/v1/surveys/{self.survey.id}/responses/",
            {
                "answers": [
                    {"question_id": self.choice_question.id, "option_id": self.park.id},
                    {"question_id": self.rating_question.id, "rating": 3},
                    {"question_id": other_question.id, "text": "No"},
                ]
            },
            format="json",
        )

        self.assertEqual(missing_required.status_code, 400)
        self.assertEqual(cross_survey.status_code, 400)
        self.assertEqual(SurveyResponse.objects.filter(survey=self.survey).count(), 0)

    def test_ratings_outside_range_and_closed_surveys_are_rejected(self):
        self.client.force_authenticate(self.respondent)
        invalid_rating = self.client.post(
            f"/api/v1/surveys/{self.survey.id}/responses/",
            {
                "answers": [
                    {"question_id": self.choice_question.id, "option_id": self.cafe.id},
                    {"question_id": self.rating_question.id, "rating": 6},
                ]
            },
            format="json",
        )
        self.assertEqual(invalid_rating.status_code, 400)

        self.survey.ends_at = timezone.now() - timedelta(minutes=1)
        self.survey.save(update_fields=("ends_at",))
        closed = self.client.post(
            f"/api/v1/surveys/{self.survey.id}/responses/",
            {
                "answers": [
                    {"question_id": self.choice_question.id, "option_id": self.cafe.id},
                    {"question_id": self.rating_question.id, "rating": 4},
                ]
            },
            format="json",
        )
        self.assertEqual(closed.status_code, 400)
        self.assertEqual(SurveyResponse.objects.filter(survey=self.survey).count(), 0)

    def test_private_surveys_and_reports_are_limited_to_workspace_managers(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner,
            status=Organization.Status.APPROVED,
        )
        Membership.objects.create(
            organization=organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        private_survey = Survey.objects.create(
            title="Private feedback",
            visibility=Survey.Visibility.PRIVATE,
            created_by=self.owner,
            organization=organization,
        )
        self.client.force_authenticate(self.respondent)
        hidden = self.client.get(f"/api/v1/surveys/{private_survey.id}/")
        denied_report = self.client.get(
            f"/api/v1/surveys/{private_survey.id}/report/"
        )
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(denied_report.status_code, 404)

        Membership.objects.create(
            organization=organization,
            user=self.respondent,
            role=Membership.Role.MEMBER,
        )
        visible = self.client.get(f"/api/v1/surveys/{private_survey.id}/")
        denied_report = self.client.get(
            f"/api/v1/surveys/{private_survey.id}/report/"
        )
        self.assertEqual(visible.status_code, 200)
        self.assertEqual(denied_report.status_code, 403)

    def test_workspace_members_only_see_published_private_surveys(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner,
            status=Organization.Status.APPROVED,
        )
        Membership.objects.create(
            organization=organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        draft = Survey.objects.create(
            title="Unpublished feedback",
            visibility=Survey.Visibility.PRIVATE,
            status=Survey.Status.DRAFT,
            created_by=self.owner,
            organization=organization,
        )
        active = Survey.objects.create(
            title="Published feedback",
            visibility=Survey.Visibility.PRIVATE,
            created_by=self.owner,
            organization=organization,
        )
        Membership.objects.create(
            organization=organization,
            user=self.respondent,
            role=Membership.Role.MEMBER,
        )
        self.client.force_authenticate(self.respondent)

        draft_result = self.client.get(f"/api/v1/surveys/{draft.id}/")
        active_result = self.client.get(f"/api/v1/surveys/{active.id}/")
        draft_comments = self.client.get(
            f"/api/v1/surveys/{draft.id}/comments/"
        )
        active_comments = self.client.get(
            f"/api/v1/surveys/{active.id}/comments/"
        )

        self.assertEqual(draft_result.status_code, 404)
        self.assertEqual(active_result.status_code, 200)
        self.assertEqual(draft_comments.status_code, 404)
        self.assertEqual(active_comments.status_code, 200)

    def test_organization_survey_creation_requires_a_creator_role(self):
        organization = Organization.objects.create(
            name="Northstar", slug="northstar", created_by=self.owner,
            status=Organization.Status.APPROVED,
        )
        Membership.objects.create(
            organization=organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        payload = {
            "title": "Workspace survey",
            "organization": organization.id,
            "questions": [
                {
                    "text": "How is the team?",
                    "question_type": "short_text",
                    "is_required": True,
                }
            ],
        }
        self.client.force_authenticate(self.respondent)
        denied = self.client.post("/api/v1/surveys/", payload, format="json")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.owner)
        created = self.client.post("/api/v1/surveys/", payload, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["organization"], organization.id)
