from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.BoardView.as_view(), name="board"),
    path("calendar/", views.TaskCalendarView.as_view(), name="calendar"),
    path("new/", views.TaskCreateView.as_view(), name="task_create"),
    path("<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task_update"),
    path("<int:pk>/delete/", views.TaskDeleteView.as_view(), name="task_delete"),
    path("<int:pk>/status/confirm/", views.confirm_task_status, name="confirm_status"),
    path("<int:pk>/status/", views.update_task_status, name="update_status"),
    path("<int:pk>/", views.TaskDetailView.as_view(), name="task_detail"),
    path("<int:pk>/comments/add/", views.add_comment, name="add_comment"),
    path("comments/<int:pk>/delete/", views.delete_comment, name="delete_comment"),
    path("<int:pk>/attachments/add/", views.add_attachment, name="add_attachment"),
    path("attachments/<int:pk>/delete/", views.delete_attachment, name="delete_attachment"),
    path("attachments/<int:pk>/download/", views.download_attachment, name="download_attachment"),
]
