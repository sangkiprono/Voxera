from django.contrib import admin

from .models import Poll, PollOption, PollResponse


class PollOptionInline(admin.TabularInline):
    model = PollOption
    extra = 0


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("title", "visibility", "status", "created_by", "organization")
    list_filter = ("visibility", "status")
    search_fields = ("title", "question", "created_by__email")
    inlines = (PollOptionInline,)


@admin.register(PollResponse)
class PollResponseAdmin(admin.ModelAdmin):
    list_display = ("poll", "user", "option", "submitted_at")
    list_filter = ("submitted_at",)
    search_fields = ("poll__title", "user__email")
