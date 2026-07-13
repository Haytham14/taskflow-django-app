from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import AdminUserChangeForm, UserCreateForm
from .models import AppRole, Department, User


@admin.register(AppRole)
class AppRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "is_system", "updated_at")
    search_fields = ("name", "description")
    filter_horizontal = ("permissions",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "manager", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    autocomplete_fields = ("manager",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreateForm
    form = AdminUserChangeForm
    model = User

    list_display = ("email", "name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "name")
    ordering = ("name",)
    filter_horizontal = ("groups", "user_permissions")
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Informations personnelles", {"fields": ("name", "role", "custom_role", "department")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates importantes", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "role", "custom_role", "department", "password1", "password2"),
            },
        ),
    )
