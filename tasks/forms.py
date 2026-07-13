from django import forms
from django.db.models import Q
from django.utils import timezone

from accounts.forms import style_form_fields
from accounts.models import User
from projects.models import Project

from .models import (
    ALLOWED_ATTACHMENT_EXTENSIONS,
    Attachment,
    Comment,
    Task,
    validate_attachment_extension,
    validate_attachment_size,
)

# Feeds the file picker's `accept` attribute (a UI hint only — the real
# enforcement is the validators below, which run server-side regardless).
ATTACHMENT_ACCEPT = ",".join(f".{ext}" for ext in ALLOWED_ATTACHMENT_EXTENSIONS)


class TaskForm(forms.ModelForm):
    assignees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Utilisateurs assignés",
        help_text="Ajoutez plusieurs membres en un clic.",
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )
    deadline = forms.DateTimeField(
        required=False,
        label="Délai temporel",
        help_text="Facultatif. Laissez vide si la tâche n'a pas de délai.",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    initial_attachment = forms.FileField(
        required=False,
        validators=[validate_attachment_size, validate_attachment_extension],
        label="Joindre un fichier",
        help_text="Facultatif. JPG, JPEG, PNG, PDF, DOC/DOCX, XLS/XLSX, TXT, CSV ou SQL. Taille max : 10 Mo.",
        widget=forms.ClearableFileInput(attrs={"accept": ATTACHMENT_ACCEPT}),
    )

    class Meta:
        model = Task
        fields = ("title", "description", "status", "priority", "deadline", "project", "assignees")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        if args and args[0] and "assigned_to" in args[0] and "assignees" not in args[0]:
            data = args[0].copy()
            if hasattr(data, "setlist"):
                data.setlist("assignees", [data.get("assigned_to")])
            else:
                data["assignees"] = [data.get("assigned_to")]
            args = (data, *args[1:])
        super().__init__(*args, **kwargs)
        self.fields["assignees"].queryset = User.objects.filter(
            is_active=True
        ).order_by("name")
        available_projects = Project.objects.filter(status=Project.Status.ACTIVE)
        if self.instance and self.instance.project_id:
            available_projects = Project.objects.filter(
                Q(status=Project.Status.ACTIVE) | Q(pk=self.instance.project_id)
            )
        self.fields["project"].queryset = available_projects.order_by("name")
        self.fields["project"].required = False
        self.fields["project"].empty_label = "Sans projet"
        if self.instance and self.instance.deadline:
            self.initial["deadline"] = timezone.localtime(self.instance.deadline).strftime(
                "%Y-%m-%dT%H:%M"
            )
        style_form_fields(self)

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected = list(self.cleaned_data.get("assignees", []))
        instance.assigned_to = selected[0] if selected else None
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)
        widgets = {
            "body": forms.Textarea(attrs={"rows": 2, "placeholder": "Écrire un commentaire…"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].label = ""
        style_form_fields(self)


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ("file",)
        widgets = {
            "file": forms.ClearableFileInput(attrs={"accept": ATTACHMENT_ACCEPT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)
