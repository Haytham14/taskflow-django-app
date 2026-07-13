from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from projects.models import Project
from tasks.models import Task


class TaskDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="dashboard-admin@example.com",
            password="test",
            name="Admin Dashboard",
            role=User.Role.ADMIN,
        )
        self.member = User.objects.create_user(
            email="dashboard-member@example.com",
            password="test",
            name="Membre Dashboard",
        )
        self.second_member = User.objects.create_user(
            email="dashboard-second@example.com",
            password="test",
            name="Deuxieme Membre",
        )
        self.project = Project.objects.create(name="Projet Dashboard", created_by=self.admin)
        self.project.members.add(self.member)

    def create_task(self, title, deadline=None, assignees=(), **kwargs):
        task = Task.objects.create(
            title=title,
            deadline=deadline,
            created_by=self.admin,
            **kwargs,
        )
        task.assignees.add(*assignees)
        return task

    def test_dashboard_displays_active_and_completed_projects(self):
        now = timezone.now()
        Project.objects.create(
            name="Projet termine dashboard",
            status=Project.Status.COMPLETED,
            created_by=self.admin,
        )
        self.create_task(
            "Tache en retard",
            deadline=now - timedelta(hours=2),
            assignees=(self.member,),
            project=self.project,
        )
        self.create_task(
            "Tache proche",
            deadline=now + timedelta(days=2),
            assignees=(self.member,),
        )
        self.create_task("Sans date", assignees=(self.member,))

        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:home"), {"range": "month"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_project_count"], 1)
        self.assertEqual(response.context["completed_project_count"], 1)
        self.assertNotIn("overdue_count", response.context)
        self.assertNotIn("due_soon_count", response.context)
        self.assertNotIn("without_deadline_count", response.context)
        self.assertNotIn("period_comment_count", response.context)
        self.assertContains(response, "Projets actifs")
        self.assertContains(response, "Projets terminés")
        self.assertNotContains(response, "Commentaires sur la période")
        self.assertNotContains(response, "Fichiers sur la période")
        self.assertContains(response, "Tâches à surveiller")

    def test_project_member_sees_unassigned_project_task(self):
        task = self.create_task("Visible par le projet", project=self.project)
        self.client.force_login(self.member)

        response = self.client.get(reverse("dashboard:home"), {"range": "month"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, task.title)

    def test_recent_task_displays_all_assignees(self):
        self.create_task(
            "Tache partagee",
            assignees=(self.member, self.second_member),
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("dashboard:home"), {"range": "month"})

        self.assertContains(response, 'title="Membre Dashboard"')
        self.assertContains(response, 'title="Deuxieme Membre"')
