from django import forms

from accounts.forms import style_form_fields
from accounts.models import User
from tasks.forms import ATTACHMENT_ACCEPT
from tasks.models import validate_attachment_extension, validate_attachment_size

from .models import Project, TeamChannel, TeamMessage


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ("name", "description", "status", "members")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "members": forms.SelectMultiple(attrs={"size": 8}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].queryset = User.objects.filter(
            is_active=True,
        ).order_by("name")
        self.fields["members"].required = False
        self.fields["members"].help_text = ""
        self.fields["members"].help_text = "Maintenez Ctrl pour sélectionner plusieurs membres."
        style_form_fields(self)


class TeamMessageForm(forms.ModelForm):
    attachment = forms.FileField(
        required=False,
        validators=[validate_attachment_size, validate_attachment_extension],
        label="Joindre un fichier",
        widget=forms.ClearableFileInput(attrs={"accept": ATTACHMENT_ACCEPT}),
    )

    class Meta:
        model = TeamMessage
        fields = ("body",)
        widgets = {
            "body": forms.Textarea(attrs={"rows": 2, "placeholder": "Écrire un message..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].label = ""
        style_form_fields(self)


class TeamChannelForm(forms.ModelForm):
    class Meta:
        model = TeamChannel
        fields = ("name", "description")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].help_text = "Exemple : general, support, dev, ventes."
        style_form_fields(self)
