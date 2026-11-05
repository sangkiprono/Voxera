from django.contrib import admin

from .models import (
    Survey,
    SurveyAnswer,
    SurveyOption,
    SurveyQuestion,
    SurveyResponse,
)


class SurveyOptionInline(admin.TabularInline):
    model = SurveyOption
    extra = 0


class SurveyQuestionInline(admin.StackedInline):
    model = SurveyQuestion
    extra = 0
    show_change_link = True


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("title", "visibility", "status", "created_by", "organization")
    list_filter = ("visibility", "status")
    search_fields = ("title", "created_by__email")
    inlines = (SurveyQuestionInline,)


@admin.register(SurveyQuestion)
class SurveyQuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "survey", "question_type", "is_required", "position")
    list_filter = ("question_type", "is_required")
    inlines = (SurveyOptionInline,)


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ("survey", "user", "submitted_at")
    list_filter = ("submitted_at",)
    search_fields = ("survey__title", "user__email")


@admin.register(SurveyAnswer)
class SurveyAnswerAdmin(admin.ModelAdmin):
    list_display = ("question", "response", "rating")
