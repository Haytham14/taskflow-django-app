from django import forms

from accounts.forms import style_form_fields
from accounts.models import User
from tasks.models import validate_attachment_extension, validate_attachment_size

from .models import Document


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ("title", "file", "category", "service", "status")
        labels = {
            "title": "Nom du document",
            "file": "Fichier",
            "category": "Categorie",
            "service": "Service",
            "status": "Statut",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].validators = [
            validate_attachment_size,
            validate_attachment_extension,
        ]
        if self.instance.pk:
            self.fields["file"].required = False
        style_form_fields(self)


class DocumentFilterForm(forms.Form):
    query = forms.CharField(required=False, label="", widget=forms.TextInput())
    source = forms.ChoiceField(required=False, label="")
    category = forms.ChoiceField(required=False, label="")
    file_type = forms.CharField(required=False, label="")
    service = forms.CharField(required=False, label="")
    uploaded_by = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="",
    )
    status = forms.ChoiceField(required=False, label="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["query"].widget.attrs["placeholder"] = "Rechercher par nom..."
        self.fields["source"].choices = [("", "Toutes les sources")] + list(
            Document.SourceModule.choices
        )
        self.fields["category"].choices = [("", "Toutes les categories")] + list(
            Document.Category.choices
        )
        self.fields["file_type"].widget.attrs["placeholder"] = "Type de fichier"
        self.fields["service"].widget.attrs["placeholder"] = "Service"
        self.fields["uploaded_by"].queryset = User.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["uploaded_by"].empty_label = "Tous les utilisateurs"
        self.fields["status"].choices = [("", "Tous les statuts")] + list(
            Document.Status.choices
        )
        style_form_fields(self)
