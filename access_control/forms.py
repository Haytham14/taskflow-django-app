from django import forms
from django.db import transaction

from accounts.forms import style_form_fields
from accounts.models import User
from projects.models import Project

from .models import (
    EmployeeMovement,
    Habilitation,
    HabilitationAccessType,
    HabilitationAssignment,
    HabilitationItem,
    HabilitationRequest,
)


class HabilitationForm(forms.ModelForm):
    habilitation_names = forms.CharField(required=False)
    access_type_names = forms.CharField(required=False)

    class Meta:
        model = Habilitation
        fields = (
            "application",
            "habilitation_names",
            "access_type_names",
            "responsible",
            "status",
        )
        labels = {
            "application": "Application",
            "responsible": "Responsable",
            "status": "Statut",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = User.objects.filter(is_active=True).order_by("name")
        self.fields["responsible"].required = False
        self.fields["responsible"].empty_label = "Aucun responsable"
        style_form_fields(self)
        self.fields["habilitation_names"].widget.attrs["class"] = "input"
        self.fields["access_type_names"].widget.attrs["class"] = "input"

    @property
    def habilitation_values(self):
        if self.is_bound:
            return self._submitted_habilitation_names()
        if self.instance.pk:
            return list(self.instance.items.values_list("name", flat=True))
        return [""]

    def _submitted_habilitation_names(self):
        if hasattr(self.data, "getlist"):
            values = self.data.getlist("habilitation_names")
        else:
            values = self.data.get("habilitation_names", [])
            if isinstance(values, str):
                values = [values]
        return [value.strip() for value in values if value.strip()]

    def clean_habilitation_names(self):
        names = self._submitted_habilitation_names()
        unique_names = list(dict.fromkeys(names))
        if not unique_names:
            raise forms.ValidationError("Ajoutez au moins une habilitation.")
        return unique_names

    @property
    def access_type_values(self):
        if self.is_bound:
            return self._submitted_values("access_type_names")
        if self.instance.pk:
            return list(self.instance.access_types.values_list("name", flat=True))
        return [""]

    def _submitted_values(self, field_name):
        if hasattr(self.data, "getlist"):
            values = self.data.getlist(field_name)
        else:
            values = self.data.get(field_name, [])
            if isinstance(values, str):
                values = [values]
        return [value.strip() for value in values if value.strip()]

    def clean_access_type_names(self):
        names = list(dict.fromkeys(self._submitted_values("access_type_names")))
        if not names:
            raise forms.ValidationError("Ajoutez au moins un type d'acces.")
        return names

    @transaction.atomic
    def save(self, commit=True):
        application = super().save(commit=commit)
        if commit:
            application.items.all().delete()
            HabilitationItem.objects.bulk_create(
                [
                    HabilitationItem(application=application, name=name, position=index)
                    for index, name in enumerate(self.cleaned_data["habilitation_names"])
                ]
            )
            application.access_types.all().delete()
            HabilitationAccessType.objects.bulk_create(
                [
                    HabilitationAccessType(
                        application=application,
                        name=name,
                        position=index,
                    )
                    for index, name in enumerate(
                        self.cleaned_data["access_type_names"]
                    )
                ]
            )
        return application


class HabilitationRequestForm(forms.ModelForm):
    submit_action = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = HabilitationRequest
        fields = (
            "requester",
            "habilitation",
            "requested_habilitations",
            "requested_access_type",
            "urgency",
            "project",
            "requested_start_date",
            "requested_end_date",
            "justification",
            "attachment",
        )
        labels = {
            "requester": "Collaborateur",
            "habilitation": "Application",
            "requested_habilitations": "Habilitations demandees",
            "requested_access_type": "Type d'acces",
            "urgency": "Urgence",
            "project": "Projet concerne",
            "requested_start_date": "Date de debut souhaitee",
            "requested_end_date": "Date de fin souhaitee",
            "attachment": "Piece jointe",
        }
        help_texts = {
            "requested_end_date": "Optionnelle. La duree sera calculee automatiquement.",
        }
        widgets = {
            "justification": forms.Textarea(attrs={"rows": 4}),
            "requested_habilitations": forms.CheckboxSelectMultiple(),
            "requested_start_date": forms.DateInput(attrs={"type": "date"}),
            "requested_end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requester"].queryset = User.objects.filter(is_active=True).order_by("name")
        self.fields["habilitation"].queryset = Habilitation.objects.filter(
            status=Habilitation.Status.ACTIVE
        ).order_by("application")
        application_id = None
        if self.is_bound:
            application_id = self.data.get("habilitation")
        elif self.instance.pk:
            application_id = self.instance.habilitation_id
        else:
            initial_application = self.initial.get("habilitation")
            application_id = getattr(initial_application, "pk", initial_application)

        if application_id:
            self.fields["requested_habilitations"].queryset = HabilitationItem.objects.filter(
                application_id=application_id
            ).order_by("position", "name")
            self.fields["requested_access_type"].queryset = HabilitationAccessType.objects.filter(
                application_id=application_id
            ).order_by("position", "name")
        else:
            self.fields["requested_habilitations"].queryset = HabilitationItem.objects.none()
            self.fields["requested_access_type"].queryset = HabilitationAccessType.objects.none()
        self.fields["project"].queryset = Project.objects.all().order_by("name")
        self.fields["project"].required = False
        self.fields["project"].empty_label = "Aucun projet"
        self.fields["requested_end_date"].required = False
        self.fields["attachment"].required = False
        style_form_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("requested_start_date")
        end_date = cleaned_data.get("requested_end_date")
        application = cleaned_data.get("habilitation")
        requested_habilitations = cleaned_data.get("requested_habilitations")
        requested_access_type = cleaned_data.get("requested_access_type")

        if application and requested_habilitations:
            invalid_habilitations = requested_habilitations.exclude(
                application=application
            )
            if invalid_habilitations.exists():
                self.add_error(
                    "requested_habilitations",
                    "Selectionnez uniquement les habilitations de cette application.",
                )
        if (
            application
            and requested_access_type
            and requested_access_type.application_id != application.pk
        ):
            self.add_error(
                "requested_access_type",
                "Selectionnez un type d'acces disponible pour cette application.",
            )
        if start_date and end_date and end_date < start_date:
            self.add_error(
                "requested_end_date",
                "La date de fin doit etre posterieure ou egale a la date de debut.",
            )
        return cleaned_data


class WorkflowActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ("approve", "Approuver"),
            ("reject", "Refuser"),
            ("request_info", "Demander information"),
            ("grant", "Attribuer l'acces"),
            ("revoke", "Revoquer"),
            ("renew", "Renouveler"),
        ),
        widget=forms.HiddenInput(),
    )
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Commentaire"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)


class EmployeeMovementForm(forms.ModelForm):
    class Meta:
        model = EmployeeMovement
        fields = (
            "user",
            "movement_type",
            "old_department",
            "new_department",
            "old_position",
            "new_position",
            "effective_date",
            "status",
            "justification",
        )
        widgets = {
            "effective_date": forms.DateInput(attrs={"type": "date"}),
            "justification": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(is_active=True).order_by("name")
        style_form_fields(self)


class HabilitationAssignmentForm(forms.ModelForm):
    class Meta:
        model = HabilitationAssignment
        fields = (
            "user",
            "habilitation",
            "start_date",
            "end_date",
            "status",
            "granted_by",
            "revoked_by",
            "revoked_reason",
        )
        labels = {
            "user": "Collaborateur",
            "habilitation": "Application",
            "start_date": "Date de debut",
            "end_date": "Date de fin",
            "status": "Statut",
            "granted_by": "Accorde par",
            "revoked_by": "Revoque par",
            "revoked_reason": "Motif de revocation",
        }
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "revoked_reason": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_users = User.objects.filter(is_active=True).order_by("name")
        self.fields["user"].queryset = active_users
        self.fields["habilitation"].queryset = Habilitation.objects.order_by("application")
        self.fields["granted_by"].queryset = active_users
        self.fields["revoked_by"].queryset = active_users
        self.fields["end_date"].required = False
        self.fields["granted_by"].required = False
        self.fields["revoked_by"].required = False
        self.fields["revoked_reason"].required = False
        style_form_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error(
                "end_date",
                "La date de fin doit etre posterieure ou egale a la date de debut.",
            )
        return cleaned_data
