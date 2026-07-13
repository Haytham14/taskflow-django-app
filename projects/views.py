from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.mixins import AdminRequiredMixin
from accounts.models import User
from tasks.forms import TaskForm
from tasks.models import Task
from tasks.utils import resolve_date_range
from tasks.views import _attach_initial_file

from .forms import ProjectForm, TeamChannelForm, TeamMessageForm
from .models import Project, TeamChannel, TeamMessage, TeamMessageAttachment


def _project_columns(tasks):
    return [
        {"key": Task.Status.TODO, "label": "À faire", "tasks": tasks.filter(status=Task.Status.TODO)},
        {"key": Task.Status.IN_PROGRESS, "label": "En cours", "tasks": tasks.filter(status=Task.Status.IN_PROGRESS)},
        {"key": Task.Status.TO_VERIFY, "label": "À vérifier", "tasks": tasks.filter(status=Task.Status.TO_VERIFY)},
        {"key": Task.Status.DONE, "label": "Terminé", "tasks": tasks.filter(status=Task.Status.DONE)},
    ]


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"

    def get_queryset(self):
        queryset = Project.objects.prefetch_related("members").annotate(task_count=Count("tasks"))
        if self.request.user.is_admin_role:
            return queryset.order_by("name")
        return queryset.filter(members=self.request.user).order_by("name")


class ProjectCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    success_url = reverse_lazy("projects:project_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Projet créé.")
        return super().form_valid(form)


class ProjectUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    success_url = reverse_lazy("projects:project_list")

    def form_valid(self, form):
        messages.success(self.request, "Projet mis à jour.")
        return super().form_valid(form)


class ProjectDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Project
    template_name = "projects/project_confirm_delete.html"
    success_url = reverse_lazy("projects:project_list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Projet supprimé.")
        return super().delete(request, *args, **kwargs)


class ProjectBoardView(LoginRequiredMixin, View):
    template_name = "projects/project_board.html"

    def get(self, request, pk):
        project = get_object_or_404(Project.objects.prefetch_related("members"), pk=pk)
        if not project.can_access(request.user):
            messages.error(request, "Vous n'avez pas accès à ce projet.")
            return redirect("projects:project_list")

        tasks = (
            project.tasks.select_related("assigned_to", "created_by", "project").prefetch_related("assignees")
            .annotate(
                comment_count=Count("comments", distinct=True),
                attachment_count=Count("attachments", distinct=True),
                priority_rank=Task.priority_rank_annotation(),
            )
            .order_by("priority_rank", "-created_at")
        )
        active_range, range_start, range_end, start_dt, end_dt = resolve_date_range(request)
        tasks = tasks.filter(created_at__range=(start_dt, end_dt))

        return render(
            request,
            self.template_name,
            {
                "project": project,
                "columns": _project_columns(tasks),
                "status_choices": Task.Status.choices,
                "active_range": active_range,
                "range_start": range_start,
                "range_end": range_end,
            },
        )


class ProjectTaskCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(Project, pk=kwargs["pk"])
        if self.project.status == Project.Status.COMPLETED:
            messages.error(request, "Ce projet est terminé. Rouvrez-le avant d'ajouter une tâche.")
            return redirect("projects:project_board", pk=self.project.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial["project"] = self.project
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["project"].disabled = True
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_eyebrow"] = self.project.name
        context["form_title"] = "Nouvelle tâche de projet"
        context["cancel_url"] = reverse("projects:project_board", kwargs={"pk": self.project.pk})
        return context

    def form_valid(self, form):
        form.instance.project = self.project
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        _attach_initial_file(self.object, form, self.request.user)
        messages.success(self.request, "Tâche créée dans le projet.")
        return response

    def get_success_url(self):
        return reverse("projects:project_board", kwargs={"pk": self.project.pk})


def _default_channel(user=None):
    channel, created = TeamChannel.objects.get_or_create(
        slug="general",
        defaults={
            "name": "general",
            "description": "Le channel principal de l'équipe.",
            "created_by": user if getattr(user, "is_authenticated", False) else None,
        },
    )
    return channel


class TeamChatView(LoginRequiredMixin, View):
    template_name = "projects/team_chat.html"

    def _accessible_tasks(self, user):
        tasks = Task.objects.prefetch_related("assignees").annotate(
            priority_rank=Task.priority_rank_annotation()
        )
        if user.is_admin_role:
            return tasks.order_by("priority_rank", "-updated_at")
        return tasks.filter(Q(assignees=user) | Q(project__members=user)).distinct().order_by(
            "priority_rank", "-updated_at"
        )

    def _channel_context(self, request, slug=None, form=None):
        default_channel = _default_channel(request.user)
        channels = TeamChannel.objects.annotate(message_count=Count("messages")).order_by("name")
        active_channel = get_object_or_404(TeamChannel, slug=slug) if slug else default_channel
        active_channel_filter = Q(message__channel=active_channel)
        if active_channel.slug == "general":
            active_channel_filter = active_channel_filter | Q(message__channel__isnull=True)

        messages_query = (
            TeamMessage.objects.select_related("author", "channel")
            .prefetch_related("attachments")
            .order_by("-created_at")
        )
        if active_channel.slug == "general":
            messages_query = messages_query.filter(Q(channel=active_channel) | Q(channel__isnull=True))
        else:
            messages_query = messages_query.filter(channel=active_channel)

        direct_users = list(User.objects.filter(is_active=True).order_by("name")[:8])
        channel_members = list(User.objects.filter(is_active=True).order_by("name")[:5])
        shared_files = (
            TeamMessageAttachment.objects.select_related("message", "message__author")
            .filter(active_channel_filter)
            .order_by("-uploaded_at")[:6]
        )
        linked_tasks = self._accessible_tasks(request.user)[:2]

        return {
            "channels": channels,
            "active_channel": active_channel,
            "direct_users": direct_users,
            "channel_members": channel_members,
            "channel_avatars": channel_members[:4],
            "member_count": User.objects.filter(is_active=True).count(),
            "linked_tasks": linked_tasks,
            "shared_files": shared_files,
            "messages_list": messages_query[:100],
            "form": form or TeamMessageForm(),
        }

    def get(self, request, slug=None):
        return render(
            request,
            self.template_name,
            self._channel_context(request, slug=slug),
        )

    def post(self, request, slug=None):
        active_channel = get_object_or_404(TeamChannel, slug=slug) if slug else _default_channel(request.user)
        form = TeamMessageForm(request.POST, request.FILES)
        if form.is_valid():
            message = form.save(commit=False)
            message.channel = active_channel
            message.author = request.user
            message.save()
            uploaded_file = form.cleaned_data.get("attachment")
            if uploaded_file:
                TeamMessageAttachment.objects.create(
                    message=message,
                    file=uploaded_file,
                    original_name=uploaded_file.name,
                )
            return redirect("projects:team_chat_channel", slug=active_channel.slug)

        return render(
            request,
            self.template_name,
            self._channel_context(request, slug=slug, form=form),
        )


class TeamChannelCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = TeamChannel
    form_class = TeamChannelForm
    template_name = "projects/team_channel_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Channel créé.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("projects:team_chat_channel", kwargs={"slug": self.object.slug})


class TeamMessageAttachmentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        attachment = get_object_or_404(TeamMessageAttachment, pk=pk)
        filename = attachment.original_name or attachment.file.name.rsplit("/", 1)[-1]
        return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=filename)
