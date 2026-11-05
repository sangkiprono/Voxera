from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from organizations.models import Membership

from .models import Poll, PollOption, PollResponse


class PollOptionSerializer(serializers.ModelSerializer):
    votes = serializers.IntegerField(read_only=True)

    class Meta:
        model = PollOption
        fields = ("id", "text", "position", "votes")
        read_only_fields = ("id", "votes")


class PollSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(
        source="organization.name", read_only=True, default=None
    )
    response_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Poll
        fields = (
            "id",
            "title",
            "question",
            "description",
            "visibility",
            "status",
            "ends_at",
            "created_by",
            "created_by_name",
            "organization",
            "organization_name",
            "options",
            "response_count",
            "created_at",
        )
        read_only_fields = fields

    def get_created_by_name(self, poll):
        return poll.created_by.get_full_name() or "Voxera member"


class PollCreateSerializer(serializers.ModelSerializer):
    options = serializers.ListField(
        child=serializers.CharField(max_length=160, allow_blank=False),
        min_length=2,
        max_length=12,
        write_only=True,
    )

    class Meta:
        model = Poll
        fields = (
            "title",
            "question",
            "description",
            "visibility",
            "ends_at",
            "organization",
            "options",
        )

    def validate_ends_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("The closing time must be in the future.")
        return value

    def validate_options(self, values):
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise serializers.ValidationError("Options cannot be blank.")
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise serializers.ValidationError("Poll options must be unique.")
        return normalized

    def create(self, validated_data):
        options = validated_data.pop("options")
        poll = Poll.objects.create(
            created_by=self.context["request"].user, **validated_data
        )
        PollOption.objects.bulk_create(
            [
                PollOption(poll=poll, text=text, position=position)
                for position, text in enumerate(options)
            ]
        )
        return poll


class PollUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Poll
        fields = ("title", "question", "description", "visibility", "ends_at", "status")

    def validate_ends_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("The closing time must be in the future.")
        return value


class PollResponseSerializer(serializers.Serializer):
    option_id = serializers.IntegerField()

    def validate_option_id(self, value):
        poll = self.context["poll"]
        if not PollOption.objects.filter(poll=poll, id=value).exists():
            raise serializers.ValidationError("Choose an option from this poll.")
        return value


class PollViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = (
            Poll.objects.select_related("created_by", "organization")
            .prefetch_related("options")
            .annotate(response_count=Count("responses", distinct=True))
        )
        user = self.request.user
        if user.is_authenticated:
            memberships = Membership.objects.filter(user=user).values(
                "organization_id"
            )
            queryset = queryset.filter(
                Q(visibility=Poll.Visibility.PUBLIC, status__in=("active", "closed"))
                | Q(created_by=user)
                | Q(organization_id__in=memberships)
            )
        else:
            queryset = queryset.filter(
                visibility=Poll.Visibility.PUBLIC,
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
        ):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.action == "create":
            return PollCreateSerializer
        if self.action in ("update", "partial_update"):
            return PollUpdateSerializer
        if self.action == "respond":
            return PollResponseSerializer
        return PollSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        response_data = PollSerializer(
            serializer.instance, context=self.get_serializer_context()
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
                    "You need an organization creator role to create its polls."
                )
        serializer.save()

    def _require_creator(self, poll):
        if poll.created_by_id == self.request.user.id:
            return
        membership = Membership.objects.filter(
            organization=poll.organization, user=self.request.user
        ).first()
        if membership is None or membership.role not in (
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        ):
            raise PermissionDenied(
                "Only the poll creator or an organization admin can do this."
            )

    def perform_update(self, serializer):
        poll = self.get_object()
        self._require_creator(poll)
        if poll.responses.exists() and "status" in serializer.validated_data:
            raise serializers.ValidationError(
                {"status": "A poll with responses cannot be reopened or edited this way."}
            )
        serializer.save()

    def perform_destroy(self, instance):
        self._require_creator(instance)
        if instance.responses.exists():
            raise serializers.ValidationError(
                "A poll with submitted responses cannot be deleted."
            )
        instance.delete()

    @action(detail=True, methods=["post"], url_path="responses")
    def respond(self, request, pk=None):
        poll = self.get_object()
        if poll.status != Poll.Status.ACTIVE or (
            poll.ends_at is not None and poll.ends_at <= timezone.now()
        ):
            return Response(
                {"detail": "This poll is closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=request.data, context={"poll": poll})
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                PollResponse.objects.create(
                    poll=poll,
                    user=request.user,
                    option_id=serializer.validated_data["option_id"],
                )
        except IntegrityError:
            return Response(
                {"detail": "You have already responded to this poll."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"detail": "Your response has been recorded."},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="results")
    def results(self, request, pk=None):
        poll = self.get_object()
        if poll.visibility == Poll.Visibility.PRIVATE and not request.user.is_authenticated:
            raise PermissionDenied("Sign in to view these results.")
        if poll.visibility == Poll.Visibility.PRIVATE:
            self._require_result_access(poll, request.user)

        options = poll.options.annotate(vote_count=Count("responses"))
        total = sum(option.vote_count for option in options)
        return Response(
            {
                "poll_id": poll.id,
                "question": poll.question,
                "total_responses": total,
                "options": [
                    {
                        "id": option.id,
                        "text": option.text,
                        "votes": option.vote_count,
                        "percentage": round(option.vote_count * 100 / total, 1)
                        if total
                        else 0,
                    }
                    for option in options
                ],
            }
        )

    def _require_result_access(self, poll, user):
        if poll.created_by_id == user.id:
            return
        if poll.organization_id and Membership.objects.filter(
            organization_id=poll.organization_id, user=user
        ).exists():
            return
        raise PermissionDenied("You do not have access to these results.")
