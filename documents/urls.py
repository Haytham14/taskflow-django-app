from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("dashboard/", views.DocumentDashboardView.as_view(), name="dashboard"),
    path("all/", views.DocumentListView.as_view(), name="all"),
    path("procedures/", views.ProcedureListView.as_view(), name="procedures"),
    path("templates/", views.TemplateListView.as_view(), name="templates"),
    path("attachments/", views.AttachmentListView.as_view(), name="attachments"),
    path("archives/", views.ArchiveListView.as_view(), name="archives"),
    path("history/", views.DocumentHistoryView.as_view(), name="history"),
    path("new/", views.DocumentCreateView.as_view(), name="create"),
    path("<int:pk>/", views.DocumentDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.DocumentUpdateView.as_view(), name="update"),
    path("<int:pk>/open/", views.DocumentOpenView.as_view(), name="open"),
    path("<int:pk>/download/", views.DocumentDownloadView.as_view(), name="download"),
    path("<int:pk>/archive/", views.DocumentArchiveView.as_view(), name="archive"),
]
