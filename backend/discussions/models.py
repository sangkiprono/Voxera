from django.conf import settings
from django.db import models
from django.db.models import Q


class ActivityComment(models.Model):
    poll = models.ForeignKey(
        "polls.Poll",
        on_delete=models.CASCADE,
        related_name="comments",
        null=True,
        blank=True,
    )
    survey = models.ForeignKey(
        "surveys.Survey",
        on_delete=models.CASCADE,
        related_name="comments",
        null=True,
        blank=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_comments",
    )
    body = models.CharField(max_length=2000)
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(poll__isnull=False, survey__isnull=True)
                    | Q(poll__isnull=True, survey__isnull=False)
                ),
                name="comment_has_one_activity",
            )
        ]

    def __str__(self):
        return f"Comment by {self.author_id} on activity {self.pk}"


class CommentModeration(models.Model):
    comment = models.ForeignKey(
        ActivityComment, on_delete=models.CASCADE, related_name="moderation_events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comment_moderation_events",
    )
    is_hidden = models.BooleanField()
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
