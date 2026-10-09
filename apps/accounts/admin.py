from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.accounts.models import User


class AccountCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "display_name")


class AccountChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class AccountAdmin(UserAdmin):
    add_form = AccountCreationForm
    form = AccountChangeForm
    list_display = ("email", "display_name", "is_active", "is_staff")
    ordering = ("email",)
    search_fields = ("email", "display_name")
    fieldsets = (
        (None, {"fields": ("email", "password", "display_name")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Activity", {"fields": ("last_login",)}),
    )
    add_fieldsets = ((None, {"fields": ("email", "display_name", "password1", "password2")}),)
