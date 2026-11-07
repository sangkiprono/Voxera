from django.contrib import admin

from .models import Membership, Organization


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0

    def has_add_permission(self, request, obj=None):
        return (
            obj is not None
            and obj.status == Organization.Status.APPROVED
            and super().has_add_permission(request, obj)
        )


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "created_by", "reviewed_at", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "created_by__email")
    readonly_fields = ("status", "review_reason", "reviewed_by", "reviewed_at")
    inlines = (MembershipInline,)
