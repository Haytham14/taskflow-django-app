from django.contrib import messages
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import (
    AppRoleForm,
    DepartmentForm,
    ProfileForm,
    UserCreateForm,
    UserUpdateForm,
    style_form_fields,
)
from .mixins import AdminRequiredMixin
from .models import AppRole, Department, User


PERMISSION_MODULE_LABELS = {
    "accounts": "Utilisateurs et rôles",
    "tasks": "Tâches",
    "projects": "Projets et chat équipe",
    "chat": "Messagerie en temps réel",
    "access_control": "Gestion des habilitations",
    "documents": "Gestion documentaire",
}

PERMISSION_ACTION_DETAILS = {
    "view": "Consulter les éléments et leurs détails.",
    "add": "Créer de nouveaux éléments.",
    "change": "Modifier les éléments existants.",
    "delete": "Supprimer définitivement des éléments.",
}


def role_permission_groups(form):
    if form.is_bound:
        selected_ids = {str(value) for value in form.data.getlist("permissions")}
    elif form.instance.pk:
        selected_ids = {str(value) for value in form.instance.permissions.values_list("pk", flat=True)}
    else:
        selected_ids = set()

    grouped = {}
    for permission in form.fields["permissions"].queryset:
        app_label = permission.content_type.app_label
        model_class = permission.content_type.model_class()
        model_label = (
            str(model_class._meta.verbose_name_plural).capitalize()
            if model_class else permission.content_type.model.replace("_", " ").capitalize()
        )
        action = permission.codename.split("_", 1)[0]
        action_label = {
            "view": "Consulter",
            "add": "Créer",
            "change": "Modifier",
            "delete": "Supprimer",
        }.get(action, permission.name)
        group = grouped.setdefault(
            app_label,
            {"key": app_label, "label": PERMISSION_MODULE_LABELS.get(app_label, app_label), "permissions": []},
        )
        group["permissions"].append(
            {
                "id": permission.pk,
                "code": f"{app_label}.{permission.codename}",
                "action": action_label,
                "model": model_label,
                "detail": PERMISSION_ACTION_DETAILS.get(action, permission.name),
                "selected": str(permission.pk) in selected_ids,
            }
        )
    return list(grouped.values())


class RoleListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = AppRole
    template_name = "accounts/role_list.html"
    context_object_name = "roles"

    def get_queryset(self):
        return AppRole.objects.annotate(
            user_count=Count("users", distinct=True),
            permission_count=Count("permissions", distinct=True),
        ).order_by("-is_system", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_roles"] = self.get_queryset().count()
        context["assigned_roles"] = self.get_queryset().filter(user_count__gt=0).count()
        context["total_permissions"] = sum(role.permission_count for role in context["roles"])
        return context


class RoleFormMixin(LoginRequiredMixin, AdminRequiredMixin):
    model = AppRole
    form_class = AppRoleForm
    template_name = "accounts/role_form.html"
    success_url = reverse_lazy("user_roles")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["permission_groups"] = role_permission_groups(context["form"])
        return context


class RoleCreateView(RoleFormMixin, CreateView):
    def form_valid(self, form):
        messages.success(self.request, "Rôle créé avec ses permissions.")
        return super().form_valid(form)


class RoleUpdateView(RoleFormMixin, UpdateView):
    def form_valid(self, form):
        messages.success(self.request, "Rôle et permissions mis à jour.")
        return super().form_valid(form)


class RoleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = AppRole
    template_name = "accounts/role_confirm_delete.html"
    success_url = reverse_lazy("user_roles")

    def form_valid(self, form):
        affected_users = self.object.users.count()
        messages.success(
            self.request,
            f"Rôle supprimé. {affected_users} utilisateur(s) n'ont désormais plus cette attribution.",
        )
        return super().form_valid(form)


class RolePermissionsView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = "accounts/role_permissions.html"
    permission_required = "accounts.view_approle"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module_keys = list(PERMISSION_MODULE_LABELS)
        roles = AppRole.objects.prefetch_related("permissions__content_type", "users").all()
        profiles = []
        for role in roles:
            permissions = list(role.permissions.all())
            granted_apps = {permission.content_type.app_label for permission in permissions}
            profiles.append(
                {
                    "role": role,
                    "grants": [key in granted_apps for key in module_keys],
                    "permissions": permissions,
                    "users": role.users.count(),
                }
            )
        context["modules"] = [PERMISSION_MODULE_LABELS[key] for key in module_keys]
        context["profiles"] = profiles
        context["total_profiles"] = len(profiles)
        context["total_permissions"] = sum(len(profile["permissions"]) for profile in profiles)
        context["total_users"] = User.objects.count()
        return context


class DepartmentListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Department
    template_name = "accounts/department_list.html"
    context_object_name = "departments"
    permission_required = "accounts.view_department"

    def get_queryset(self):
        return Department.objects.select_related("manager").annotate(member_count=Count("members"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_departments"] = len(context["departments"])
        context["active_departments"] = sum(1 for item in context["departments"] if item.is_active)
        context["covered_users"] = sum(item.member_count for item in context["departments"])
        return context


class DepartmentFormMixin(LoginRequiredMixin, AdminRequiredMixin):
    model = Department
    form_class = DepartmentForm
    template_name = "accounts/department_form.html"
    success_url = reverse_lazy("user_departments")


class DepartmentCreateView(DepartmentFormMixin, CreateView):
    def form_valid(self, form):
        messages.success(self.request, "Service créé.")
        return super().form_valid(form)


class DepartmentUpdateView(DepartmentFormMixin, UpdateView):
    def form_valid(self, form):
        messages.success(self.request, "Service mis à jour.")
        return super().form_valid(form)


class DepartmentDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Department
    template_name = "accounts/department_confirm_delete.html"
    success_url = reverse_lazy("user_departments")

    def form_valid(self, form):
        messages.success(self.request, "Service supprimé. Les comptes utilisateurs restent actifs.")
        return super().form_valid(form)


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = "accounts/profile_settings.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Votre profil a été mis à jour.")
        return super().form_valid(form)


class ProfilePasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = "accounts/profile_password.html"
    success_url = reverse_lazy("accounts:profile")

    def get_form(self, form_class=None):
        return style_form_fields(super().get_form(form_class))

    def form_valid(self, form):
        messages.success(self.request, "Votre mot de passe a été modifié.")
        return super().form_valid(form)


class UserListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    def get_queryset(self):
        queryset = User.objects.select_related("custom_role", "department").order_by("name")
        query = self.request.GET.get("q", "").strip()
        role = self.request.GET.get("role", "").strip()
        department = self.request.GET.get("department", "").strip()
        status = self.request.GET.get("status", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(email__icontains=query))
        if role:
            queryset = queryset.filter(custom_role_id=role)
        if department:
            queryset = queryset.filter(department_id=department)
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["roles"] = AppRole.objects.all()
        context["departments"] = Department.objects.all()
        context["active_users"] = User.objects.filter(is_active=True).count()
        context["total_users"] = User.objects.count()
        context["unassigned_users"] = User.objects.filter(custom_role=None).count()
        return context


class UserCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        messages.success(self.request, "Utilisateur créé.")
        return super().form_valid(form)


class UserUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        messages.success(self.request, "Utilisateur mis à jour.")
        return super().form_valid(form)


class UserDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = User
    template_name = "accounts/user_confirm_delete.html"
    success_url = reverse_lazy("accounts:user_list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Utilisateur supprimé.")
        return super().delete(request, *args, **kwargs)


class UserPasswordResetView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Lets an admin set a new password for another user."""

    template_name = "accounts/user_password_form.html"
    permission_required = "accounts.change_user"

    def get(self, request, pk):
        target_user = get_object_or_404(User, pk=pk)
        form = style_form_fields(SetPasswordForm(target_user))
        return render(request, self.template_name, {"form": form, "target_user": target_user})

    def post(self, request, pk):
        target_user = get_object_or_404(User, pk=pk)
        form = style_form_fields(SetPasswordForm(target_user, request.POST))
        if form.is_valid():
            form.save()
            messages.success(request, f"Mot de passe mis à jour pour {target_user.name}.")
            return redirect("accounts:user_list")
        return render(request, self.template_name, {"form": form, "target_user": target_user})
