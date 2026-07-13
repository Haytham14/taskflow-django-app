from django.urls import path

from . import views

app_name = "access_control"

urlpatterns = [
    path("dashboard/", views.AccessDashboardView.as_view(), name="dashboard"),
    path("requests/", views.HabilitationRequestListView.as_view(), name="request_list"),
    path("requests/new/", views.HabilitationRequestCreateView.as_view(), name="request_create"),
    path("requests/<int:pk>/", views.HabilitationRequestDetailView.as_view(), name="request_detail"),
    path("requests/<int:pk>/edit/", views.HabilitationRequestUpdateView.as_view(), name="request_update"),
    path("requests/<int:pk>/delete/", views.HabilitationRequestDeleteView.as_view(), name="request_delete"),
    path("catalog/", views.HabilitationCatalogView.as_view(), name="catalog"),
    path("catalog/new/", views.HabilitationCreateView.as_view(), name="catalog_create"),
    path("catalog/<int:pk>/", views.HabilitationDetailView.as_view(), name="catalog_detail"),
    path("catalog/<int:pk>/edit/", views.HabilitationUpdateView.as_view(), name="catalog_update"),
    path("catalog/<int:pk>/delete/", views.HabilitationDeleteView.as_view(), name="catalog_delete"),
    path("validations/", views.ValidationsView.as_view(), name="validations"),
    path("granted/", views.GrantedAccessView.as_view(), name="granted"),
    path("granted/<int:pk>/edit/", views.HabilitationAssignmentUpdateView.as_view(), name="assignment_update"),
    path("granted/<int:pk>/delete/", views.HabilitationAssignmentDeleteView.as_view(), name="assignment_delete"),
    path("hr-movements/", views.EmployeeMovementListView.as_view(), name="hr_movements"),
    path("hr-movements/<int:pk>/edit/", views.EmployeeMovementUpdateView.as_view(), name="movement_update"),
    path("hr-movements/<int:pk>/delete/", views.EmployeeMovementDeleteView.as_view(), name="movement_delete"),
    path("audit/", views.AuditLogView.as_view(), name="audit"),
    path("audit/clear/", views.AuditLogClearView.as_view(), name="audit_clear"),
    path("audit/<int:pk>/delete/", views.AuditLogDeleteView.as_view(), name="audit_delete"),
]
