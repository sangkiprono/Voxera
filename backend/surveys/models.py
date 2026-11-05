from django.conf import settings
from django.db import models


class Survey(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="surveys",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="surveys",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title


class SurveyQuestion(models.Model):
    class QuestionType(models.TextChoices):
        SINGLE_CHOICE = "single_choice", "Single choice"
        MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
        SHORT_TEXT = "short_text", "Short text"
        LONG_TEXT = "long_text", "Long text"
        RATING = "rating", "Rating"

    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.CharField(max_length=500)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    is_required = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("survey", "position"), name="unique_survey_question_position"
            )
        ]

    def __str__(self):
        return self.text


class SurveyOption(models.Model):
    question = models.ForeignKey(
        SurveyQuestion, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=160)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("question", "position"), name="unique_survey_option_position"
            )
        ]

    def __str__(self):
        return self.text


class SurveyResponse(models.Model):
    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name="responses"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="survey_responses",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("survey", "user"), name="one_response_per_user_per_survey"
            )
        ]
        ordering = ("submitted_at",)

    def __str__(self):
        return f"{self.user} responded to {self.survey}"


class SurveyAnswer(models.Model):
    response = models.ForeignKey(
        SurveyResponse, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        SurveyQuestion, on_delete=models.PROTECT, related_name="answers"
    )
    text = models.CharField(max_length=1000, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    selected_options = models.ManyToManyField(
        SurveyOption, related_name="answers", blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("response", "question"), name="one_answer_per_survey_question"
            )
        ]

    def __str__(self):
        return f"Answer to {self.question}"
