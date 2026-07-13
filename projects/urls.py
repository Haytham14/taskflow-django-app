from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.ProjectListView.as_view(), name="project_list"),
    path("new/", views.ProjectCreateView.as_view(), name="project_create"),
    path("<int:pk>/edit/", views.ProjectUpdateView.as_view(), name="project_update"),
    path("<int:pk>/delete/", views.ProjectDeleteView.as_view(), name="project_delete"),
    path("<int:pk>/", views.ProjectBoardView.as_view(), name="project_board"),
    path("<int:pk>/tasks/new/", views.ProjectTaskCreateView.as_view(), name="project_task_create"),
]
