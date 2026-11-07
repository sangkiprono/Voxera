import hashlib
import secrets
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from polls.models import Poll
from polls.models import PollResponse
from surveys.models import Survey
from surveys.models import SurveyResponse
from notifications.models import Notification
from subscriptions.serializers import OrganizationSubscriptionStatusSerializer

from .models import Membership, Organization, OrganizationInvitation
from .serializers import (
    AcceptOrganizationInvitationSerializer,
    AddMemberSerializer,
    CreateOrganizationInvitationSerializer,
    MembershipSerializer,
    OrganizationInvitationSerializer,
    OrganizationReviewSerializer,
    OrganizationSerializer,
)
from subscriptions.limits import enforce_member_limit


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Organization.objects.filter(
                memberships__user=self.request.user,
                status=Organization.Status.APPROVED,
            )
            .annotate(member_count=Count("memberships"))
            .prefetch_related("memberships")
            .distinct()
        )

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()

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

    @action(detail=False, methods=["get"], url_path="applications")
    def applications(self, request):
        applications = Organization.objects.all()
        if request.user.is_staff:
            applications = applications.filter(status=Organization.Status.PENDING)
        else:
            applications = applications.filter(created_by=request.user)
        applications = applications.order_by("-created_at")
        return Response(
            OrganizationSerializer(
                applications,
                many=True,
                context=self.get_serializer_context(),
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="review",
        permission_classes=[permissions.IsAdminUser],
    )
    def review(self, request, slug=None):
        serializer = OrganizationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            organization = (
                Organization.objects.select_for_update()
                .filter(slug=slug, status=Organization.Status.PENDING)
                .first()
            )
            if organization is None:
                raise NotFound("This organization request is no longer pending.")

            approved = serializer.validated_data["status"] == Organization.Status.APPROVED
            organization.status = serializer.validated_data["status"]
            organization.review_reason = serializer.validated_data["reason"]
            organization.reviewed_by = request.user
            organization.reviewed_at = timezone.now()
            organization.save(
                update_fields=[
                    "status",
                    "review_reason",
                    "reviewed_by",
                    "reviewed_at",
                ]
            )
            if approved:
                Membership.objects.get_or_create(
                    organization=organization,
                    user=organization.created_by,
                    defaults={"role": Membership.Role.OWNER},
                )
            Notification.objects.create(
                recipient=organization.created_by,
                actor=request.user,
                kind=Notification.Kind.ORGANIZATION_REVIEW,
                message=(
                    f"Your organization request for {organization.name} was "
                    f"{'approved' if approved else 'not approved'}."
                )[:240],
                organization=organization,
            )
        return Response(
            OrganizationSerializer(
                organization, context=self.get_serializer_context()
            ).data
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
        with transaction.atomic():
            organization = Organization.objects.select_for_update().get(
                pk=organization.pk
            )
            serializer = AddMemberSerializer(
                data=request.data, context={"organization": organization}
            )
            serializer.is_valid(raise_exception=True)
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
            MembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get", "post"], url_path="invitations")
    def invitations(self, request, slug=None):
        organization = self.get_object()
        self._require_admin(organization)
        if request.method == "GET":
            invitations = organization.invitations.select_related("invited_by")
            return Response(
                OrganizationInvitationSerializer(invitations, many=True).data
            )

        with transaction.atomic():
            organization = Organization.objects.select_for_update().get(
                pk=organization.pk, status=Organization.Status.APPROVED
            )
            serializer = CreateOrganizationInvitationSerializer(
                data=request.data, context={"organization": organization}
            )
            serializer.is_valid(raise_exception=True)
            email = serializer.validated_data["email"]
            OrganizationInvitation.objects.filter(
                organization=organization,
                email=email,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__lte=timezone.now(),
            ).update(revoked_at=timezone.now())

            if OrganizationInvitation.objects.filter(
                organization=organization,
                email=email,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).exists():
                raise ValidationError(
                    {"email": "A valid invitation has already been sent to this address."}
                )

            raw_token = secrets.token_urlsafe(32)
            invitation = OrganizationInvitation.objects.create(
                organization=organization,
                email=email,
                role=serializer.validated_data["role"],
                token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
                invited_by=request.user,
                expires_at=timezone.now() + timedelta(days=7),
            )
            link = (
                f"{settings.FRONTEND_BASE_URL}/"
                f"?accept_invite={raw_token}"
            )
            sent = send_mail(
                f"Invitation to join {organization.name} on Voxera",
                (
                    f"{request.user.get_full_name() or request.user.email} invited "
                    f"you to join {organization.name} as {invitation.get_role_display()}.\n\n"
                    f"Sign in to the Voxera account for {email} and accept this "
                    f"invitation within 7 days:\n\n{link}\n"
                ),
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            if sent != 1:
                raise RuntimeError("The organization invitation email was not sent.")

        return Response(
            OrganizationInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path=r"invitations/(?P<invitation_id>[^/.]+)/revoke",
    )
    def revoke_invitation(self, request, slug=None, invitation_id=None):
        organization = self.get_object()
        self._require_admin(organization)
        with transaction.atomic():
            invitation = (
                OrganizationInvitation.objects.select_for_update()
                .filter(
                    pk=invitation_id,
                    organization=organization,
                    accepted_at__isnull=True,
                    revoked_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if invitation is None:
                raise NotFound("This pending invitation could not be found.")
            invitation.revoked_at = timezone.now()
            invitation.save(update_fields=["revoked_at"])
        return Response(OrganizationInvitationSerializer(invitation).data)

    @action(
        detail=False,
        methods=["post"],
        url_path="invitations/accept",
        permission_classes=[permissions.IsAuthenticated],
    )
    def accept_invitation(self, request):
        serializer = AcceptOrganizationInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        digest = hashlib.sha256(
            serializer.validated_data["token"].encode()
        ).hexdigest()
        with transaction.atomic():
            invitation = (
                OrganizationInvitation.objects.select_for_update()
                .select_related("organization")
                .filter(
                    token_digest=digest,
                    accepted_at__isnull=True,
                    revoked_at__isnull=True,
                    expires_at__gt=timezone.now(),
                    organization__status=Organization.Status.APPROVED,
                )
                .first()
            )
            if invitation is None:
                raise NotFound("This invitation is invalid, expired, or revoked.")
            if not request.user.email_verified:
                raise PermissionDenied(
                    "Verify your email address before accepting invitations."
                )
            if invitation.email.casefold() != request.user.email.casefold():
                raise PermissionDenied(
                    "Sign in with the verified email address this invitation was sent to."
                )
            if Membership.objects.filter(
                organization=invitation.organization, user=request.user
            ).exists():
                raise ValidationError(
                    {"detail": "You are already a member of this workspace."}
                )

            locked_organization = Organization.objects.select_for_update().get(
                pk=invitation.organization_id
            )
            enforce_member_limit(locked_organization)
            membership = Membership.objects.create(
                organization=locked_organization,
                user=request.user,
                role=invitation.role,
            )
            invitation.accepted_by = request.user
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["accepted_by", "accepted_at"])
        return Response(
            {
                "membership": MembershipSerializer(membership).data,
                "organization_name": locked_organization.name,
                "organization_slug": locked_organization.slug,
            }
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
        top_polls = list(
            polls.order_by()
            .annotate(response_count=Count("responses", distinct=True))
            .order_by("-response_count", "-created_at", "id")
            .values("id", "title", "status", "response_count")[:5]
        )
        top_surveys = list(
            surveys.order_by()
            .annotate(response_count=Count("responses", distinct=True))
            .order_by("-response_count", "-created_at", "id")
            .values("id", "title", "status", "response_count")[:5]
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
                "top_polls": top_polls,
                "top_surveys": top_surveys,
            }
        )

    @action(detail=True, methods=["get"], url_path="subscription")
    def subscription(self, request, slug=None):
        organization = self.get_object()
        self._require_admin(organization)
        serializer = OrganizationSubscriptionStatusSerializer(
            organization, context=self.get_serializer_context()
        )
        return Response(serializer.data)
