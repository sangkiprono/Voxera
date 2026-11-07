from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    class Kind(models.TextChoices):
        COMMENT = "comment", "New comment"
        WORKSPACE_ADDED = "workspace_added", "Added to workspace"
        ORGANIZATION_REVIEW = "organization_review", "Organization request reviewed"
        ORGANIZATION_INVITATION_ACCEPTED = (
            "organization_invitation_accepted",
            "Organization invitation accepted",
        )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="sent_notifications",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=40, choices=Kind.choices)
    message = models.CharField(max_length=240)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    poll = models.ForeignKey(
        "polls.Poll",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    survey = models.ForeignKey(
        "surveys.Survey",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("recipient", "read_at", "-created_at"),
                name="notification_inbox_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        organization__isnull=False,
                        poll__isnull=True,
                        survey__isnull=True,
                    )
                    | Q(
                        organization__isnull=True,
                        poll__isnull=False,
                        survey__isnull=True,
                    )
                    | Q(
                        organization__isnull=True,
                        poll__isnull=True,
                        survey__isnull=False,
                    )
                ),
                name="notification_has_one_target",
            )
        ]


class NotificationEmail(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    notification = models.OneToOneField(
        Notification, on_delete=models.CASCADE, related_name="email_delivery"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = [
            models.Index(
                fields=("status", "created_at"), name="notification_email_queue_idx"
            )
        ]
