from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from organizations.models import Membership

from .models import Election, ElectionCandidate, ElectionEligibleVoter
from .serializers import (
    CandidateNominationSerializer,
    ElectionCreateSerializer,
    ElectionSerializer,
)


class ElectionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        memberships = Membership.objects.filter(user=self.request.user).values(
            "organization_id"
        )
        admin_organizations = Membership.objects.filter(
            user=self.request.user,
            role__in=(Membership.Role.OWNER, Membership.Role.ADMIN),
        ).values("organization_id")
        return (
            Election.objects.filter(organization_id__in=memberships)
            .filter(
                Q(status__in=(Election.Status.NOMINATIONS, Election.Status.READY, Election.Status.CANCELLED))
                | Q(organization_id__in=admin_organizations)
            )
            .select_related("organization", "created_by")
            .prefetch_related("candidates__user")
            .annotate(eligible_voter_count=Count("eligible_voters", distinct=True))
        )

    def get_serializer_class(self):
        if self.action == "create":
            return ElectionCreateSerializer
        if self.action in ("update", "partial_update"):
            return ElectionUpdateSerializer
        if self.action == "nominate":
            return CandidateNominationSerializer
        return ElectionSerializer

    def _require_admin(self, election):
        if not Membership.objects.filter(
            organization=election.organization,
            user=self.request.user,
            role__in=(Membership.Role.OWNER, Membership.Role.ADMIN),
        ).exists():
            raise PermissionDenied(
                "Only organization owners and administrators can manage elections."
            )

    def perform_create(self, serializer):
        organization = serializer.validated_data["organization"]
        if not Membership.objects.filter(
            organization=organization,
            user=self.request.user,
            role__in=(Membership.Role.OWNER, Membership.Role.ADMIN),
        ).exists():
            raise PermissionDenied(
                "Only organization owners and administrators can create elections."
            )
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        election = self.get_queryset().get(pk=serializer.instance.pk)
        return Response(
            ElectionSerializer(election, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        election = self.get_object()
        self._require_admin(election)
        if election.status != Election.Status.DRAFT:
            raise serializers.ValidationError(
                "Only draft elections can be edited."
            )
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin(instance)
        if instance.status != Election.Status.DRAFT:
            raise serializers.ValidationError(
                "Only draft elections can be deleted. Cancel an opened election instead."
            )
        instance.delete()

    @action(detail=True, methods=["post"], url_path="open-nominations")
    def open_nominations(self, request, pk=None):
        election = self.get_object()
        self._require_admin(election)
        with transaction.atomic():
            election = Election.objects.select_for_update().get(pk=election.pk)
            if election.status != Election.Status.DRAFT:
                raise serializers.ValidationError(
                    "Only draft elections can open nominations."
                )
            member_ids = Membership.objects.filter(
                organization=election.organization
            ).values_list("user_id", flat=True)
            ElectionEligibleVoter.objects.bulk_create(
                [
                    ElectionEligibleVoter(election=election, user_id=user_id)
                    for user_id in member_ids
                ],
                ignore_conflicts=True,
            )
            election.status = Election.Status.NOMINATIONS
            election.nominations_opened_at = timezone.now()
            election.save(
                update_fields=("status", "nominations_opened_at", "updated_at")
            )
        return Response(
            self.get_serializer(self.get_queryset().get(pk=election.pk)).data
        )

    @action(detail=True, methods=["post"], url_path="close-nominations")
    def close_nominations(self, request, pk=None):
        election = self.get_object()
        self._require_admin(election)
        with transaction.atomic():
            election = Election.objects.select_for_update().get(pk=election.pk)
            if election.status != Election.Status.NOMINATIONS:
                raise serializers.ValidationError(
                    "Only elections with open nominations can close nominations."
                )
            election.status = Election.Status.READY
            election.nominations_closed_at = timezone.now()
            election.save(
                update_fields=("status", "nominations_closed_at", "updated_at")
            )
        return Response(
            self.get_serializer(self.get_queryset().get(pk=election.pk)).data
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        election = self.get_object()
        self._require_admin(election)
        if election.status == Election.Status.CANCELLED:
            raise serializers.ValidationError(
                "This election is already cancelled."
            )
        election.status = Election.Status.CANCELLED
        election.save(update_fields=("status", "updated_at"))
        return Response(self.get_serializer(election).data)

    @action(detail=True, methods=["post"], url_path="nominate")
    def nominate(self, request, pk=None):
        election = self.get_object()
        if election.status != Election.Status.NOMINATIONS:
            raise serializers.ValidationError(
                "Nominations are not open for this election."
            )
        if not ElectionEligibleVoter.objects.filter(
            election=election, user=request.user
        ).exists():
            raise PermissionDenied(
                "Only members eligible when nominations opened can nominate."
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _, created = ElectionCandidate.objects.get_or_create(
            election=election,
            user=request.user,
            defaults={"statement": serializer.validated_data["statement"].strip()},
        )
        if not created:
            raise serializers.ValidationError(
                "You are already nominated for this election."
            )
        candidate = election.candidates.select_related("user").get(user=request.user)
        return Response(
            {
                "id": candidate.id,
                "user": candidate.user_id,
                "name": candidate.user.get_full_name() or "Voxera member",
                "statement": candidate.statement,
                "nominated_at": candidate.nominated_at,
            },
            status=status.HTTP_201_CREATED,
        )
