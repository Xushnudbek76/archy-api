from django.contrib import admin

from apps.courses.models import Course


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "created_at", "archived_at")
    list_filter = ("archived_at",)
    search_fields = ("title",)
    autocomplete_fields = ("owner",)
