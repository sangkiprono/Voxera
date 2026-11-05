from rest_framework.exceptions import ValidationError

from .models import OrganizationSubscription


def _subscribed_plan(organization):
    try:
        subscription = organization.subscription
    except OrganizationSubscription.DoesNotExist:
        return None
    return subscription.plan


def enforce_member_limit(organization):
    plan = _subscribed_plan(organization)
    if plan is not None and plan.max_members is not None:
        if organization.memberships.count() >= plan.max_members:
            raise ValidationError(
                {"email": f"The {plan.name} plan allows up to {plan.max_members} members."}
            )


def enforce_activity_limit(organization, activity_type):
    plan = _subscribed_plan(organization)
    if plan is None:
        return
    if activity_type == "poll":
        limit = plan.max_active_polls
        current = organization.polls.filter(status="active").count()
        label = "active polls"
    elif activity_type == "survey":
        limit = plan.max_active_surveys
        current = organization.surveys.filter(status="active").count()
        label = "active surveys"
    else:
        raise ValueError(f"Unknown activity type: {activity_type}")

    if limit is not None and current >= limit:
        raise ValidationError(
            {
                "organization": (
                    f"The {plan.name} plan allows up to {limit} {label}."
                )
            }
        )
