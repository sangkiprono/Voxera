from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Membership, Organization, OrganizationInvitation
from subscriptions.limits import enforce_member_limit

User = get_user_model()


class MembershipSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    name = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ("id", "email", "name", "role", "joined_at")
        read_only_fields = fields

    def get_name(self, membership):
        return membership.user.get_full_name() or membership.user.email


class OrganizationSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "status",
            "review_reason",
            "reviewed_at",
            "role",
            "member_count",
            "created_at",
        )
        read_only_fields = (
            "id",
            "status",
            "review_reason",
            "reviewed_at",
            "role",
            "member_count",
            "created_at",
        )

    def get_role(self, organization):
        membership = next(
            (
                member
                for member in organization.memberships.all()
                if member.user_id == self.context["request"].user.id
            ),
            None,
        )
        return membership.role if membership else None

    def get_member_count(self, organization):
        return organization.memberships.count()

    def create(self, validated_data):
        return Organization.objects.create(
            created_by=self.context["request"].user,
            status=Organization.Status.PENDING,
            **validated_data,
        )


class OrganizationReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(Organization.Status.APPROVED, Organization.Status.REJECTED)
    )
    reason = serializers.CharField(max_length=2000, allow_blank=False)


class AddMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=(
            Membership.Role.ADMIN,
            Membership.Role.CREATOR,
            Membership.Role.MEMBER,
        ),
        default=Membership.Role.MEMBER,
    )

    def validate_email(self, value):
        try:
            return User.objects.get(email__iexact=value)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError(
                "This person needs a Voxera account before they can be added."
            ) from exc

    def validate(self, attrs):
        if Membership.objects.filter(
            organization=self.context["organization"], user=attrs["email"]
        ).exists():
            raise serializers.ValidationError(
                {"email": "This person is already a member."}
            )
        enforce_member_limit(self.context["organization"])
        return attrs

    def create(self, validated_data):
        return Membership.objects.create(
            organization=self.context["organization"],
            user=validated_data["email"],
            role=validated_data["role"],
        )


class OrganizationInvitationSerializer(serializers.ModelSerializer):
    invited_by_name = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)

    class Meta:
        model = OrganizationInvitation
        fields = (
            "id",
            "email",
            "role",
            "status",
            "invited_by_name",
            "expires_at",
            "created_at",
        )
        read_only_fields = fields

    def get_invited_by_name(self, invitation):
        return invitation.invited_by.get_full_name() or invitation.invited_by.email


class CreateOrganizationInvitationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=(
            Membership.Role.ADMIN,
            Membership.Role.CREATOR,
            Membership.Role.MEMBER,
        ),
        default=Membership.Role.MEMBER,
    )

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        organization = self.context["organization"]
        email = attrs["email"]
        if Membership.objects.filter(
            organization=organization, user__email__iexact=email
        ).exists():
            raise serializers.ValidationError(
                {"email": "This person is already a member."}
            )
        return attrs


class AcceptOrganizationInvitationSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)


class RevokeOrganizationInvitationSerializer(serializers.Serializer):
    invitation_id = serializers.IntegerField(min_value=1)
