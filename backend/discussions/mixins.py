from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from organizations.models import Membership

from .models import ActivityComment, CommentModeration
from .serializers import (
    ActivityCommentSerializer,
    CommentModerationSerializer,
    CommentSubmissionSerializer,
)


def can_moderate_activity_comments(activity, user):
    if not user.is_authenticated:
        return False
    if activity.created_by_id == user.id:
        return True
    return bool(
        activity.organization_id
        and Membership.objects.filter(
            organization_id=activity.organization_id,
            user=user,
            role__in=(Membership.Role.OWNER, Membership.Role.ADMIN),
        ).exists()
    )


class ActivityCommentsMixin:
    @action(detail=True, methods=["get", "post"], url_path="comments")
    def comments(self, request, pk=None):
        activity = self.get_object()
        comment_filter = {self.comment_field: activity}
        if request.method == "GET":
            comments = ActivityComment.objects.filter(**comment_filter).select_related(
                "author"
            )
            if not can_moderate_activity_comments(activity, request.user):
                comments = comments.filter(is_hidden=False)
            return Response(ActivityCommentSerializer(comments, many=True).data)

        if activity.status != "active" or (
            activity.ends_at is not None and activity.ends_at <= timezone.now()
        ):
            return Response(
                {"detail": "Comments are closed for this activity."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = CommentSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = ActivityComment.objects.create(
            **comment_filter,
            author=request.user,
            body=serializer.validated_data["body"],
        )
        return Response(
            ActivityCommentSerializer(comment).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"comments/(?P<comment_id>[^/.]+)/moderate",
    )
    def moderate_comment(self, request, pk=None, comment_id=None):
        activity = self.get_object()
        if not can_moderate_activity_comments(activity, request.user):
            raise PermissionDenied(
                "Only the activity creator or an organization administrator can moderate comments."
            )
        comment = get_object_or_404(
            ActivityComment, pk=comment_id, **{self.comment_field: activity}
        )
        serializer = CommentModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment.is_hidden = serializer.validated_data["is_hidden"]
        comment.save(update_fields=["is_hidden", "updated_at"])
        CommentModeration.objects.create(
            comment=comment,
            actor=request.user,
            is_hidden=comment.is_hidden,
            reason=serializer.validated_data.get("reason", "").strip(),
        )
        return Response(ActivityCommentSerializer(comment).data)
