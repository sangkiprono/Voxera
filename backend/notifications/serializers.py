from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    organization_slug = serializers.CharField(
        source="organization.slug", read_only=True, default=None
    )
    target_title = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "message",
            "actor_name",
            "organization_slug",
            "poll_id",
            "survey_id",
            "target_title",
            "created_at",
            "read_at",
        )
        read_only_fields = fields

    def get_actor_name(self, notification):
        if notification.actor is None:
            return "Voxera"
        return notification.actor.get_full_name() or "Voxera member"

    def get_target_title(self, notification):
        if notification.poll_id:
            return notification.poll.title
        if notification.survey_id:
            return notification.survey.title
        return notification.organization.name
