from django import forms
from django.contrib.auth.forms import AuthenticationForm as BaseAuthenticationForm
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from django.contrib.auth.forms import UserCreationForm

from django.contrib.auth.models import Permission

from .models import AppRole, Department, User


def style_form_fields(form):
    """Add a shared CSS class to every widget so templates stay simple."""
    for field in form.fields.values():
        existing = field.widget.attrs.get("class", "")
        css_class = "select" if isinstance(field.widget, forms.Select) else "input"
        field.widget.attrs["class"] = f"{existing} {css_class}".strip()
    return form


class LoginForm(BaseAuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)


class UserCreateForm(UserCreationForm):
    """Used by the in-app 'Add user' page. Handles password hashing."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("name", "email", "role", "custom_role", "department")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].label = "Fonction métier"
        self.fields["role"].help_text = "Utilisée dans les circuits de validation des habilitations."
        self.fields["custom_role"].help_text = "Détermine précisément les permissions dans l'application."
        style_form_fields(self)

    def save(self, commit=True):
        user = super().save(commit=False)
        selected = self.cleaned_data.get("custom_role")
        if selected and selected.system_key:
            user.role = selected.system_key
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserUpdateForm(forms.ModelForm):
    """Used by the in-app 'Edit user' page. Password is changed separately."""

    class Meta:
        model = User
        fields = ("name", "email", "role", "custom_role", "department", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].label = "Fonction métier"
        self.fields["role"].help_text = "Utilisée dans les circuits de validation des habilitations."
        self.fields["custom_role"].help_text = "Détermine précisément les permissions dans l'application."
        style_form_fields(self)

    def save(self, commit=True):
        user = super().save(commit=False)
        selected = self.cleaned_data.get("custom_role")
        if selected and selected.system_key:
            user.role = selected.system_key
        if commit:
            user.save()
            self.save_m2m()
        return user


class ProfileForm(forms.ModelForm):
    """Personal settings that a signed-in user may update safely."""

    class Meta:
        model = User
        fields = ("name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)


class AppRoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Permissions du rôle",
    )

    class Meta:
        model = AppRole
        fields = ("name", "description", "permissions")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = Permission.objects.filter(
            content_type__app_label__in=(
                "accounts", "tasks", "projects", "chat", "access_control", "documents"
            )
        ).select_related("content_type").order_by("content_type__app_label", "content_type__model", "codename")
        style_form_fields(self)


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("name", "code", "description", "manager", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = User.objects.filter(is_active=True).order_by("name")
        self.fields["manager"].required = False
        self.fields["manager"].empty_label = "Aucun responsable"
        style_form_fields(self)


class AdminUserChangeForm(BaseUserChangeForm):
    """Used only by the built-in Django admin site (/admin/)."""

    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = ("email", "password", "name", "role", "is_active", "is_staff", "is_superuser")
