from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect


class AdminRequiredMixin(UserPassesTestMixin):
    """Allow legacy admins or users granted the view's matching CRUD permission."""

    permission_required = None

    def get_permission_required(self):
        if self.permission_required:
            return self.permission_required
        model = getattr(self, "model", None)
        if model is None:
            return None
        class_name = type(self).__name__.lower()
        action = "view"
        if "create" in class_name:
            action = "add"
        elif "update" in class_name or "archive" in class_name or "reset" in class_name:
            action = "change"
        elif "delete" in class_name:
            action = "delete"
        return f"{model._meta.app_label}.{action}_{model._meta.model_name}"

    def test_func(self):
        user = self.request.user
        permission = self.get_permission_required()
        return user.is_authenticated and (
            user.is_admin_role or bool(permission and user.has_perm(permission))
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("accounts:login")
        messages.error(self.request, "Votre rôle ne possède pas la permission requise pour cette action.")
        return redirect("dashboard:home")
