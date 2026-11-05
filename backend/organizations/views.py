from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from polls.models import Poll
from polls.models import PollResponse
from surveys.models import Survey
from surveys.models import SurveyResponse
from notifications.models import Notification

from .models import Membership, Organization
from .serializers import (
    AddMemberSerializer,
    MembershipSerializer,
    OrganizationSerializer,
)


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Organization.objects.filter(memberships__user=self.request.user)
            .annotate(member_count=Count("memberships"))
            .prefetch_related("memberships")
            .distinct()
        )

    @transaction.atomic
    def perform_create(self, serializer):
        organization = serializer.save()
        Membership.objects.create(
            organization=organization,
            user=self.request.user,
            role=Membership.Role.OWNER,
        )

    def _require_admin(self, organization):
        membership = Membership.objects.filter(
            organization=organization, user=self.request.user
        ).first()
        if membership is None or membership.role not in (
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only organization owners and administrators can do this."
            )

    def perform_update(self, serializer):
        self._require_admin(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin(instance)
        if (
            instance.polls.exists()
            or instance.surveys.exists()
            or instance.elections.exists()
        ):
            raise ValidationError(
                "A workspace with activities or elections cannot be deleted. Archive it instead."
            )
        instance.delete()

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, slug=None):
        organization = self.get_object()
        if request.method == "GET":
            members = organization.memberships.select_related("user")
            return Response(MembershipSerializer(members, many=True).data)

        self._require_admin(organization)
        serializer = AddMemberSerializer(
            data=request.data, context={"organization": organization}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            membership = serializer.save()
            if membership.user_id != request.user.id:
                Notification.objects.create(
                    recipient=membership.user,
                    actor=request.user,
                    kind=Notification.Kind.WORKSPACE_ADDED,
                    message=f"You were added to {organization.name}"[:240],
                    organization=organization,
                )
        return Response(
            MembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"], url_path="analytics")
    def analytics(self, request, slug=None):
        organization = self.get_object()
        self._require_admin(organization)
        polls = Poll.objects.filter(organization=organization)
        surveys = Survey.objects.filter(organization=organization)
        poll_stats = polls.aggregate(
            total=Count("id", distinct=True),
            active=Count("id", filter=Q(status=Poll.Status.ACTIVE), distinct=True),
            responses=Count("responses", distinct=True),
        )
        survey_stats = surveys.aggregate(
            total=Count("id", distinct=True),
            active=Count("id", filter=Q(status=Survey.Status.ACTIVE), distinct=True),
            responses=Count("responses", distinct=True),
        )
        today = timezone.localdate()
        start_date = today - timedelta(days=29)
        start_at = timezone.make_aware(datetime.combine(start_date, time.min))
        poll_activity = {
            entry["day"]: entry["count"]
            for entry in PollResponse.objects.filter(
                poll__organization=organization, submitted_at__gte=start_at
            )
            .annotate(day=TruncDate("submitted_at"))
            .values("day")
            .annotate(count=Count("id"))
        }
        survey_activity = {
            entry["day"]: entry["count"]
            for entry in SurveyResponse.objects.filter(
                survey__organization=organization, submitted_at__gte=start_at
            )
            .annotate(day=TruncDate("submitted_at"))
            .values("day")
            .annotate(count=Count("id"))
        }
        daily_activity = [
            {
                "date": (start_date + timedelta(days=offset)).isoformat(),
                "poll_responses": poll_activity.get(
                    start_date + timedelta(days=offset), 0
                ),
                "survey_responses": survey_activity.get(
                    start_date + timedelta(days=offset), 0
                ),
            }
            for offset in range(30)
        ]
        return Response(
            {
                "member_count": organization.memberships.count(),
                "poll_count": poll_stats["total"],
                "active_poll_count": poll_stats["active"],
                "poll_response_count": poll_stats["responses"],
                "survey_count": survey_stats["total"],
                "active_survey_count": survey_stats["active"],
                "survey_response_count": survey_stats["responses"],
                "daily_activity": daily_activity,
            }
        )
