from rest_framework import serializers

from .models import OrganizationSubscription


class OrganizationSubscriptionStatusSerializer(serializers.Serializer):
    subscription = serializers.SerializerMethodField()
    usage = serializers.SerializerMethodField()

    def get_subscription(self, organization):
        try:
            subscription = organization.subscription
        except OrganizationSubscription.DoesNotExist:
            return None
        return OrganizationSubscriptionSerializer(
            subscription, context=self.context
        ).data

    def get_usage(self, organization):
        return {
            "members": organization.memberships.count(),
            "active_polls": organization.polls.filter(status="active").count(),
            "active_surveys": organization.surveys.filter(status="active").count(),
        }


class OrganizationSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    monthly_price_minor = serializers.IntegerField(
        source="plan.monthly_price_minor", read_only=True, allow_null=True
    )
    currency = serializers.CharField(source="plan.currency", read_only=True)
    max_members = serializers.IntegerField(source="plan.max_members", read_only=True)
    max_active_polls = serializers.IntegerField(
        source="plan.max_active_polls", read_only=True
    )
    max_active_surveys = serializers.IntegerField(
        source="plan.max_active_surveys", read_only=True
    )
    member_count = serializers.SerializerMethodField()
    active_poll_count = serializers.SerializerMethodField()
    active_survey_count = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationSubscription
        fields = (
            "plan_name",
            "plan_code",
            "monthly_price_minor",
            "currency",
            "max_members",
            "max_active_polls",
            "max_active_surveys",
            "status",
            "started_at",
            "current_period_ends_at",
            "member_count",
            "active_poll_count",
            "active_survey_count",
        )
        read_only_fields = fields

    def get_member_count(self, subscription):
        return subscription.organization.memberships.count()

    def get_active_poll_count(self, subscription):
        return subscription.organization.polls.filter(status="active").count()

    def get_active_survey_count(self, subscription):
        return subscription.organization.surveys.filter(status="active").count()
