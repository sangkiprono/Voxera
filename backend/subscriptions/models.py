from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class SubscriptionPlan(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    monthly_price_minor = models.PositiveBigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="KES")
    max_members = models.PositiveIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1),)
    )
    max_active_polls = models.PositiveIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1),)
    )
    max_active_surveys = models.PositiveIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1),)
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("monthly_price_minor", "name")
        constraints = [
            models.CheckConstraint(
                condition=Q(max_members__isnull=True) | Q(max_members__gte=1),
                name="subscription_plan_member_limit_positive",
            ),
            models.CheckConstraint(
                condition=Q(max_active_polls__isnull=True)
                | Q(max_active_polls__gte=1),
                name="subscription_plan_poll_limit_positive",
            ),
            models.CheckConstraint(
                condition=Q(max_active_surveys__isnull=True)
                | Q(max_active_surveys__gte=1),
                name="subscription_plan_survey_limit_positive",
            ),
        ]

    def __str__(self):
        return self.name


class OrganizationSubscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    started_at = models.DateTimeField(auto_now_add=True)
    current_period_ends_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("organization__name",)

    def __str__(self):
        return f"{self.organization} — {self.plan}"
