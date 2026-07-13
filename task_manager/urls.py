from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from access_control import views as access_views
from accounts import views as account_views
from tasks import views as task_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("access/", include("access_control.urls")),
    path("accounts/", include("accounts.urls")),
    path("documents/", include("documents.urls")),
    path("projects/", include("projects.urls")),
    path("tasks/", include("tasks.urls")),
    path("api/chat/", include("chat.urls")),
    path("api/tasks/calendar/", task_views.task_calendar_api, name="task_calendar_api"),
    path(
        "api/tasks/<int:pk>/calendar-position/",
        task_views.update_calendar_position,
        name="task_calendar_position",
    ),
    path("work/dashboard/", RedirectView.as_view(pattern_name="dashboard:home", permanent=False)),
    path("work/tasks/", RedirectView.as_view(pattern_name="tasks:board", permanent=False)),
    path("work/projects/", RedirectView.as_view(pattern_name="projects:project_list", permanent=False)),
    path("work/chat/", access_views.WorkChatView.as_view(), name="work_chat"),
    path("users/list/", RedirectView.as_view(pattern_name="accounts:user_list", permanent=False)),
    path("users/roles/", account_views.RoleListView.as_view(), name="user_roles"),
    path("users/roles/new/", account_views.RoleCreateView.as_view(), name="role_create"),
    path("users/roles/<int:pk>/edit/", account_views.RoleUpdateView.as_view(), name="role_update"),
    path("users/roles/<int:pk>/delete/", account_views.RoleDeleteView.as_view(), name="role_delete"),
    path("users/departments/", account_views.DepartmentListView.as_view(), name="user_departments"),
    path("users/departments/new/", account_views.DepartmentCreateView.as_view(), name="department_create"),
    path("users/departments/<int:pk>/edit/", account_views.DepartmentUpdateView.as_view(), name="department_update"),
    path("users/departments/<int:pk>/delete/", account_views.DepartmentDeleteView.as_view(), name="department_delete"),
    path("users/permissions/", account_views.RolePermissionsView.as_view(), name="user_permissions"),
    path("api/habilitations/<int:pk>/", access_views.api_habilitation_detail, name="api_habilitation_detail"),
    path("api/habilitation-requests/<int:pk>/", access_views.api_request_detail, name="api_request_detail"),
    path("api/habilitation-requests/<int:pk>/submit/", access_views.api_request_submit, name="api_request_submit"),
    path(
        "api/habilitation-requests/<int:pk>/<str:action>/",
        access_views.api_request_action,
        name="api_request_action",
    ),
    path(
        "api/habilitation-assignments/<int:pk>/<str:action>/",
        access_views.api_assignment_action,
        name="api_assignment_action",
    ),
    path("api/<str:resource>/", access_views.api_collection, name="access_api_collection"),
    path("api/users/<int:pk>/habilitations/", access_views.api_user_habilitations, name="api_user_habilitations"),
    path("api/projects/<int:pk>/habilitations/", access_views.api_project_habilitations, name="api_project_habilitations"),
]
