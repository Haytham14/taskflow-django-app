from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.models import User
from projects.models import Project
from tasks.models import Task
from tasks.utils import resolve_date_range


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        range_key, start_date, end_date, start_dt, end_dt = resolve_date_range(self.request)

        visible_tasks = Task.objects.all()
        if not user.is_admin_role:
            visible_tasks = visible_tasks.filter(
                Q(assignees=user) | Q(project__members=user)
            ).distinct()

        period_tasks = visible_tasks.filter(created_at__range=(start_dt, end_dt))

        status_counts = {
            row["status"]: row["count"]
            for row in period_tasks.values("status").annotate(count=Count("id", distinct=True))
        }
        priority_counts = {
            row["priority"]: row["count"]
            for row in period_tasks.values("priority").annotate(count=Count("id", distinct=True))
        }

        now = timezone.now()
        open_tasks = visible_tasks.exclude(status=Task.Status.DONE)
        visible_projects = Project.objects.all()
        if not user.is_admin_role:
            visible_projects = visible_projects.filter(members=user)
        period_project_count = period_tasks.aggregate(
            project_count=Count("project", distinct=True),
        )["project_count"]

        context["active_range"] = range_key
        context["range_start"] = start_date
        context["range_end"] = end_date

        total_tasks = period_tasks.count()
        context["total_tasks"] = total_tasks
        context["todo_count"] = status_counts.get(Task.Status.TODO, 0)
        context["in_progress_count"] = status_counts.get(Task.Status.IN_PROGRESS, 0)
        context["to_verify_count"] = status_counts.get(Task.Status.TO_VERIFY, 0)
        context["done_count"] = status_counts.get(Task.Status.DONE, 0)
        context["completion_rate"] = (
            round(context["done_count"] * 100 / total_tasks) if total_tasks else 0
        )
        context["status_overview"] = [
            {
                "key": value.lower(),
                "label": label,
                "count": status_counts.get(value, 0),
                "percent": round(status_counts.get(value, 0) * 100 / total_tasks)
                if total_tasks
                else 0,
            }
            for value, label in Task.Status.choices
        ]

        context["status_labels"] = [label for _, label in Task.Status.choices]
        context["status_data"] = [status_counts.get(value, 0) for value, _ in Task.Status.choices]

        context["priority_labels"] = [label for _, label in Task.Priority.choices]
        context["priority_data"] = [priority_counts.get(value, 0) for value, _ in Task.Priority.choices]

        context.update(
            {
                "active_project_count": visible_projects.filter(status=Project.Status.ACTIVE).count(),
                "completed_project_count": visible_projects.filter(
                    status=Project.Status.COMPLETED
                ).count(),
                "period_project_count": period_project_count,
                "attention_tasks": open_tasks.filter(deadline__isnull=False)
                .select_related("project")
                .prefetch_related("assignees")
                .annotate(
                    comment_count=Count("comments", distinct=True),
                    attachment_count=Count("attachments", distinct=True),
                    priority_rank=Task.priority_rank_annotation(),
                )
                .order_by("deadline", "priority_rank")[:6],
                "recent_tasks": period_tasks.select_related("project")
                .prefetch_related("assignees")
                .annotate(
                    comment_count=Count("comments", distinct=True),
                    attachment_count=Count("attachments", distinct=True),
                )
                .order_by("-created_at")[:8],
            }
        )

        if user.is_admin_role:
            context["team_workload"] = User.objects.filter(is_active=True).annotate(
                open_task_count=Count(
                    "assigned_tasks",
                    filter=~Q(assigned_tasks__status=Task.Status.DONE),
                    distinct=True,
                ),
                overdue_task_count=Count(
                    "assigned_tasks",
                    filter=(
                        ~Q(assigned_tasks__status=Task.Status.DONE)
                        & Q(assigned_tasks__deadline__lt=now)
                    ),
                    distinct=True,
                ),
            ).order_by("-open_task_count", "name")
            context["total_users"] = User.objects.count()

        return context
