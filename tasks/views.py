import json
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import CreateView, DeleteView, UpdateView

from accounts.mixins import AdminRequiredMixin
from accounts.models import User
from projects.models import Project

from .forms import AttachmentForm, CommentForm, TaskForm
from .models import Attachment, Comment, Task
from .utils import resolve_date_range


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _can_access_task(user, task):
    """Admins can access any task; members need assignment or project membership."""
    if user.is_admin_role or task.is_assigned_to(user):
        return True
    if task.project_id:
        return task.project.members.filter(pk=user.pk).exists()
    return False


def _visible_tasks(user):
    tasks = Task.objects.all()
    if user.is_admin_role:
        return tasks
    return tasks.filter(Q(assignees=user) | Q(project__members=user)).distinct()


def _safe_next_url(request, default):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default


def _redirect_after_status_update(request):
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("tasks:board")


def _status_change_error(user, task, new_status):
    valid_statuses = {value for value, _ in Task.Status.choices}
    if new_status not in valid_statuses:
        return "Statut invalide."
    if not user.is_admin_role and not task.is_assigned_to(user):
        return "Vous ne pouvez modifier que vos propres tâches."
    if not user.is_admin_role:
        if task.status in Task.LOCKED_FOR_MEMBERS:
            return "Cette tâche est verrouillée en attente de vérification par un administrateur."
        if new_status == Task.Status.DONE:
            return "Seul un administrateur peut marquer une tâche comme Terminée."
    return None


@login_required
@require_http_methods(["GET"])
def confirm_task_status(request, pk):
    task = get_object_or_404(Task, pk=pk)
    new_status = request.GET.get("status", "")
    next_url = _safe_next_url(request, str(reverse_lazy("tasks:board")))
    error = _status_change_error(request.user, task, new_status)
    if error:
        messages.error(request, error)
        return redirect(next_url)
    if task.status == new_status:
        return redirect(next_url)

    status_labels = dict(Task.Status.choices)
    if new_status == Task.Status.TO_VERIFY:
        explanation = "Après l'envoi, la tâche sera verrouillée pour le membre jusqu'à sa validation par un administrateur."
    elif new_status == Task.Status.DONE:
        explanation = "La tâche sera marquée comme terminée."
    elif task.status in Task.LOCKED_FOR_MEMBERS:
        explanation = "Cette tâche est actuellement verrouillée. Confirmez son déplacement vers le nouveau statut."
    else:
        explanation = "Confirmez le changement de statut de cette tâche."

    return render(
        request,
        "tasks/task_status_confirm.html",
        {
            "task": task,
            "new_status": new_status,
            "new_status_label": status_labels[new_status],
            "next_url": next_url,
            "explanation": explanation,
        },
    )


class BoardView(LoginRequiredMixin, View):
    template_name = "tasks/board.html"

    def get(self, request):
        tasks = (
            Task.objects.select_related("assigned_to", "created_by", "project").prefetch_related("assignees")
            .annotate(
                # distinct=True avoids double-counting from the join fan-out
                # that happens when annotating two separate reverse relations.
                comment_count=Count("comments", distinct=True),
                attachment_count=Count("attachments", distinct=True),
                priority_rank=Task.priority_rank_annotation(),
            )
            .order_by("priority_rank", "-created_at")
        )
        if not request.user.is_admin_role:
            tasks = tasks.filter(assignees=request.user)

        active_range, range_start, range_end, start_dt, end_dt = resolve_date_range(request)
        tasks = tasks.filter(created_at__range=(start_dt, end_dt))

        context = {
            "columns": [
                {
                    "key": Task.Status.TODO,
                    "label": "À faire",
                    "tasks": tasks.filter(status=Task.Status.TODO),
                },
                {
                    "key": Task.Status.IN_PROGRESS,
                    "label": "En cours",
                    "tasks": tasks.filter(status=Task.Status.IN_PROGRESS),
                },
                {
                    "key": Task.Status.TO_VERIFY,
                    "label": "À vérifier",
                    "tasks": tasks.filter(status=Task.Status.TO_VERIFY),
                },
                {
                    "key": Task.Status.DONE,
                    "label": "Terminé",
                    "tasks": tasks.filter(status=Task.Status.DONE),
                },
            ],
            "status_choices": Task.Status.choices,
            "active_range": active_range,
            "range_start": range_start,
            "range_end": range_end,
        }
        return render(request, self.template_name, context)


def _attach_initial_file(task, form, user):
    """Turn TaskForm's optional `initial_attachment` field into a real Attachment row."""
    uploaded_file = form.cleaned_data.get("initial_attachment")
    if uploaded_file:
        Attachment.objects.create(
            task=task,
            uploaded_by=user,
            file=uploaded_file,
            original_name=uploaded_file.name,
        )


class TaskCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("tasks:board")

    def get_initial(self):
        initial = super().get_initial()
        deadline = parse_datetime(self.request.GET.get("deadline", ""))
        if deadline:
            if timezone.is_naive(deadline):
                deadline = timezone.make_aware(deadline, timezone.get_current_timezone())
            initial["deadline"] = deadline
        return initial

    def get_success_url(self):
        return _safe_next_url(self.request, str(self.success_url))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = _safe_next_url(self.request, str(self.success_url))
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        _attach_initial_file(self.object, form, self.request.user)
        messages.success(self.request, "Tâche créée.")
        return response


class TaskUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("tasks:board")

    def get_success_url(self):
        return _safe_next_url(self.request, str(self.success_url))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = _safe_next_url(self.request, str(self.success_url))
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        _attach_initial_file(self.object, form, self.request.user)
        messages.success(self.request, "Tâche mise à jour.")
        return response


class TaskDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Task
    template_name = "tasks/task_confirm_delete.html"
    success_url = reverse_lazy("tasks:board")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Tâche supprimée.")
        return super().delete(request, *args, **kwargs)


@login_required
@require_POST
def update_task_status(request, pk):
    """Move a task between columns.

    Members may only move their own tasks, and only while those tasks are
    still in À faire/En cours. Once a task reaches À vérifier or Terminé,
    it's locked — from that point on, only an admin can change its status
    (that's what "verifying" a task means here), and a member can never set
    a task directly to Terminé themselves.
    """
    task = get_object_or_404(Task, pk=pk)

    new_status = request.POST.get("status")
    error = _status_change_error(request.user, task, new_status)
    if error:
        if _is_ajax(request):
            status_code = 400 if error == "Statut invalide." else 403
            return JsonResponse({"ok": False, "error": error}, status=status_code)
        messages.error(request, error)
        return _redirect_after_status_update(request)

    task.status = new_status
    task.save(update_fields=["status", "updated_at"])

    if _is_ajax(request):
        return JsonResponse({"ok": True, "status": task.status, "status_display": task.get_status_display()})

    messages.success(request, f'« {task.title} » déplacée vers {task.get_status_display()}.')
    return _redirect_after_status_update(request)


class TaskDetailView(LoginRequiredMixin, View):
    """Full task view with description, comments, and file attachments."""

    template_name = "tasks/task_detail.html"

    def get(self, request, pk):
        task = get_object_or_404(
            Task.objects.select_related("assigned_to", "created_by", "project").prefetch_related("assignees"),
            pk=pk,
        )
        if not _can_access_task(request.user, task):
            messages.error(request, "Vous n'avez pas accès à cette tâche.")
            return redirect("tasks:board")

        context = {
            "task": task,
            "comments": task.comments.select_related("author"),
            "attachments": task.attachments.select_related("uploaded_by"),
            "comment_form": CommentForm(),
            "attachment_form": AttachmentForm(),
        }
        return render(request, self.template_name, context)


class TaskCalendarView(LoginRequiredMixin, View):
    template_name = "tasks/calendar.html"

    def get(self, request):
        visible = _visible_tasks(request.user)
        project_ids = visible.exclude(project=None).values_list("project_id", flat=True)
        assignee_ids = visible.values_list("assignees__id", flat=True)
        return render(
            request,
            self.template_name,
            {
                "projects": Project.objects.filter(pk__in=project_ids).order_by("name").distinct(),
                "assignees": User.objects.filter(pk__in=assignee_ids).order_by("name").distinct(),
                "priority_choices": Task.Priority.choices,
                "status_choices": Task.Status.choices,
            },
        )


def _calendar_date(value, fallback):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def _calendar_user_payload(user):
    if not user:
        return None
    parts = (user.name or user.email).split()
    return {
        "id": user.pk,
        "name": user.name,
        "initials": "".join(part[0] for part in parts[:2]).upper(),
    }


def _calendar_task_payload(task, event_type="due"):
    occurrence = task.created_at if event_type == "created" else task.deadline
    occurrence = timezone.localtime(occurrence) if occurrence else None
    is_all_day = bool(
        event_type == "due" and occurrence and occurrence.time() == time.min
    )
    return {
        "id": task.pk,
        "occurrence_id": f"{event_type}-{task.pk}",
        "event_type": event_type,
        "event_label": "Créée" if event_type == "created" else "Échéance",
        "title": task.title,
        "start": occurrence.isoformat() if occurrence else None,
        "end": (
            (occurrence + timedelta(hours=1)).isoformat()
            if occurrence and not is_all_day else None
        ),
        "is_all_day": is_all_day,
        "priority": task.priority,
        "priority_label": task.get_priority_display(),
        "status": task.status,
        "status_label": task.get_status_display(),
        "assignee": _calendar_user_payload(task.assignees.first()),
        "assignees": [_calendar_user_payload(user) for user in task.assignees.all()],
        "project": (
            {"id": task.project_id, "name": task.project.name}
            if task.project_id else None
        ),
        "attachment_count": task.attachment_count,
        "detail_url": f"/tasks/{task.pk}/",
    }


def _apply_calendar_filters(tasks, request):
    search = request.GET.get("search", "").strip()
    if search:
        tasks = tasks.filter(
            Q(title__icontains=search)
            | Q(project__name__icontains=search)
            | Q(assignees__name__icontains=search)
        )
    for parameter, field in {
        "project": "project_id",
        "assignee": "assignees__id",
        "priority": "priority",
        "status": "status",
    }.items():
        value = request.GET.get(parameter, "").strip()
        if value:
            tasks = tasks.filter(**{field: value})
    return tasks


@login_required
@require_http_methods(["GET"])
def task_calendar_api(request):
    today = timezone.localdate()
    period_start = _calendar_date(request.GET.get("start"), today)
    period_end = _calendar_date(request.GET.get("end"), period_start)
    if period_end < period_start:
        return JsonResponse({"error": "La date de fin doit suivre la date de début."}, status=400)
    if (period_end - period_start).days > 42:
        return JsonResponse({"error": "La période demandée est trop longue."}, status=400)

    current_timezone = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(period_start, time.min), current_timezone)
    end_dt = timezone.make_aware(
        datetime.combine(period_end + timedelta(days=1), time.min),
        current_timezone,
    )
    visible = _apply_calendar_filters(
        _visible_tasks(request.user).select_related("assigned_to", "project").prefetch_related("assignees"),
        request,
    )
    period_tasks = (
        visible.filter(
            Q(created_at__gte=start_dt, created_at__lt=end_dt)
            | Q(deadline__gte=start_dt, deadline__lt=end_dt)
        )
        .annotate(attachment_count=Count("attachments", distinct=True))
        .order_by("title")
        .distinct()
    )
    without_due = visible.filter(deadline__isnull=True).order_by("-created_at")
    statistics = {
        "total": period_tasks.count(),
        "overdue": period_tasks.filter(deadline__lt=timezone.now())
        .exclude(status=Task.Status.DONE)
        .count(),
        "completed": period_tasks.filter(status=Task.Status.DONE).count(),
        "without_due_date": without_due.count(),
    }
    occurrences = []
    for task in period_tasks:
        if start_dt <= task.created_at < end_dt:
            occurrences.append(_calendar_task_payload(task, "created"))
        if task.deadline and start_dt <= task.deadline < end_dt:
            occurrences.append(_calendar_task_payload(task, "due"))
    occurrences.sort(key=lambda occurrence: (occurrence["start"], occurrence["title"]))
    return JsonResponse(
        {
            "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
            "statistics": statistics,
            "tasks": occurrences,
            "without_due_tasks": [
                {
                    "id": task.pk,
                    "title": task.title,
                    "priority_label": task.get_priority_display(),
                    "detail_url": f"/tasks/{task.pk}/",
                }
                for task in without_due[:100]
            ],
        }
    )


@login_required
@require_http_methods(["PATCH"])
def update_calendar_position(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not request.user.is_admin_role:
        return JsonResponse(
            {"ok": False, "error": "Vous n’avez pas l’autorisation de déplacer cette tâche."},
            status=403,
        )
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Données invalides."}, status=400)

    start = parse_datetime(data.get("start", ""))
    end = parse_datetime(data.get("end", "")) if data.get("end") else None
    if not start:
        return JsonResponse({"ok": False, "error": "La date de début est obligatoire."}, status=400)
    if timezone.is_naive(start):
        start = timezone.make_aware(start, timezone.get_current_timezone())
    if end and timezone.is_naive(end):
        end = timezone.make_aware(end, timezone.get_current_timezone())
    if end and start >= end:
        return JsonResponse(
            {"ok": False, "error": "La date de début doit précéder la date de fin."},
            status=400,
        )

    task.deadline = start
    task.save(update_fields=["deadline", "updated_at"])
    task = (
        Task.objects.select_related("assigned_to", "project").prefetch_related("assignees")
        .annotate(attachment_count=Count("attachments", distinct=True))
        .get(pk=task.pk)
    )
    return JsonResponse({"ok": True, "task": _calendar_task_payload(task, "due")})


@login_required
@require_POST
def add_comment(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _can_access_task(request.user, task):
        messages.error(request, "Vous n'avez pas accès à cette tâche.")
        return redirect("tasks:board")

    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        comment.save()
        messages.success(request, "Commentaire ajouté.")
    else:
        messages.error(request, "Ce commentaire n'a pas pu être publié — veuillez réessayer.")
    return redirect("tasks:task_detail", pk=task.pk)


@login_required
@require_POST
def delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    if not (request.user.is_admin_role or comment.author_id == request.user.id):
        messages.error(request, "Vous ne pouvez supprimer que vos propres commentaires.")
        return redirect("tasks:task_detail", pk=comment.task_id)

    task_id = comment.task_id
    comment.delete()
    messages.success(request, "Commentaire supprimé.")
    return redirect("tasks:task_detail", pk=task_id)


@login_required
@require_POST
def add_attachment(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _can_access_task(request.user, task):
        messages.error(request, "Vous n'avez pas accès à cette tâche.")
        return redirect("tasks:board")

    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.task = task
        attachment.uploaded_by = request.user
        attachment.original_name = form.cleaned_data["file"].name
        attachment.save()
        messages.success(request, "Fichier joint.")
    else:
        errors = form.errors.get("file") or ["Le fichier n'a pas pu être joint."]
        for error in errors:
            messages.error(request, error)
    return redirect("tasks:task_detail", pk=task.pk)


@login_required
@require_POST
def delete_attachment(request, pk):
    attachment = get_object_or_404(Attachment, pk=pk)
    if not (request.user.is_admin_role or attachment.uploaded_by_id == request.user.id):
        messages.error(request, "Vous ne pouvez supprimer que les fichiers que vous avez téléversés.")
        return redirect("tasks:task_detail", pk=attachment.task_id)

    task_id = attachment.task_id
    attachment.file.delete(save=False)
    attachment.delete()
    messages.success(request, "Pièce jointe supprimée.")
    return redirect("tasks:task_detail", pk=task_id)


@login_required
def download_attachment(request, pk):
    """Serve the file only to users who can access the parent task.

    Files are intentionally NOT exposed under MEDIA_URL for direct/public
    access — every download is checked against the same admin-or-assignee
    rule as the rest of the task.
    """
    attachment = get_object_or_404(Attachment, pk=pk)
    if not _can_access_task(request.user, attachment.task):
        return HttpResponseForbidden("Vous n'avez pas accès à ce fichier.")

    filename = attachment.original_name or attachment.file.name.rsplit("/", 1)[-1]
    return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=filename)
