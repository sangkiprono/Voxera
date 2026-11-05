from django.utils import timezone
from django.db import transaction
from rest_framework import serializers

from .models import (
    Survey,
    SurveyAnswer,
    SurveyOption,
    SurveyQuestion,
    SurveyResponse,
)


class SurveyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyOption
        fields = ("id", "text", "position")
        read_only_fields = fields


class SurveyQuestionSerializer(serializers.ModelSerializer):
    options = SurveyOptionSerializer(many=True, read_only=True)

    class Meta:
        model = SurveyQuestion
        fields = ("id", "text", "question_type", "is_required", "position", "options")
        read_only_fields = fields


class SurveyQuestionInputSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=500, trim_whitespace=True)
    question_type = serializers.ChoiceField(choices=SurveyQuestion.QuestionType.choices)
    is_required = serializers.BooleanField(default=True)
    options = serializers.ListField(
        child=serializers.CharField(max_length=160, allow_blank=False),
        required=False,
        default=list,
        max_length=12,
    )

    def validate(self, attrs):
        question_type = attrs["question_type"]
        options = [option.strip() for option in attrs["options"]]
        uses_options = question_type in (
            SurveyQuestion.QuestionType.SINGLE_CHOICE,
            SurveyQuestion.QuestionType.MULTIPLE_CHOICE,
        )
        if uses_options and len(options) < 2:
            raise serializers.ValidationError(
                {"options": "Choice questions need at least two options."}
            )
        if not uses_options and options:
            raise serializers.ValidationError(
                {"options": "Only choice questions can have options."}
            )
        if any(not option for option in options):
            raise serializers.ValidationError(
                {"options": "Options cannot be blank."}
            )
        if len({option.casefold() for option in options}) != len(options):
            raise serializers.ValidationError(
                {"options": "Options must be unique within a question."}
            )
        attrs["options"] = options
        return attrs


class SurveyCreateSerializer(serializers.ModelSerializer):
    questions = SurveyQuestionInputSerializer(
        many=True, write_only=True, min_length=1, max_length=20
    )

    class Meta:
        model = Survey
        fields = (
            "title",
            "description",
            "visibility",
            "ends_at",
            "organization",
            "questions",
        )

    def validate_ends_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("The closing time must be in the future.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        questions = validated_data.pop("questions")
        survey = Survey.objects.create(
            created_by=self.context["request"].user, **validated_data
        )
        for position, question_data in enumerate(questions):
            options = question_data.pop("options")
            question = SurveyQuestion.objects.create(
                survey=survey, position=position, **question_data
            )
            SurveyOption.objects.bulk_create(
                [
                    SurveyOption(question=question, text=text, position=option_position)
                    for option_position, text in enumerate(options)
                ]
            )
        return survey


class SurveyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Survey
        fields = ("title", "description", "visibility", "ends_at", "status")

    def validate_ends_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("The closing time must be in the future.")
        return value


class SurveySerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(
        source="organization.name", read_only=True, default=None
    )
    response_count = serializers.IntegerField(read_only=True)
    has_responded = serializers.SerializerMethodField()

    class Meta:
        model = Survey
        fields = (
            "id",
            "title",
            "description",
            "visibility",
            "status",
            "ends_at",
            "created_by",
            "created_by_name",
            "organization",
            "organization_name",
            "questions",
            "response_count",
            "has_responded",
            "created_at",
        )
        read_only_fields = fields

    def get_created_by_name(self, survey):
        return survey.created_by.get_full_name() or "Voxera member"

    def get_has_responded(self, survey):
        user = self.context["request"].user
        return user.is_authenticated and survey.responses.filter(user=user).exists()


class SurveySubmissionSerializer(serializers.Serializer):
    answers = serializers.ListField(
        child=serializers.DictField(), allow_empty=True, max_length=20
    )

    def validate_answers(self, answers):
        survey = self.context["survey"]
        questions = list(survey.questions.prefetch_related("options"))
        questions_by_id = {question.id: question for question in questions}
        seen_ids = set()
        normalized = []

        for answer in answers:
            question_id = answer.get("question_id")
            if isinstance(question_id, bool) or not isinstance(question_id, int):
                raise serializers.ValidationError(
                    "Each answer needs a valid question_id."
                )
            if question_id in seen_ids:
                raise serializers.ValidationError(
                    "Each question can only be answered once."
                )
            seen_ids.add(question_id)
            question = questions_by_id.get(question_id)
            if question is None:
                raise serializers.ValidationError(
                    "An answer refers to a question outside this survey."
                )
            normalized.append(
                self._validate_answer(question, answer)
            )

        missing_required = [
            question.text
            for question in questions
            if question.is_required and question.id not in seen_ids
        ]
        if missing_required:
            raise serializers.ValidationError(
                f"Please answer all required questions: {', '.join(missing_required)}."
            )
        return normalized

    @staticmethod
    def _validate_answer(question, answer):
        question_type = question.question_type
        allowed_fields = {
            SurveyQuestion.QuestionType.SINGLE_CHOICE: {"question_id", "option_id"},
            SurveyQuestion.QuestionType.MULTIPLE_CHOICE: {"question_id", "option_ids"},
            SurveyQuestion.QuestionType.SHORT_TEXT: {"question_id", "text"},
            SurveyQuestion.QuestionType.LONG_TEXT: {"question_id", "text"},
            SurveyQuestion.QuestionType.RATING: {"question_id", "rating"},
        }[question_type]
        if set(answer) - allowed_fields:
            raise serializers.ValidationError(
                f"The answer for “{question.text}” has unexpected fields."
            )

        result = {"question": question, "text": "", "rating": None, "options": []}
        if question_type == SurveyQuestion.QuestionType.SINGLE_CHOICE:
            option_id = answer.get("option_id")
            if isinstance(option_id, bool) or not isinstance(option_id, int):
                raise serializers.ValidationError(
                    f"Choose an option for “{question.text}”."
                )
            option_ids = [option_id]
        elif question_type == SurveyQuestion.QuestionType.MULTIPLE_CHOICE:
            option_ids = answer.get("option_ids")
            if not isinstance(option_ids, list) or any(
                isinstance(option_id, bool) or not isinstance(option_id, int)
                for option_id in option_ids
            ):
                raise serializers.ValidationError(
                    f"Choose one or more options for “{question.text}”."
                )
        else:
            option_ids = []

        if question_type in (
            SurveyQuestion.QuestionType.SINGLE_CHOICE,
            SurveyQuestion.QuestionType.MULTIPLE_CHOICE,
        ):
            if len(set(option_ids)) != len(option_ids):
                raise serializers.ValidationError(
                    f"Duplicate choices are not allowed for “{question.text}”."
                )
            options_by_id = {option.id: option for option in question.options.all()}
            if any(option_id not in options_by_id for option_id in option_ids):
                raise serializers.ValidationError(
                    f"Choose only options from “{question.text}”."
                )
            if question.is_required and not option_ids:
                raise serializers.ValidationError(
                    f"Please answer “{question.text}”."
                )
            result["options"] = [options_by_id[option_id] for option_id in option_ids]
        elif question_type in (
            SurveyQuestion.QuestionType.SHORT_TEXT,
            SurveyQuestion.QuestionType.LONG_TEXT,
        ):
            text = answer.get("text", "")
            if not isinstance(text, str) or len(text) > 1000:
                raise serializers.ValidationError(
                    f"Enter a valid answer for “{question.text}” (up to 1,000 characters)."
                )
            result["text"] = text.strip()
            if question.is_required and not result["text"]:
                raise serializers.ValidationError(
                    f"Please answer “{question.text}”."
                )
        else:
            rating = answer.get("rating")
            if (
                isinstance(rating, bool)
                or not isinstance(rating, int)
                or rating < 1
                or rating > 5
            ):
                raise serializers.ValidationError(
                    f"Choose a rating from 1 to 5 for “{question.text}”."
                )
            result["rating"] = rating
        return result

    def create(self, validated_data):
        response = validated_data.pop("response", None)
        if response is None:
            response = SurveyResponse.objects.create(
                survey=self.context["survey"], user=self.context["request"].user
            )
        for answer_data in validated_data["answers"]:
            options = answer_data.pop("options")
            answer = SurveyAnswer.objects.create(response=response, **answer_data)
            answer.selected_options.set(options)
        return response
