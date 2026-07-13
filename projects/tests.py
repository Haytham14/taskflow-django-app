from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from tasks.forms import TaskForm
from tasks.models import Task

from .models import Project


class ProjectCompletionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="project-admin@example.com",
            password="test",
            name="Admin Projet",
            role=User.Role.ADMIN,
        )
        self.member = User.objects.create_user(
            email="project-member@example.com",
            password="test",
            name="Membre Projet",
        )

    def test_completing_and_reopening_project_tracks_completion_date(self):
        project = Project.objects.create(name="Projet Cycle", created_by=self.admin)

        project.status = Project.Status.COMPLETED
        project.save(update_fields=["status"])
        project.refresh_from_db()
        self.assertIsNotNone(project.completed_at)

        project.status = Project.Status.ACTIVE
        project.save(update_fields=["status"])
        project.refresh_from_db()
        self.assertIsNone(project.completed_at)

    def test_completed_project_is_read_only_and_rejects_new_tasks(self):
        project = Project.objects.create(
            name="Projet Termine",
            status=Project.Status.COMPLETED,
            created_by=self.admin,
        )
        project.members.add(self.member)
        self.client.force_login(self.admin)

        board_response = self.client.get(reverse("projects:project_board", args=[project.pk]))
        create_response = self.client.get(reverse("projects:project_task_create", args=[project.pk]))

        self.assertContains(board_response, "Le tableau est en lecture seule")
        self.assertNotContains(board_response, "+ Nouvelle tâche")
        self.assertRedirects(create_response, reverse("projects:project_board", args=[project.pk]))
        self.assertFalse(Task.objects.filter(project=project).exists())

    def test_completed_projects_are_not_available_on_new_task_form(self):
        active = Project.objects.create(name="Projet Actif", created_by=self.admin)
        completed = Project.objects.create(
            name="Projet Archive",
            status=Project.Status.COMPLETED,
            created_by=self.admin,
        )

        project_ids = set(TaskForm().fields["project"].queryset.values_list("pk", flat=True))

        self.assertIn(active.pk, project_ids)
        self.assertNotIn(completed.pk, project_ids)
