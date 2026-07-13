from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from accounts.mixins import AdminRequiredMixin

from .forms import DocumentFilterForm, DocumentForm
from .models import Document, DocumentHistory


def log_document_action(document, user, action, details=""):
    DocumentHistory.objects.create(
        document=document,
        document_title=document.title,
        user=user,
        action=action,
        source_module=document.source_module,
        details=details,
    )


class DocumentDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "documents/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active = Document.objects.filter(is_archived=False)
        source_labels = dict(Document.SourceModule.choices)
        source_stats = [
            {
                "label": source_labels.get(item["source_module"], item["source_module"]),
                "total": item["total"],
            }
            for item in active.values("source_module")
            .annotate(total=Count("id"))
            .order_by("-total")
        ]
        context.update(
            {
                "total_documents": active.count(),
                "manual_count": active.filter(
                    source_module=Document.SourceModule.MANUAL
                ).count(),
                "attachment_count": active.exclude(
                    source_module=Document.SourceModule.MANUAL
                ).count(),
                "archive_count": Document.objects.filter(is_archived=True).count(),
                "total_size": active.aggregate(total=Sum("file_size"))["total"] or 0,
                "source_stats": source_stats,
                "recent_documents": active.select_related("uploaded_by")[:8],
            }
        )
        return context


class DocumentListView(LoginRequiredMixin, ListView):
    model = Document
    template_name = "documents/document_list.html"
    context_object_name = "documents"
    mode = "all"
    page_title = "Tous les documents"

    def get_queryset(self):
        queryset = Document.objects.select_related("uploaded_by")
        if self.mode == "archives":
            queryset = queryset.filter(is_archived=True)
        else:
            queryset = queryset.filter(is_archived=False)
        if self.mode == "procedures":
            queryset = queryset.filter(category=Document.Category.PROCEDURE)
        elif self.mode == "templates":
            queryset = queryset.filter(
                category__in=[Document.Category.TEMPLATE, Document.Category.FORM]
            )
        elif self.mode == "attachments":
            queryset = queryset.exclude(source_module=Document.SourceModule.MANUAL)

        form = DocumentFilterForm(self.request.GET)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("query"):
                queryset = queryset.filter(
                    Q(title__icontains=data["query"])
                    | Q(original_filename__icontains=data["query"])
                )
            if data.get("source"):
                queryset = queryset.filter(source_module=data["source"])
            if data.get("category"):
                queryset = queryset.filter(category=data["category"])
            if data.get("file_type"):
                queryset = queryset.filter(file_type__icontains=data["file_type"])
            if data.get("service"):
                queryset = queryset.filter(service__icontains=data["service"])
            if data.get("uploaded_by"):
                queryset = queryset.filter(uploaded_by=data["uploaded_by"])
            if data.get("status"):
                queryset = queryset.filter(status=data["status"])
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = DocumentFilterForm(self.request.GET)
        context["page_title"] = self.page_title
        context["mode"] = self.mode
        return context


class ProcedureListView(DocumentListView):
    mode = "procedures"
    page_title = "Procedures"


class TemplateListView(DocumentListView):
    mode = "templates"
    page_title = "Modeles / Formulaires"


class AttachmentListView(DocumentListView):
    mode = "attachments"
    page_title = "Pieces jointes"


class ArchiveListView(DocumentListView):
    mode = "archives"
    page_title = "Archives"


class DocumentHistoryView(LoginRequiredMixin, ListView):
    model = DocumentHistory
    template_name = "documents/history.html"
    context_object_name = "history_entries"

    def get_queryset(self):
        return DocumentHistory.objects.select_related("user", "document").order_by(
            "-created_at"
        )[:300]


class DocumentDetailView(LoginRequiredMixin, DetailView):
    model = Document
    template_name = "documents/document_detail.html"
    context_object_name = "document"


class DocumentCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = "documents/document_form.html"
    success_url = reverse_lazy("documents:all")

    def form_valid(self, form):
        uploaded_file = form.cleaned_data["file"]
        form.instance.original_filename = uploaded_file.name
        form.instance.file_size = uploaded_file.size
        form.instance.file_type = (
            uploaded_file.name.rsplit(".", 1)[-1].upper()
            if "." in uploaded_file.name
            else "FILE"
        )
        form.instance.source_module = Document.SourceModule.MANUAL
        form.instance.source_type = "documents.Document"
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        self.object.source_id = str(self.object.pk)
        self.object.save(update_fields=["source_id", "updated_at"])
        log_document_action(
            self.object,
            self.request.user,
            DocumentHistory.Action.CREATED,
            "Document ajoute manuellement.",
        )
        messages.success(self.request, "Document ajoute.")
        return response


class DocumentUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Document
    form_class = DocumentForm
    template_name = "documents/document_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object.source_module != Document.SourceModule.MANUAL:
            form.fields["file"].disabled = True
            form.fields["file"].help_text = (
                "Le fichier reste gere dans son module d'origine."
            )
        return form

    def form_valid(self, form):
        uploaded_file = form.cleaned_data.get("file")
        if uploaded_file and uploaded_file is not self.object.file:
            form.instance.original_filename = uploaded_file.name
            form.instance.file_size = uploaded_file.size
        response = super().form_valid(form)
        log_document_action(
            self.object,
            self.request.user,
            DocumentHistory.Action.UPDATED,
            "Metadonnees du document modifiees.",
        )
        messages.success(self.request, "Document mis a jour.")
        return response

    def get_success_url(self):
        return reverse_lazy("documents:detail", kwargs={"pk": self.object.pk})


class DocumentDownloadView(LoginRequiredMixin, View):
    as_attachment = True
    action = DocumentHistory.Action.DOWNLOADED

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        if not document.file:
            raise Http404("Fichier introuvable.")
        try:
            file_handle = document.file.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            raise Http404("Fichier introuvable.")
        log_document_action(document, request.user, self.action)
        return FileResponse(
            file_handle,
            as_attachment=self.as_attachment,
            filename=document.original_filename,
        )


class DocumentOpenView(DocumentDownloadView):
    as_attachment = False
    action = DocumentHistory.Action.OPENED


class DocumentArchiveView(LoginRequiredMixin, AdminRequiredMixin, View):
    permission_required = "documents.change_document"
    def post(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        if document.is_archived:
            document.status = Document.Status.ACTIVE
            action = DocumentHistory.Action.RESTORED
            message = "Document restaure."
        else:
            document.status = Document.Status.ARCHIVED
            action = DocumentHistory.Action.ARCHIVED
            message = "Document archive."
        document.save(update_fields=["status", "is_archived", "updated_at"])
        log_document_action(document, request.user, action)
        messages.success(request, message)
        return redirect(request.POST.get("next") or "documents:all")
