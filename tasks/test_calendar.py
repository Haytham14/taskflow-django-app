import json
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from projects.models import Project

from .forms import TaskForm
from .models import Task

User = get_user_model()


class TaskCalendarTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-calendar@example.com",
            password="test",
            name="Admin Calendar",
            role=User.Role.ADMIN,
        )
        self.member = User.objects.create_user(
            email="member-calendar@example.com",
            password="test",
            name="Membre Calendar",
        )
        self.outsider = User.objects.create_user(
            email="outsider-calendar@example.com",
            password="test",
            name="Externe Calendar",
        )
        self.project = Project.objects.create(name="Projet visible", created_by=self.admin)
        self.project.members.add(self.member)
        self.other_project = Project.objects.create(name="Projet privé", created_by=self.admin)
        self.today = timezone.localdate()
        self.week_start = self.today - timedelta(days=self.today.weekday())

    def aware(self, day, hour=10):
        return timezone.make_aware(
            datetime.combine(day, time(hour=hour)),
            timezone.get_current_timezone(),
        )

    def create_task(self, title, day=None, **kwargs):
        return Task.objects.create(
            title=title,
            created_by=self.admin,
            deadline=self.aware(day) if day else None,
            **kwargs,
        )

    def calendar(self, start, end, **parameters):
        query = {"start": start.isoformat(), "end": end.isoformat(), **parameters}
        return self.client.get("/api/tasks/calendar/", query)

    def test_week_range_returns_only_tasks_in_week(self):
        inside = self.create_task("Dans la semaine", self.week_start, assigned_to=self.member)
        self.create_task("Hors semaine", self.week_start + timedelta(days=8), assigned_to=self.member)
        self.client.force_login(self.member)

        response = self.calendar(self.week_start, self.week_start + timedelta(days=6))

        self.assertEqual(response.status_code, 200)
        due_events = [
            task for task in response.json()["tasks"] if task["event_type"] == "due"
        ]
        self.assertEqual([task["id"] for task in due_events], [inside.pk])

    def test_month_range_returns_correct_tasks(self):
        month_start = self.today.replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        inside = self.create_task("Dans le mois", month_start, assigned_to=self.member)
        self.create_task("Mois suivant", next_month, assigned_to=self.member)
        self.client.force_login(self.member)

        response = self.calendar(month_start, month_end, view="month")

        due_events = [
            task for task in response.json()["tasks"] if task["event_type"] == "due"
        ]
        self.assertEqual([task["id"] for task in due_events], [inside.pk])

    def test_search_filters_title_project_and_assignee(self):
        task = self.create_task(
            "Restaurer la sauvegarde",
            self.today,
            project=self.project,
            assigned_to=self.member,
        )
        self.create_task("Autre tâche", self.today, assigned_to=self.member)
        self.client.force_login(self.member)

        title_response = self.calendar(self.today, self.today, search="sauvegarde")
        project_response = self.calendar(self.today, self.today, search="Projet visible")
        assignee_response = self.calendar(self.today, self.today, search="Membre Calendar")

        self.assertEqual({item["id"] for item in title_response.json()["tasks"]}, {task.pk})
        self.assertIn(task.pk, [item["id"] for item in project_response.json()["tasks"]])
        self.assertIn(task.pk, [item["id"] for item in assignee_response.json()["tasks"]])

    def test_project_filter_works(self):
        visible = self.create_task(
            "Projet attendu",
            self.today,
            project=self.project,
            assigned_to=self.member,
        )
        self.create_task("Sans projet", self.today, assigned_to=self.member)
        self.client.force_login(self.member)

        response = self.calendar(self.today, self.today, project=str(self.project.pk))

        self.assertEqual({task["id"] for task in response.json()["tasks"]}, {visible.pk})

    def test_statistics_count_overdue_completed_and_without_due_date(self):
        yesterday = self.today - timedelta(days=1)
        self.create_task("En retard", yesterday, assigned_to=self.member)
        self.create_task(
            "Terminée",
            self.today,
            assigned_to=self.member,
            status=Task.Status.DONE,
        )
        self.create_task("Sans délai", assigned_to=self.member)
        self.client.force_login(self.member)

        response = self.calendar(yesterday, self.today)
        statistics = response.json()["statistics"]

        self.assertEqual(statistics["total"], 3)
        self.assertEqual(statistics["overdue"], 1)
        self.assertEqual(statistics["completed"], 1)
        self.assertEqual(statistics["without_due_date"], 1)

    def test_unauthorized_user_cannot_see_restricted_tasks(self):
        restricted = self.create_task("Tâche privée", self.today, project=self.other_project)
        self.client.force_login(self.outsider)

        response = self.calendar(self.today, self.today)

        self.assertNotIn(restricted.pk, [task["id"] for task in response.json()["tasks"]])

    def test_changing_calendar_position_updates_original_task(self):
        task = self.create_task("Déplacer", self.today, assigned_to=self.member)
        new_start = self.aware(self.today + timedelta(days=1), 14)
        self.client.force_login(self.admin)

        response = self.client.patch(
            f"/api/tasks/{task.pk}/calendar-position/",
            data=json.dumps(
                {
                    "start": new_start.isoformat(),
                    "end": (new_start + timedelta(hours=1)).isoformat(),
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.deadline, new_start)

    def test_member_cannot_change_calendar_position(self):
        task = self.create_task("Non modifiable", self.today, assigned_to=self.member)
        self.client.force_login(self.member)

        response = self.client.patch(
            f"/api/tasks/{task.pk}/calendar-position/",
            data=json.dumps({"start": self.aware(self.today + timedelta(days=1)).isoformat()}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_created_task_appears_in_board_and_calendar(self):
        self.client.force_login(self.admin)
        deadline = self.aware(self.today, 11)

        response = self.client.post(
            "/tasks/new/",
            {
                "title": "Créée depuis le calendrier",
                "description": "",
                "status": Task.Status.TODO,
                "priority": Task.Priority.HIGH,
                "deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
                "project": "",
                "assigned_to": self.member.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title="Créée depuis le calendrier")
        board_response = self.client.get("/tasks/")
        calendar_response = self.calendar(self.today, self.today)
        self.assertContains(board_response, task.title)
        self.assertIn(task.pk, [item["id"] for item in calendar_response.json()["tasks"]])
        task_events = [
            item["event_type"]
            for item in calendar_response.json()["tasks"]
            if item["id"] == task.pk
        ]
        self.assertCountEqual(task_events, ["created", "due"])

    def test_task_without_deadline_appears_at_creation_time(self):
        task = self.create_task("Créée sans échéance", assigned_to=self.member)
        self.client.force_login(self.member)

        response = self.calendar(self.today, self.today)
        task_events = [
            item for item in response.json()["tasks"] if item["id"] == task.pk
        ]

        self.assertEqual(len(task_events), 1)
        self.assertEqual(task_events[0]["event_type"], "created")
        self.assertEqual(task_events[0]["event_label"], "Créée")

    def test_project_task_form_can_assign_any_active_user(self):
        self.client.force_login(self.admin)

        response = self.client.get(f"/projects/{self.other_project.pk}/tasks/new/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.member.name)
        self.assertContains(response, self.outsider.name)

    def test_status_transitions_record_verification_and_completion_dates(self):
        task = self.create_task("Suivi des étapes", assigned_to=self.member)

        task.status = Task.Status.TO_VERIFY
        task.save(update_fields=["status", "updated_at"])
        task.refresh_from_db()
        verification_at = task.verification_at

        self.assertIsNotNone(verification_at)
        self.assertIsNone(task.completed_at)

        task.status = Task.Status.DONE
        task.save(update_fields=["status", "updated_at"])
        task.refresh_from_db()

        self.assertEqual(task.verification_at, verification_at)
        self.assertIsNotNone(task.completed_at)

    def test_dashboard_displays_task_lifecycle_date_columns(self):
        task = self.create_task("Dates du cycle", assigned_to=self.member)
        task.status = Task.Status.TO_VERIFY
        task.save(update_fields=["status", "updated_at"])
        task.status = Task.Status.DONE
        task.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.admin)

        response = self.client.get("/")

        self.assertContains(response, "Créée le")
        self.assertContains(response, "Mise à vérifier le")
        self.assertContains(response, "Terminée le")
        self.assertContains(response, task.created_at.strftime("%Y"))


class TaskAssignmentFormTests(TestCase):
    def test_all_active_user_roles_can_be_assigned(self):
        active_users = [
            User.objects.create_user(
                email=f"{role.lower()}@example.com",
                password="test",
                name=f"Utilisateur {role}",
                role=role,
            )
            for role in (
                User.Role.MEMBER,
                User.Role.COLLABORATOR,
                User.Role.MANAGER,
                User.Role.ADMIN,
            )
        ]
        inactive = User.objects.create_user(
            email="inactive@example.com",
            password="test",
            name="Utilisateur inactif",
            is_active=False,
        )

        assignee_ids = set(TaskForm().fields["assignees"].queryset.values_list("pk", flat=True))

        self.assertTrue({user.pk for user in active_users}.issubset(assignee_ids))
        self.assertNotIn(inactive.pk, assignee_ids)
