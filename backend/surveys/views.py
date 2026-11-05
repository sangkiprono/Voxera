from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from organizations.models import Membership

from .models import Survey, SurveyQuestion, SurveyResponse as SurveyResponseRecord
from .serializers import (
    SurveyCreateSerializer,
    SurveySerializer,
    SurveySubmissionSerializer,
    SurveyUpdateSerializer,
)


class SurveyViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user = self.request.user
        queryset = (
            Survey.objects.select_related("created_by", "organization")
            .prefetch_related("questions__options")
            .annotate(response_count=Count("responses", distinct=True))
        )
        if user.is_authenticated:
            memberships = Membership.objects.filter(user=user).values(
                "organization_id"
            )
            queryset = queryset.filter(
                Q(visibility=Survey.Visibility.PUBLIC, status__in=("active", "closed"))
                | Q(created_by=user)
                | Q(
                    visibility=Survey.Visibility.PRIVATE,
                    status__in=("active", "closed"),
                    organization_id__in=memberships,
                )
            )
        else:
            queryset = queryset.filter(
                visibility=Survey.Visibility.PUBLIC,
                status__in=("active", "closed"),
            )
        return queryset.distinct()

    def get_permissions(self):
        if self.action in (
            "create",
            "update",
            "partial_update",
            "destroy",
            "respond",
            "report",
        ):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.action == "create":
            return SurveyCreateSerializer
        if self.action in ("update", "partial_update"):
            return SurveyUpdateSerializer
        if self.action == "respond":
            return SurveySubmissionSerializer
        return SurveySerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        response_data = SurveySerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        ).data
        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(response_data),
        )

    def perform_create(self, serializer):
        organization = serializer.validated_data.get("organization")
        if organization is not None:
            membership = Membership.objects.filter(
                organization=organization, user=self.request.user
            ).first()
            if membership is None or membership.role not in (
                Membership.Role.OWNER,
                Membership.Role.ADMIN,
                Membership.Role.CREATOR,
            ):
                raise PermissionDenied(
                    "You need an organization creator role to create its surveys."
                )
        serializer.save()

    def _require_manager(self, survey):
        if survey.created_by_id == self.request.user.id:
            return
        membership = Membership.objects.filter(
            organization=survey.organization, user=self.request.user
        ).first()
        if membership is None or membership.role not in (
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only the survey creator or an organization administrator can do this."
            )

    def perform_update(self, serializer):
        survey = self.get_object()
        self._require_manager(survey)
        if survey.responses.exists():
            raise serializers.ValidationError(
                "Surveys cannot be edited after a response has been submitted."
            )
        serializer.save()

    def perform_destroy(self, instance):
        self._require_manager(instance)
        if instance.responses.exists():
            raise serializers.ValidationError(
                "A survey with submitted responses cannot be deleted."
            )
        instance.delete()

    @action(detail=True, methods=["post"], url_path="responses")
    def respond(self, request, pk=None):
        survey = self.get_object()
        if survey.status != Survey.Status.ACTIVE or (
            survey.ends_at is not None and survey.ends_at <= timezone.now()
        ):
            return Response(
                {"detail": "This survey is closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if SurveyResponseRecord.objects.filter(
            survey=survey, user=request.user
        ).exists():
            return Response(
                {"detail": "You have already responded to this survey."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = self.get_serializer(
            data=request.data, context={"survey": survey, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            response, created = SurveyResponseRecord.objects.get_or_create(
                survey=survey, user=request.user
            )
            if not created:
                return Response(
                    {"detail": "You have already responded to this survey."},
                    status=status.HTTP_409_CONFLICT,
                )
            serializer.save(response=response)
        return Response(
            {"detail": "Your response has been recorded."},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="report")
    def report(self, request, pk=None):
        survey = self.get_object()
        self._require_manager(survey)
        questions = survey.questions.prefetch_related(
            "options__answers", "answers__response__user"
        )
        question_reports = []
        for question in questions:
            answers = question.answers.all()
            report = {
                "id": question.id,
                "text": question.text,
                "question_type": question.question_type,
                "response_count": answers.count(),
            }
            if question.question_type in (
                SurveyQuestion.QuestionType.SINGLE_CHOICE,
                SurveyQuestion.QuestionType.MULTIPLE_CHOICE,
            ):
                report["options"] = [
                    {
                        "id": option.id,
                        "text": option.text,
                        "responses": option.answers.count(),
                    }
                    for option in question.options.all()
                ]
            elif question.question_type == SurveyQuestion.QuestionType.RATING:
                report["average_rating"] = self._average_rating(answers)
                report["ratings"] = [
                    {
                        "rating": rating,
                        "responses": answers.filter(rating=rating).count(),
                    }
                    for rating in range(1, 6)
                ]
            else:
                report["answers"] = [
                    {"text": answer.text, "submitted_at": answer.response.submitted_at}
                    for answer in answers.exclude(text="")
                ]
            question_reports.append(report)
        return Response(
            {
                "survey_id": survey.id,
                "title": survey.title,
                "total_responses": survey.responses.count(),
                "questions": question_reports,
            }
        )

    @staticmethod
    def _average_rating(answers):
        ratings = [answer.rating for answer in answers if answer.rating is not None]
        return round(sum(ratings) / len(ratings), 2) if ratings else None
