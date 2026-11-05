from rest_framework import serializers

from .models import ActivityComment


class ActivityCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityComment
        fields = ("id", "body", "author", "author_name", "is_hidden", "created_at")
        read_only_fields = fields

    def get_author_name(self, comment):
        return comment.author.get_full_name() or "Voxera member"


class CommentSubmissionSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000, trim_whitespace=True)


class CommentModerationSerializer(serializers.Serializer):
    is_hidden = serializers.BooleanField()
    reason = serializers.CharField(max_length=300, allow_blank=True, required=False)
