from django.contrib import admin

from .models import (
    AuditLog,
    EmployeeMovement,
    Habilitation,
    HabilitationAccessType,
    HabilitationItem,
    HabilitationAssignment,
    HabilitationRequest,
    HabilitationRequestStep,
)


class HabilitationItemInline(admin.TabularInline):
    model = HabilitationItem
    extra = 1


class HabilitationAccessTypeInline(admin.TabularInline):
    model = HabilitationAccessType
    extra = 1


@admin.register(Habilitation)
class HabilitationAdmin(admin.ModelAdmin):
    list_display = ("application", "status", "responsible")
    list_filter = ("status",)
    search_fields = ("application", "items__name", "access_types__name", "description")
    autocomplete_fields = ("responsible",)
    inlines = [HabilitationItemInline, HabilitationAccessTypeInline]


class HabilitationRequestStepInline(admin.TabularInline):
    model = HabilitationRequestStep
    extra = 0
    autocomplete_fields = ("assigned_to",)


@admin.register(HabilitationRequest)
class HabilitationRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "requester", "habilitation", "status", "current_step", "created_at")
    list_filter = ("status", "urgency", "requested_access_type")
    search_fields = (
        "reference",
        "requester__name",
        "habilitation__application",
        "habilitation__items__name",
        "justification",
    )
    autocomplete_fields = (
        "requester",
        "habilitation",
        "project",
    )
    filter_horizontal = ("requested_habilitations",)
    inlines = [HabilitationRequestStepInline]
    date_hierarchy = "created_at"


@admin.register(HabilitationAssignment)
class HabilitationAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "habilitation", "status", "start_date", "end_date", "granted_by")
    list_filter = ("status",)
    search_fields = (
        "user__name",
        "habilitation__application",
        "habilitation__items__name",
    )
    autocomplete_fields = ("user", "habilitation", "request", "granted_by", "revoked_by")


@admin.register(EmployeeMovement)
class EmployeeMovementAdmin(admin.ModelAdmin):
    list_display = ("user", "movement_type", "effective_date", "status")
    list_filter = ("movement_type", "status")
    search_fields = ("user__name", "old_department", "new_department", "old_position", "new_position")
    autocomplete_fields = ("user",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "entity_type", "entity_id", "ip_address")
    list_filter = ("action", "entity_type")
    search_fields = ("action", "entity_type", "entity_id", "old_value", "new_value")
    autocomplete_fields = ("user",)
