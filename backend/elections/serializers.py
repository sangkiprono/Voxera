from rest_framework import serializers

from .models import Election, ElectionCandidate


class ElectionCandidateSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = ElectionCandidate
        fields = ("id", "user", "name", "statement", "nominated_at")
        read_only_fields = fields

    def get_name(self, candidate):
        return candidate.user.get_full_name() or "Voxera member"


class ElectionSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    candidates = ElectionCandidateSerializer(many=True, read_only=True)
    eligible_voter_count = serializers.IntegerField(read_only=True)
    is_eligible = serializers.SerializerMethodField()

    class Meta:
        model = Election
        fields = (
            "id",
            "organization",
            "organization_name",
            "title",
            "description",
            "status",
            "created_by",
            "created_at",
            "nominations_opened_at",
            "nominations_closed_at",
            "eligible_voter_count",
            "is_eligible",
            "candidates",
        )
        read_only_fields = fields

    def get_is_eligible(self, election):
        user = self.context["request"].user
        if not user.is_authenticated or election.status == Election.Status.DRAFT:
            return False
        return election.eligible_voters.filter(user=user).exists()


class ElectionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Election
        fields = ("organization", "title", "description")


class ElectionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Election
        fields = ("title", "description")


class CandidateNominationSerializer(serializers.Serializer):
    statement = serializers.CharField(
        max_length=1000, allow_blank=True, required=False, default=""
    )
