from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from accounts.models import User
from chat.models import ChatChannel, ChatChannelMember, ChatMessage
from tasks.models import Task

from .forms import (
    EmployeeMovementForm,
    HabilitationAssignmentForm,
    HabilitationForm,
    HabilitationRequestForm,
    WorkflowActionForm,
)
from .models import (
    AuditLog,
    EmployeeMovement,
    Habilitation,
    HabilitationAccessType,
    HabilitationAssignment,
    HabilitationRequest,
    HabilitationRequestStep,
)


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _audit(user, action, entity, old_value="", new_value="", request=None):
    AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        entity_type=entity.__class__.__name__,
        entity_id=str(getattr(entity, "pk", "")),
        old_value=old_value,
        new_value=new_value,
        ip_address=_client_ip(request) if request else None,
    )


class AdminRequiredMixin(UserPassesTestMixin):
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
        elif "update" in class_name or "clear" in class_name:
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


class AccessDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    template_name = "access_control/confirm_delete.html"
    blocked_message = "Suppression impossible car cet element est deja utilise."
    success_message = "Element supprime."
    audit_action = "Suppression"
    delete_kind = "element"
    cancel_url_name = None

    def get_cancel_url(self):
        if self.cancel_url_name:
            return reverse(self.cancel_url_name, args=[self.object.pk])
        return self.success_url

    def get_delete_label(self):
        return str(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["delete_kind"] = self.delete_kind
        context["delete_label"] = self.get_delete_label()
        context["cancel_url"] = self.get_cancel_url()
        return context

    def form_valid(self, form):
        self.object = self.get_object()
        try:
            _audit(self.request.user, self.audit_action, self.object, request=self.request)
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, self.blocked_message)
            return redirect(self.get_cancel_url())
        messages.success(self.request, self.success_message)
        return response


def _first_user_for_roles(*roles):
    return User.objects.filter(role__in=roles, is_active=True).order_by("name").first()


def _manager_for(access_request):
    return (
        _first_user_for_roles(User.Role.MANAGER, User.Role.ADMIN, User.Role.SYSTEM_ADMIN)
        or access_request.requester
    )


def _business_owner_for(access_request):
    return (
        access_request.habilitation.responsible
        or _first_user_for_roles(User.Role.BUSINESS_OWNER, User.Role.ADMIN, User.Role.SYSTEM_ADMIN)
        or access_request.requester
    )


def _access_admin_for():
    return _first_user_for_roles(
        User.Role.ACCESS_ADMIN, User.Role.ADMIN, User.Role.SYSTEM_ADMIN
    )


def _priority_for_criticality(criticality):
    if criticality == HabilitationRequest.Urgency.CRITICAL:
        return Task.Priority.CRITICAL
    if criticality == HabilitationRequest.Urgency.HIGH:
        return Task.Priority.HIGH
    if criticality == HabilitationRequest.Urgency.LOW:
        return Task.Priority.LOW
    return Task.Priority.MEDIUM


def _create_task_for_step(access_request, assigned_to, title):
    if not assigned_to:
        return None
    return Task.objects.create(
        title=title,
        description=(
            f"Demande {access_request.reference} - {access_request.habilitation.application}\n\n"
            f"Justification : {access_request.justification}\n\n"
            f"Ouvrir la demande : /access/requests/{access_request.pk}/"
        ),
        priority=_priority_for_criticality(access_request.urgency),
        status=Task.Status.TODO,
        assigned_to=assigned_to,
        created_by=access_request.requester,
        project=access_request.project,
        habilitation_request=access_request,
    )


def _ensure_workflow(access_request):
    if access_request.steps.exists():
        return
    HabilitationRequestStep.objects.create(
        request=access_request,
        step_name="Validation manager",
        assigned_to=_manager_for(access_request),
    )
    HabilitationRequestStep.objects.create(
        request=access_request,
        step_name="Avis responsable metier",
        assigned_to=_business_owner_for(access_request),
        status=HabilitationRequestStep.Status.WAITING,
    )
    HabilitationRequestStep.objects.create(
        request=access_request,
        step_name="Attribution administrateur",
        assigned_to=_access_admin_for(),
        status=HabilitationRequestStep.Status.WAITING,
    )


def _submit_request(access_request, user, request=None):
    _ensure_workflow(access_request)
    access_request.status = HabilitationRequest.Status.PENDING_MANAGER
    access_request.current_step = "Validation manager"
    access_request.save(update_fields=["status", "current_step", "updated_at"])
    _create_task_for_step(
        access_request,
        _manager_for(access_request),
        "Valider la demande d'habilitation",
    )
    _audit(user, "Soumission demande", access_request, new_value=access_request.status, request=request)


def _current_pending_step(access_request):
    return access_request.steps.filter(status=HabilitationRequestStep.Status.PENDING).first()


def _approve_step(access_request, user, comment="", request=None):
    step = _current_pending_step(access_request)
    if not step:
        return "Aucune etape en attente."

    step.status = HabilitationRequestStep.Status.APPROVED
    step.decision = HabilitationRequestStep.Decision.APPROVE
    step.comment = comment
    step.validated_at = timezone.now()
    step.save(update_fields=["status", "decision", "comment", "validated_at", "updated_at"])

    if access_request.status == HabilitationRequest.Status.PENDING_MANAGER:
        next_step = access_request.steps.filter(step_name="Avis responsable metier").first()
        if next_step:
            next_step.status = HabilitationRequestStep.Status.PENDING
            next_step.save(update_fields=["status", "updated_at"])
        access_request.status = HabilitationRequest.Status.PENDING_BUSINESS
        access_request.current_step = "Avis responsable metier"
        access_request.save(update_fields=["status", "current_step", "updated_at"])
        _create_task_for_step(
            access_request,
            _business_owner_for(access_request),
            "Avis metier pour demande d'habilitation",
        )
    elif access_request.status == HabilitationRequest.Status.PENDING_BUSINESS:
        next_step = access_request.steps.filter(step_name="Attribution administrateur").first()
        if next_step:
            next_step.status = HabilitationRequestStep.Status.PENDING
            next_step.save(update_fields=["status", "updated_at"])
        access_request.status = HabilitationRequest.Status.PENDING_ADMIN
        access_request.current_step = "Attribution administrateur"
        access_request.save(update_fields=["status", "current_step", "updated_at"])
        _create_task_for_step(access_request, _access_admin_for(), "Attribuer l'acces")

    _audit(user, "Validation", access_request, new_value=access_request.status, request=request)
    return ""


def _reject_step(access_request, user, comment, request=None):
    if not comment.strip():
        return "Le commentaire est obligatoire pour refuser."
    step = _current_pending_step(access_request)
    if step:
        step.status = HabilitationRequestStep.Status.REJECTED
        step.decision = HabilitationRequestStep.Decision.REJECT
        step.comment = comment
        step.validated_at = timezone.now()
        step.save(update_fields=["status", "decision", "comment", "validated_at", "updated_at"])
    access_request.status = HabilitationRequest.Status.REJECTED
    access_request.current_step = "Refusee"
    access_request.save(update_fields=["status", "current_step", "updated_at"])
    _audit(user, "Refus", access_request, new_value=comment, request=request)
    return ""


def _request_info(access_request, user, comment, request=None):
    step = _current_pending_step(access_request)
    if step:
        step.status = HabilitationRequestStep.Status.INFO_REQUESTED
        step.decision = HabilitationRequestStep.Decision.REQUEST_INFO
        step.comment = comment
        step.validated_at = timezone.now()
        step.save(update_fields=["status", "decision", "comment", "validated_at", "updated_at"])
    access_request.status = HabilitationRequest.Status.INFO_REQUESTED
    access_request.current_step = "Retour demandeur"
    access_request.save(update_fields=["status", "current_step", "updated_at"])
    _audit(user, "Demande information", access_request, new_value=comment, request=request)


def _grant_access(access_request, user, comment="", request=None):
    if access_request.status != HabilitationRequest.Status.PENDING_ADMIN:
        return "Cette demande ne peut pas etre attribuee."

    step = _current_pending_step(access_request)
    if step:
        step.status = HabilitationRequestStep.Status.APPROVED
        step.decision = HabilitationRequestStep.Decision.GRANT
        step.comment = comment
        step.validated_at = timezone.now()
        step.save(update_fields=["status", "decision", "comment", "validated_at", "updated_at"])

    assignment, _ = HabilitationAssignment.objects.get_or_create(
        user=access_request.requester,
        habilitation=access_request.habilitation,
        request=access_request,
        defaults={
            "start_date": access_request.requested_start_date,
            "end_date": access_request.requested_end_date,
            "granted_by": user,
        },
    )
    assignment.start_date = access_request.requested_start_date
    assignment.end_date = access_request.requested_end_date
    assignment.status = HabilitationAssignment.Status.ACTIVE
    assignment.granted_by = user
    assignment.save(update_fields=["start_date", "end_date", "status", "granted_by", "updated_at"])

    access_request.status = HabilitationRequest.Status.GRANTED
    access_request.current_step = "Acces attribue"
    access_request.save(update_fields=["status", "current_step", "updated_at"])
    _audit(user, "Attribution", access_request, new_value=assignment.status, request=request)
    return ""


def _revoke_access(access_request, user, comment, request=None):
    if not comment.strip():
        return "Le motif est obligatoire pour revoquer."
    access_request.assignments.filter(status=HabilitationAssignment.Status.ACTIVE).update(
        status=HabilitationAssignment.Status.REVOKED,
        revoked_by=user,
        revoked_reason=comment,
        updated_at=timezone.now(),
    )
    access_request.status = HabilitationRequest.Status.REVOKED
    access_request.current_step = "Acces revoque"
    access_request.save(update_fields=["status", "current_step", "updated_at"])
    _audit(user, "Revocation", access_request, new_value=comment, request=request)
    return ""


class AccessDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "access_control/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        requests = HabilitationRequest.objects.select_related("requester", "habilitation")
        assignments = HabilitationAssignment.objects.select_related("user", "habilitation")
        context["pending_count"] = requests.filter(
            status__in=[
                HabilitationRequest.Status.SUBMITTED,
                HabilitationRequest.Status.PENDING_MANAGER,
                HabilitationRequest.Status.PENDING_BUSINESS,
                HabilitationRequest.Status.PENDING_ADMIN,
                HabilitationRequest.Status.INFO_REQUESTED,
            ]
        ).count()
        context["active_count"] = assignments.filter(status=HabilitationAssignment.Status.ACTIVE).count()
        context["expiring_count"] = assignments.filter(
            status=HabilitationAssignment.Status.ACTIVE,
            end_date__range=(today, today + timedelta(days=30)),
        ).count()
        context["revoked_count"] = assignments.filter(status=HabilitationAssignment.Status.REVOKED).count()
        context["rejected_count"] = requests.filter(status=HabilitationRequest.Status.REJECTED).count()
        context["critical_count"] = requests.filter(
            urgency=HabilitationRequest.Urgency.CRITICAL
        ).count()
        context["latest_requests"] = requests.order_by("-created_at")[:8]
        return context


class HabilitationRequestListView(LoginRequiredMixin, ListView):
    model = HabilitationRequest
    template_name = "access_control/request_list.html"
    context_object_name = "requests_list"

    def get_queryset(self):
        queryset = HabilitationRequest.objects.select_related(
            "requester", "habilitation", "requested_access_type", "project"
        ).prefetch_related("requested_habilitations")
        user = self.request.user
        if not (user.is_admin_role or getattr(user, "is_access_admin_role", False)):
            queryset = queryset.filter(Q(requester=user) | Q(steps__assigned_to=user)).distinct()

        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        access_type = self.request.GET.get("type", "").strip()
        urgency = self.request.GET.get("urgency", "").strip()
        requester = self.request.GET.get("requester", "").strip()

        if q:
            queryset = queryset.filter(
                Q(reference__icontains=q)
                | Q(requester__name__icontains=q)
                | Q(habilitation__application__icontains=q)
                | Q(habilitation__items__name__icontains=q)
            )
        if status:
            queryset = queryset.filter(status=status)
        if access_type:
            queryset = queryset.filter(requested_access_type__name=access_type)
        if urgency:
            queryset = queryset.filter(urgency=urgency)
        if requester:
            queryset = queryset.filter(requester_id=requester)
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = HabilitationRequest.Status.choices
        type_names = (
            HabilitationAccessType.objects.values_list("name", flat=True)
            .distinct()
            .order_by("name")
        )
        context["type_choices"] = [(name, name) for name in type_names]
        context["urgency_choices"] = HabilitationRequest.Urgency.choices
        context["requesters"] = User.objects.filter(is_active=True).order_by("name")
        return context


class HabilitationRequestCreateView(LoginRequiredMixin, CreateView):
    model = HabilitationRequest
    form_class = HabilitationRequestForm
    template_name = "access_control/request_form.html"

    def get_initial(self):
        initial = super().get_initial()
        initial["requester"] = self.request.user
        initial["requested_start_date"] = timezone.localdate()
        return initial

    def form_valid(self, form):
        access_request = form.save(commit=False)
        submit_action = form.cleaned_data.get("submit_action")
        if submit_action == "submit":
            access_request.status = HabilitationRequest.Status.SUBMITTED
            access_request.current_step = "Soumise"
        else:
            access_request.status = HabilitationRequest.Status.DRAFT
            access_request.current_step = "Brouillon"
        access_request.save()
        form.save_m2m()
        _audit(self.request.user, "Creation demande", access_request, request=self.request)
        if submit_action == "submit":
            _submit_request(access_request, self.request.user, self.request)
            messages.success(self.request, "Demande soumise.")
        else:
            messages.success(self.request, "Brouillon enregistre.")
        return redirect("access_control:request_detail", pk=access_request.pk)


class HabilitationRequestUpdateView(LoginRequiredMixin, UpdateView):
    model = HabilitationRequest
    form_class = HabilitationRequestForm
    template_name = "access_control/request_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not request.user.is_admin_role and self.object.requester_id != request.user.id:
            return self.handle_no_permission()
        if not request.user.is_admin_role and self.object.status not in (
            HabilitationRequest.Status.DRAFT,
            HabilitationRequest.Status.INFO_REQUESTED,
        ):
            messages.error(request, "Cette demande ne peut plus etre modifiee.")
            return redirect("access_control:request_detail", pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        access_request = form.save(commit=False)
        if form.cleaned_data.get("submit_action") == "submit":
            access_request.status = HabilitationRequest.Status.SUBMITTED
            access_request.current_step = "Soumise"
        access_request.save()
        form.save_m2m()
        _audit(self.request.user, "Modification demande", access_request, request=self.request)
        if form.cleaned_data.get("submit_action") == "submit":
            _submit_request(access_request, self.request.user, self.request)
            messages.success(self.request, "Demande soumise.")
        else:
            messages.success(self.request, "Demande mise a jour.")
        return redirect("access_control:request_detail", pk=access_request.pk)


class HabilitationRequestDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = HabilitationRequest
    template_name = "access_control/request_confirm_delete.html"
    context_object_name = "access_request"
    success_url = reverse_lazy("access_control:request_list")

    def test_func(self):
        return self.request.user.is_admin_role

    def form_valid(self, form):
        reference = self.object.reference
        _audit(self.request.user, "Suppression demande", self.object, request=self.request)
        messages.success(self.request, f"Demande {reference} supprimee.")
        return super().form_valid(form)


class HabilitationRequestDetailView(LoginRequiredMixin, View):
    template_name = "access_control/request_detail.html"

    def get(self, request, pk):
        access_request = get_object_or_404(
            HabilitationRequest.objects.select_related(
                "requester",
                "habilitation",
                "requested_access_type",
                "project",
            ).prefetch_related("requested_habilitations"),
            pk=pk,
        )
        return render(
            request,
            self.template_name,
            {
                "access_request": access_request,
                "steps": access_request.steps.select_related("assigned_to"),
                "assignments": access_request.assignments.select_related("user", "habilitation"),
                "audit_logs": AuditLog.objects.filter(
                    entity_type="HabilitationRequest", entity_id=str(access_request.pk)
                )[:10],
                "action_form": WorkflowActionForm(),
            },
        )

    def post(self, request, pk):
        access_request = get_object_or_404(HabilitationRequest, pk=pk)
        form = WorkflowActionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Action invalide.")
            return redirect("access_control:request_detail", pk=pk)
        action = form.cleaned_data["action"]
        comment = form.cleaned_data.get("comment", "")
        error = ""
        if action == "approve":
            error = _approve_step(access_request, request.user, comment, request)
        elif action == "reject":
            error = _reject_step(access_request, request.user, comment, request)
        elif action == "request_info":
            _request_info(access_request, request.user, comment, request)
        elif action == "grant":
            error = _grant_access(access_request, request.user, comment, request)
        elif action == "revoke":
            error = _revoke_access(access_request, request.user, comment, request)
        elif action == "renew":
            assignment = access_request.assignments.order_by("-end_date").first()
            duration = (
                (assignment.end_date - assignment.start_date).days
                if assignment and assignment.end_date
                else None
            )
            if assignment and duration is not None:
                base_date = assignment.end_date or timezone.localdate()
                assignment.end_date = base_date + timedelta(
                    days=duration
                )
                assignment.status = HabilitationAssignment.Status.ACTIVE
                assignment.save(update_fields=["end_date", "status", "updated_at"])
                _audit(request.user, "Renouvellement", access_request, request=request)
            elif not assignment:
                error = "Aucun acces a renouveler."
            else:
                error = "Cet acces accorde n'a pas de date de fin definie."
        if error:
            messages.error(request, error)
        else:
            messages.success(request, "Action enregistree.")
        return redirect("access_control:request_detail", pk=pk)


class HabilitationCatalogView(LoginRequiredMixin, ListView):
    model = Habilitation
    template_name = "access_control/catalog_list.html"
    context_object_name = "habilitations"

    def get_queryset(self):
        queryset = Habilitation.objects.select_related("responsible").prefetch_related(
            "items", "access_types"
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(application__icontains=q) | Q(items__name__icontains=q)
            ).distinct()
        return queryset.order_by("application")


class HabilitationCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Habilitation
    form_class = HabilitationForm
    template_name = "access_control/catalog_form.html"
    success_url = reverse_lazy("access_control:catalog")

    def form_valid(self, form):
        response = super().form_valid(form)
        _audit(self.request.user, "Creation habilitation", self.object, request=self.request)
        messages.success(self.request, "Habilitation creee.")
        return response


class HabilitationUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Habilitation
    form_class = HabilitationForm
    template_name = "access_control/catalog_form.html"
    success_url = reverse_lazy("access_control:catalog")

    def form_valid(self, form):
        response = super().form_valid(form)
        _audit(self.request.user, "Modification habilitation", self.object, request=self.request)
        messages.success(self.request, "Habilitation mise a jour.")
        return response


class HabilitationDetailView(LoginRequiredMixin, TemplateView):
    template_name = "access_control/catalog_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["habilitation"] = get_object_or_404(
            Habilitation.objects.select_related("responsible").prefetch_related(
                "items", "access_types"
            ),
            pk=kwargs["pk"],
        )
        return context


class HabilitationDeleteView(AccessDeleteView):
    model = Habilitation
    success_url = reverse_lazy("access_control:catalog")
    cancel_url_name = "access_control:catalog_detail"
    delete_kind = "habilitation"
    audit_action = "Suppression habilitation"
    success_message = "Habilitation supprimee."
    blocked_message = (
        "Cette habilitation ne peut pas etre supprimee car elle est liee a des demandes ou des acces."
    )

    def get_delete_label(self):
        return self.object.application


class ValidationsView(LoginRequiredMixin, ListView):
    model = HabilitationRequestStep
    template_name = "access_control/validations.html"
    context_object_name = "steps"

    def get_queryset(self):
        queryset = HabilitationRequestStep.objects.select_related(
            "request", "request__requester", "request__habilitation", "assigned_to"
        ).filter(status=HabilitationRequestStep.Status.PENDING)
        if not (self.request.user.is_admin_role or getattr(self.request.user, "is_access_admin_role", False)):
            queryset = queryset.filter(assigned_to=self.request.user)
        return queryset.order_by("created_at")


class GrantedAccessView(LoginRequiredMixin, ListView):
    model = HabilitationAssignment
    template_name = "access_control/granted.html"
    context_object_name = "assignments"

    def get_queryset(self):
        today = timezone.localdate()
        HabilitationAssignment.objects.filter(
            status=HabilitationAssignment.Status.ACTIVE,
            end_date__lt=today,
        ).update(status=HabilitationAssignment.Status.EXPIRED)
        return HabilitationAssignment.objects.select_related(
            "user", "habilitation", "granted_by"
        ).order_by("end_date")


class HabilitationAssignmentDeleteView(AccessDeleteView):
    model = HabilitationAssignment
    success_url = reverse_lazy("access_control:granted")
    delete_kind = "acces accorde"
    audit_action = "Suppression acces accorde"
    success_message = "Acces accorde supprime."
    cancel_url_name = "access_control:assignment_update"

    def get_delete_label(self):
        return f"{self.object.user.name} - {self.object.habilitation.application}"


class HabilitationAssignmentUpdateView(
    LoginRequiredMixin, AdminRequiredMixin, UpdateView
):
    model = HabilitationAssignment
    form_class = HabilitationAssignmentForm
    template_name = "access_control/assignment_form.html"
    success_url = reverse_lazy("access_control:granted")

    def form_valid(self, form):
        response = super().form_valid(form)
        _audit(
            self.request.user,
            "Modification acces accorde",
            self.object,
            request=self.request,
        )
        messages.success(self.request, "Acces accorde mis a jour.")
        return response


class EmployeeMovementListView(LoginRequiredMixin, ListView):
    model = EmployeeMovement
    template_name = "access_control/hr_movements.html"
    context_object_name = "movements"

    def get_queryset(self):
        return EmployeeMovement.objects.select_related("user").order_by("-effective_date")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_admin_role:
            context["form"] = EmployeeMovementForm()
        return context

    def post(self, request):
        if not request.user.is_admin_role:
            return self.handle_no_permission()
        form = EmployeeMovementForm(request.POST)
        if form.is_valid():
            movement = form.save()
            if movement.movement_type == EmployeeMovement.MovementType.DEPARTURE:
                HabilitationAssignment.objects.filter(
                    user=movement.user, status=HabilitationAssignment.Status.ACTIVE
                ).update(
                    status=HabilitationAssignment.Status.REVOKED,
                    revoked_by=request.user,
                    revoked_reason="Depart salarie",
                    updated_at=timezone.now(),
                )
            elif movement.movement_type == EmployeeMovement.MovementType.SUSPENSION:
                HabilitationAssignment.objects.filter(
                    user=movement.user, status=HabilitationAssignment.Status.ACTIVE
                ).update(status=HabilitationAssignment.Status.SUSPENDED, updated_at=timezone.now())
            _audit(request.user, "Creation mouvement RH", movement, request=request)
            messages.success(request, "Mouvement RH enregistre.")
        else:
            messages.error(request, "Le mouvement RH n'a pas pu etre enregistre.")
        return redirect("access_control:hr_movements")


class EmployeeMovementDeleteView(AccessDeleteView):
    model = EmployeeMovement
    success_url = reverse_lazy("access_control:hr_movements")
    delete_kind = "mouvement RH"
    audit_action = "Suppression mouvement RH"
    success_message = "Mouvement RH supprime."
    cancel_url_name = "access_control:movement_update"

    def get_delete_label(self):
        return f"{self.object.user.name} - {self.object.get_movement_type_display()}"


class EmployeeMovementUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = EmployeeMovement
    form_class = EmployeeMovementForm
    template_name = "access_control/movement_form.html"
    success_url = reverse_lazy("access_control:hr_movements")

    def form_valid(self, form):
        response = super().form_valid(form)
        _audit(
            self.request.user,
            "Modification mouvement RH",
            self.object,
            request=self.request,
        )
        messages.success(self.request, "Mouvement RH mis a jour.")
        return response


class AuditLogView(LoginRequiredMixin, ListView):
    model = AuditLog
    template_name = "access_control/audit.html"
    context_object_name = "logs"

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("user")
        user = self.request.GET.get("user", "").strip()
        action = self.request.GET.get("action", "").strip()
        module = self.request.GET.get("module", "").strip()
        if user:
            queryset = queryset.filter(user_id=user)
        if action:
            queryset = queryset.filter(action__icontains=action)
        if module:
            queryset = queryset.filter(entity_type__icontains=module)
        return queryset.order_by("-created_at")[:200]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["users"] = User.objects.filter(is_active=True).order_by("name")
        return context


class AuditLogClearView(LoginRequiredMixin, AdminRequiredMixin, View):
    permission_required = "access_control.delete_auditlog"
    def post(self, request):
        deleted_count, _ = AuditLog.objects.all().delete()
        messages.success(
            request,
            f"Historique vide ({deleted_count} element(s) supprime(s)).",
        )
        return redirect("access_control:audit")


class AuditLogDeleteView(AccessDeleteView):
    model = AuditLog
    success_url = reverse_lazy("access_control:audit")
    delete_kind = "ligne d'audit"
    audit_action = "Suppression ligne audit"
    success_message = "Ligne d'audit supprimee."

    def get_delete_label(self):
        return f"{self.object.created_at:%d/%m/%Y %H:%M} - {self.object.action}"


class PlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = "access_control/placeholder.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("title", "Page")
        context.setdefault("eyebrow", "Administration")
        context.setdefault("description", "Cette page est prete a etre connectee.")
        return context


class UserRolesView(LoginRequiredMixin, TemplateView):
    template_name = "access_control/user_roles.html"

    role_descriptions = {
        User.Role.ADMIN: "Gestion complète de l'application et des utilisateurs.",
        User.Role.MEMBER: "Utilisateur opérationnel du tableau des tâches.",
        User.Role.COLLABORATOR: "Crée ses demandes et suit ses habilitations.",
        User.Role.MANAGER: "Valide les demandes de son équipe au niveau hiérarchique.",
        User.Role.BUSINESS_OWNER: "Donne l'avis métier sur les habilitations sensibles.",
        User.Role.ACCESS_ADMIN: "Gère le catalogue, attribue, révoque et renouvelle les accès.",
        User.Role.HR: "Gère les mouvements RH et déclenche les revues d'accès.",
        User.Role.AUDITOR: "Consulte l'historique et les traces d'audit.",
        User.Role.SYSTEM_ADMIN: "Accès système complet à tous les modules.",
    }

    role_modules = {
        User.Role.ADMIN: "Tous les modules",
        User.Role.MEMBER: "Tâches",
        User.Role.COLLABORATOR: "Demandes",
        User.Role.MANAGER: "Validations manager",
        User.Role.BUSINESS_OWNER: "Validations métier",
        User.Role.ACCESS_ADMIN: "Habilitations",
        User.Role.HR: "Mouvements RH",
        User.Role.AUDITOR: "Audit",
        User.Role.SYSTEM_ADMIN: "Administration",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = {
            row["role"]: row["count"]
            for row in User.objects.values("role").annotate(count=Count("id"))
        }
        context["roles"] = [
            {
                "value": value,
                "label": label,
                "count": counts.get(value, 0),
                "description": self.role_descriptions.get(value, ""),
                "module": self.role_modules.get(value, "-"),
            }
            for value, label in User.Role.choices
        ]
        context["total_roles"] = len(context["roles"])
        context["assigned_roles"] = sum(1 for role in context["roles"] if role["count"])
        context["total_users"] = User.objects.count()
        return context


class UserDepartmentsView(LoginRequiredMixin, TemplateView):
    template_name = "access_control/user_departments.html"

    def _count_roles(self, *roles):
        return User.objects.filter(role__in=roles).count()

    def _owner_for(self, *roles):
        return User.objects.filter(role__in=roles, is_active=True).order_by("name").first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        departments = [
            {
                "name": "Direction IT",
                "code": "IT",
                "manager": self._owner_for(User.Role.SYSTEM_ADMIN, User.Role.ADMIN, User.Role.ACCESS_ADMIN),
                "members": self._count_roles(User.Role.SYSTEM_ADMIN, User.Role.ADMIN, User.Role.ACCESS_ADMIN),
                "scope": "Support applicatif, systèmes, sécurité et habilitations.",
                "status": "Actif",
            },
            {
                "name": "Ressources humaines",
                "code": "RH",
                "manager": self._owner_for(User.Role.HR, User.Role.ADMIN),
                "members": self._count_roles(User.Role.HR),
                "scope": "Arrivées, départs, mutations et suspensions.",
                "status": "Actif",
            },
            {
                "name": "Responsables métier",
                "code": "METIER",
                "manager": self._owner_for(User.Role.BUSINESS_OWNER, User.Role.MANAGER),
                "members": self._count_roles(User.Role.BUSINESS_OWNER, User.Role.MANAGER),
                "scope": "Avis fonctionnels et validations métier.",
                "status": "Actif",
            },
            {
                "name": "Équipes projets",
                "code": "PROJ",
                "manager": self._owner_for(User.Role.MANAGER, User.Role.ADMIN),
                "members": self._count_roles(User.Role.MEMBER, User.Role.COLLABORATOR, User.Role.MANAGER),
                "scope": "Production des tâches et demandes opérationnelles.",
                "status": "Actif",
            },
            {
                "name": "Audit & conformité",
                "code": "AUDIT",
                "manager": self._owner_for(User.Role.AUDITOR, User.Role.ADMIN),
                "members": self._count_roles(User.Role.AUDITOR),
                "scope": "Consultation des logs, contrôles et traçabilité.",
                "status": "Actif",
            },
        ]
        context["departments"] = departments
        context["total_departments"] = len(departments)
        context["covered_users"] = sum(item["members"] for item in departments)
        context["active_departments"] = sum(1 for item in departments if item["status"] == "Actif")
        return context


class UserPermissionsView(LoginRequiredMixin, TemplateView):
    template_name = "access_control/user_permissions.html"

    permission_matrix = [
        {
            "role": User.Role.COLLABORATOR,
            "permissions": ["Créer demande", "Voir ses demandes", "Voir ses tâches"],
        },
        {
            "role": User.Role.MANAGER,
            "permissions": ["Voir équipe", "Approuver manager", "Refuser manager"],
        },
        {
            "role": User.Role.BUSINESS_OWNER,
            "permissions": ["Avis métier", "Valider urgence", "Demander information"],
        },
        {
            "role": User.Role.ACCESS_ADMIN,
            "permissions": ["Gérer catalogue", "Attribuer accès", "Révoquer accès", "Renouveler accès"],
        },
        {
            "role": User.Role.HR,
            "permissions": ["Créer mouvement RH", "Suspendre accès", "Déclencher revue"],
        },
        {
            "role": User.Role.AUDITOR,
            "permissions": ["Lire audit", "Consulter accès", "Exporter logs"],
        },
        {
            "role": User.Role.SYSTEM_ADMIN,
            "permissions": ["Accès complet", "Gérer utilisateurs", "Configurer rôles"],
        },
    ]

    columns = [
        "Demandes",
        "Validations",
        "Catalogue",
        "Accès",
        "RH",
        "Audit",
        "Utilisateurs",
    ]

    grants = {
        User.Role.COLLABORATOR: {"Demandes"},
        User.Role.MANAGER: {"Demandes", "Validations"},
        User.Role.BUSINESS_OWNER: {"Demandes", "Validations", "Catalogue"},
        User.Role.ACCESS_ADMIN: {"Demandes", "Validations", "Catalogue", "Accès", "Audit"},
        User.Role.HR: {"Accès", "RH", "Audit"},
        User.Role.AUDITOR: {"Demandes", "Catalogue", "Accès", "RH", "Audit"},
        User.Role.SYSTEM_ADMIN: set(columns),
        User.Role.ADMIN: set(columns),
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        labels = dict(User.Role.choices)
        context["columns"] = self.columns
        context["profiles"] = [
            {
                "role": item["role"],
                "label": labels.get(item["role"], item["role"]),
                "permissions": item["permissions"],
                "grants": [column in self.grants.get(item["role"], set()) for column in self.columns],
                "users": User.objects.filter(role=item["role"]).count(),
            }
            for item in self.permission_matrix
        ]
        context["total_profiles"] = len(context["profiles"])
        context["total_permissions"] = sum(len(item["permissions"]) for item in context["profiles"])
        context["auditors"] = User.objects.filter(role=User.Role.AUDITOR).count()
        return context


class StaticWorkChatView(LoginRequiredMixin, TemplateView):
    template_name = "access_control/work_chat.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["channels"] = [
            {"name": "Général", "unread": 2},
            {"name": "Support IT", "unread": 3, "active": True},
            {"name": "Projet refonte", "unread": 0},
            {"name": "Demandes urgentes", "unread": 1},
        ]
        context["direct_messages"] = [
            {"name": "Mohamed Ghayati", "initials": "MG", "online": True},
            {"name": "Adnan Motawakil", "initials": "AM", "online": False},
            {"name": "Haytam Hafid", "initials": "HH", "online": True},
        ]
        context["messages"] = [
            {
                "author": "Mohamed Ghayati",
                "initials": "MG",
                "time": "09:15",
                "content": "Bonjour l'équipe 👋\nMerci de vérifier l'accès au serveur de test pour @Adnan Motawakil.\nIl rencontre une erreur 403 depuis ce matin.",
                "reactions": ["👍 2", "👌 1"],
            },
            {
                "author": "Adnan Motawakil",
                "initials": "AM",
                "time": "09:27",
                "content": "Merci @Mohamed Ghayati, je regarde ça tout de suite.\nJe vous tiens au courant.",
                "reactions": [],
            },
            {
                "author": "Haytam Hafid",
                "initials": "HH",
                "time": "09:45",
                "content": "Voici les journaux d'erreurs que j'ai récupérés sur le serveur.\nÇa peut aider à diagnostiquer le problème.",
                "file": {"name": "logs_serveur_test_2024-05-14.txt", "meta": "12,4 Ko · TXT"},
                "reactions": ["👍 1"],
            },
            {
                "author": "Mohamed Ghayati",
                "initials": "MG",
                "time": "10:02",
                "content": "Parfait, merci @Haytam Hafid 🙏\nJe reviens vers vous dès que j'ai du nouveau.",
                "reactions": ["✅ 1"],
            },
        ]
        context["linked_tasks"] = [
            {
                "code": "IT-241",
                "title": "Accès serveur de test",
                "priority": "Critique",
                "priority_class": "critical",
                "assignee": "Adnan Motawakil",
                "initials": "AM",
                "status": "À vérifier",
            },
            {
                "code": "IT-198",
                "title": "Mise à jour des droits VPN",
                "priority": "Moyenne",
                "priority_class": "medium",
                "assignee": "Mohamed Ghayati",
                "initials": "MG",
                "status": "En cours",
            },
        ]
        context["shared_files"] = [
            {
                "name": "Procédure accès serveur.pdf",
                "type": "PDF",
                "meta": "PDF · 245 Ko · 10/05/2024",
            },
            {
                "name": "Guide dépannage IT.docx",
                "type": "W",
                "meta": "DOCX · 1,1 Mo · 02/05/2024",
            },
        ]
        context["channel_members"] = [
            {"name": "Mohamed Ghayati", "initials": "MG", "role": "Responsable IT", "online": True},
            {"name": "Adnan Motawakil", "initials": "AM", "role": "Ingénieur système", "online": True},
            {"name": "Haytam Hafid", "initials": "HH", "role": "Administrateur", "online": True},
        ]
        context["current_author"] = self.request.user.name or "Haytam Hafid"
        context["current_user_id"] = self.request.user.pk
        context["current_is_admin"] = self.request.user.is_admin_role
        context["current_initials"] = "".join(
            part[:1] for part in (self.request.user.name or "Haytam Hafid").split()[:2]
        ).upper()
        return context


@method_decorator(ensure_csrf_cookie, name="dispatch")
class WorkChatView(LoginRequiredMixin, TemplateView):
    template_name = "access_control/work_chat.html"

    def _ensure_default_channel(self):
        user = self.request.user
        if ChatChannelMember.objects.filter(user=user, channel__is_archived=False).exists():
            return

        channel, _created = ChatChannel.objects.get_or_create(
            slug="support-it",
            defaults={
                "name": "Support IT",
                "description": "Discussion equipe pour les demandes IT.",
                "channel_type": ChatChannel.ChannelType.SUPPORT,
                "created_by": user,
            },
        )
        ChatChannelMember.objects.get_or_create(
            channel=channel,
            user=user,
            defaults={"role": ChatChannelMember.Role.OWNER},
        )

        users = list(User.objects.filter(is_active=True).order_by("name")[:4])
        if user not in users:
            users.insert(0, user)
        for member in users[:4]:
            ChatChannelMember.objects.get_or_create(
                channel=channel,
                user=member,
                defaults={
                    "role": ChatChannelMember.Role.OWNER
                    if member.pk == user.pk
                    else ChatChannelMember.Role.MEMBER
                },
            )

        if channel.messages.exists():
            return

        samples = [
            ("Bonjour, pouvez-vous verifier l'acces au serveur de test ?", users[0]),
            ("Oui, je regarde ca tout de suite.", users[1] if len(users) > 1 else user),
            ("J'ai partage le rapport dans les fichiers.", users[2] if len(users) > 2 else user),
            ("Parfait, merci.", users[0]),
        ]
        for content, author in samples:
            ChatMessage.objects.create(channel=channel, sender=author, content=content)

    def get_context_data(self, **kwargs):
        self._ensure_default_channel()
        context = super().get_context_data(**kwargs)
        context["current_author"] = self.request.user.name or "Haytam Hafid"
        context["current_user_id"] = self.request.user.pk
        context["current_is_admin"] = self.request.user.is_admin_role
        context["current_initials"] = "".join(
            part[:1] for part in (self.request.user.name or "Haytam Hafid").split()[:2]
        ).upper()
        chat_users = User.objects.filter(is_active=True).exclude(
            pk=self.request.user.pk
        ).select_related("chat_presence").order_by("name")
        context["chat_users"] = [
            {
                "id": user.pk,
                "name": user.name,
                "email": user.email,
                "is_online": bool(
                    getattr(user, "chat_presence", None)
                    and user.chat_presence.is_online
                ),
            }
            for user in chat_users
        ]
        return context


@login_required
def api_collection(request, resource):
    serializers = {
        "habilitations": lambda: list(Habilitation.objects.values()),
        "habilitation-requests": lambda: list(
            HabilitationRequest.objects.values(
                "id", "reference", "requester_id", "habilitation_id", "status", "current_step"
            )
        ),
        "employee-movements": lambda: list(EmployeeMovement.objects.values()),
        "audit-logs": lambda: list(AuditLog.objects.values()[:200]),
    }
    if resource not in serializers:
        return JsonResponse({"error": "Ressource inconnue"}, status=404)
    return JsonResponse({"results": serializers[resource]()})


@login_required
def api_habilitation_detail(request, pk):
    item = get_object_or_404(
        Habilitation.objects.prefetch_related("items", "access_types"), pk=pk
    )
    return JsonResponse(
        {
            "id": item.pk,
            "application": item.application,
            "habilitations": list(item.items.values("id", "name")),
            "access_types": list(item.access_types.values("id", "name")),
            "status": item.status,
        }
    )


@login_required
def api_request_detail(request, pk):
    item = get_object_or_404(
        HabilitationRequest.objects.select_related(
            "requester", "habilitation", "requested_access_type"
        ),
        pk=pk,
    )
    return JsonResponse(
        {
            "id": item.pk,
            "reference": item.reference,
            "requester": item.requester.name if item.requester else "",
            "habilitation": item.habilitation.application,
            "requested_habilitations": list(
                item.requested_habilitations.values_list("name", flat=True)
            ),
            "access_type": item.requested_access_type.name,
            "urgency": item.urgency,
            "status": item.status,
            "current_step": item.current_step,
            "requested_start_date": item.requested_start_date.isoformat(),
            "requested_end_date": item.requested_end_date.isoformat() if item.requested_end_date else None,
            "requested_duration_days": item.requested_duration_days,
        }
    )


@login_required
@require_POST
def api_request_submit(request, pk):
    item = get_object_or_404(HabilitationRequest, pk=pk)
    _submit_request(item, request.user, request)
    return JsonResponse({"ok": True, "status": item.status})


@login_required
@require_POST
def api_request_action(request, pk, action):
    item = get_object_or_404(HabilitationRequest, pk=pk)
    comment = request.POST.get("comment", "")
    handlers = {
        "approve": lambda: _approve_step(item, request.user, comment, request),
        "reject": lambda: _reject_step(item, request.user, comment, request),
        "request-info": lambda: (_request_info(item, request.user, comment, request) or ""),
        "grant": lambda: _grant_access(item, request.user, comment, request),
    }
    if action not in handlers:
        return JsonResponse({"ok": False, "error": "Action inconnue"}, status=404)
    error = handlers[action]()
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)
    item.refresh_from_db()
    return JsonResponse({"ok": True, "status": item.status, "current_step": item.current_step})


@login_required
@require_POST
def api_assignment_action(request, pk, action):
    assignment = get_object_or_404(HabilitationAssignment, pk=pk)
    if action == "revoke":
        reason = request.POST.get("comment", "").strip()
        if not reason:
            return JsonResponse({"ok": False, "error": "Motif obligatoire"}, status=400)
        assignment.status = HabilitationAssignment.Status.REVOKED
        assignment.revoked_by = request.user
        assignment.revoked_reason = reason
        assignment.save(update_fields=["status", "revoked_by", "revoked_reason", "updated_at"])
        _audit(request.user, "Revocation", assignment, new_value=reason, request=request)
    elif action == "renew":
        duration = (
            (assignment.end_date - assignment.start_date).days
            if assignment.end_date
            else None
        )
        if duration is None:
            return JsonResponse(
                {"ok": False, "error": "Cet acces accorde n'a pas de date de fin definie."},
                status=400,
            )
        base_date = assignment.end_date or timezone.localdate()
        assignment.end_date = base_date + timedelta(
            days=duration
        )
        assignment.status = HabilitationAssignment.Status.ACTIVE
        assignment.save(update_fields=["end_date", "status", "updated_at"])
        _audit(request.user, "Renouvellement", assignment, request=request)
    else:
        return JsonResponse({"ok": False, "error": "Action inconnue"}, status=404)
    return JsonResponse(
        {
            "ok": True,
            "status": assignment.status,
            "end_date": assignment.end_date.isoformat() if assignment.end_date else None,
        }
    )


@login_required
def api_user_habilitations(request, pk):
    assignments = HabilitationAssignment.objects.filter(user_id=pk).select_related("habilitation")
    return JsonResponse(
        {
            "results": [
                {
                    "application": assignment.habilitation.application,
                    "habilitation": assignment.habilitation.application,
                    "status": assignment.status,
                    "start_date": assignment.start_date.isoformat(),
                    "end_date": assignment.end_date.isoformat() if assignment.end_date else None,
                }
                for assignment in assignments
            ]
        }
    )


@login_required
def api_project_habilitations(request, pk):
    requests = HabilitationRequest.objects.filter(project_id=pk).select_related("habilitation")
    return JsonResponse(
        {
            "results": [
                {
                    "request": item.reference,
                    "application": item.habilitation.application,
                    "habilitation": item.habilitation.application,
                    "status": item.status,
                }
                for item in requests
            ]
        }
    )
