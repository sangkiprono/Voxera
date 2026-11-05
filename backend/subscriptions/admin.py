from django.contrib import admin

from .models import OrganizationSubscription, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "monthly_price_minor",
        "currency",
        "max_members",
        "max_active_polls",
        "max_active_surveys",
        "is_active",
    )
    list_filter = ("is_active", "currency")
    search_fields = ("name", "code")


@admin.register(OrganizationSubscription)
class OrganizationSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "plan",
        "status",
        "started_at",
        "current_period_ends_at",
    )
    list_filter = ("status", "plan")
    search_fields = ("organization__name", "plan__name")
    readonly_fields = ("started_at", "updated_at")
