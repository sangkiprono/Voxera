from django.db import transaction
from django.db.models import Count
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

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
        if instance.polls.exists() or instance.surveys.exists():
            raise ValidationError(
                "A workspace with polls or surveys cannot be deleted. Archive it instead."
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
        membership = serializer.save()
        return Response(
            MembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )
