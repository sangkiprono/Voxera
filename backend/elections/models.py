from django.conf import settings
from django.db import models


class Election(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        NOMINATIONS = "nominations", "Nominations open"
        READY = "ready", "Nominations closed"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="elections",
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_elections",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    nominations_opened_at = models.DateTimeField(null=True, blank=True)
    nominations_closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title


class ElectionEligibleVoter(models.Model):
    election = models.ForeignKey(
        Election, on_delete=models.CASCADE, related_name="eligible_voters"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="election_eligibilities",
    )
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("election", "user"), name="unique_election_eligible_voter"
            )
        ]
        ordering = ("id",)


class ElectionCandidate(models.Model):
    election = models.ForeignKey(
        Election, on_delete=models.CASCADE, related_name="candidates"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="election_candidacies",
    )
    statement = models.CharField(max_length=1000, blank=True)
    nominated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("election", "user"), name="unique_election_candidate"
            )
        ]
        ordering = ("nominated_at", "id")
