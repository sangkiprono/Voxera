from django.contrib import admin

from .models import Election, ElectionCandidate, ElectionEligibleVoter


class ElectionCandidateInline(admin.TabularInline):
    model = ElectionCandidate
    extra = 0
    readonly_fields = ("user", "statement", "nominated_at")
    can_delete = False


class ElectionEligibleVoterInline(admin.TabularInline):
    model = ElectionEligibleVoter
    extra = 0
    readonly_fields = ("user", "captured_at")
    can_delete = False
    max_num = 0


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "status", "created_by", "created_at")
    list_filter = ("status", "organization")
    search_fields = ("title", "organization__name")
    readonly_fields = (
        "created_by",
        "created_at",
        "updated_at",
        "nominations_opened_at",
        "nominations_closed_at",
    )
    inlines = (ElectionCandidateInline, ElectionEligibleVoterInline)


@admin.register(ElectionCandidate)
class ElectionCandidateAdmin(admin.ModelAdmin):
    list_display = ("election", "user", "nominated_at")
    search_fields = ("election__title", "user__email")
    readonly_fields = ("nominated_at",)


@admin.register(ElectionEligibleVoter)
class ElectionEligibleVoterAdmin(admin.ModelAdmin):
    list_display = ("election", "user", "captured_at")
    search_fields = ("election__title", "user__email")
    readonly_fields = ("election", "user", "captured_at")
