from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from tasks.models import Attachment, Task

from .models import Document, DocumentHistory


class DocumentManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="documents-admin@example.com",
            password="pass",
            name="Documents Admin",
            role=User.Role.ADMIN,
        )
        self.member = User.objects.create_user(
            email="documents-member@example.com",
            password="pass",
            name="Documents Member",
            role=User.Role.MEMBER,
        )

    def upload(self, name="rapport_test.pdf", content=b"document"):
        return SimpleUploadedFile(
            name,
            content,
            content_type="application/pdf",
        )

    def test_task_attachment_is_automatically_indexed(self):
        task = Task.objects.create(
            title="Tester les sauvegardes",
            created_by=self.admin,
        )
        attachment = Attachment.objects.create(
            task=task,
            uploaded_by=self.admin,
            file=self.upload("checklist.pdf"),
            original_name="checklist.pdf",
        )

        document = Document.objects.get(
            source_type="tasks.Attachment",
            source_id=str(attachment.pk),
        )

        self.assertEqual(document.source_module, Document.SourceModule.TASK)
        self.assertEqual(document.linked_item_label, task.title)
        self.assertEqual(document.file.name, attachment.file.name)

    def test_admin_can_create_manual_document(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("documents:create"),
            {
                "title": "Rapport mensuel",
                "file": self.upload(),
                "category": Document.Category.REPORT,
                "service": "IT",
                "status": Document.Status.ACTIVE,
            },
        )

        document = Document.objects.get(title="Rapport mensuel")
        self.assertRedirects(response, reverse("documents:all"))
        self.assertEqual(document.source_module, Document.SourceModule.MANUAL)
        self.assertTrue(
            DocumentHistory.objects.filter(
                document=document,
                action=DocumentHistory.Action.CREATED,
            ).exists()
        )

    def test_member_cannot_create_or_archive_document(self):
        document = Document.objects.create(
            title="Document protege",
            original_filename="protege.pdf",
            file=self.upload("protege.pdf"),
            uploaded_by=self.admin,
        )
        self.client.force_login(self.member)

        create_response = self.client.get(reverse("documents:create"))
        archive_response = self.client.post(
            reverse("documents:archive", args=[document.pk])
        )

        self.assertRedirects(create_response, reverse("dashboard:home"))
        self.assertRedirects(archive_response, reverse("dashboard:home"))
        document.refresh_from_db()
        self.assertFalse(document.is_archived)

    def test_archiving_does_not_delete_file(self):
        document = Document.objects.create(
            title="Document a archiver",
            original_filename="archive.pdf",
            file=self.upload("archive.pdf"),
            uploaded_by=self.admin,
        )
        storage = document.file.storage
        file_name = document.file.name
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("documents:archive", args=[document.pk])
        )

        document.refresh_from_db()
        self.assertRedirects(response, reverse("documents:all"))
        self.assertTrue(document.is_archived)
        self.assertTrue(storage.exists(file_name))

    def test_download_is_logged(self):
        document = Document.objects.create(
            title="Document telecharge",
            original_filename="download.pdf",
            file=self.upload("download.pdf"),
            uploaded_by=self.admin,
        )
        self.client.force_login(self.member)

        response = self.client.get(
            reverse("documents:download", args=[document.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            DocumentHistory.objects.filter(
                document=document,
                user=self.member,
                action=DocumentHistory.Action.DOWNLOADED,
            ).exists()
        )

    def test_attachments_page_excludes_manual_documents(self):
        manual = Document.objects.create(
            title="Document manuel",
            original_filename="manual.pdf",
            file=self.upload("manual.pdf"),
            source_module=Document.SourceModule.MANUAL,
        )
        task = Task.objects.create(title="Tache source", created_by=self.admin)
        Attachment.objects.create(
            task=task,
            uploaded_by=self.admin,
            file=self.upload("task.pdf"),
            original_name="task.pdf",
        )
        self.client.force_login(self.member)

        response = self.client.get(reverse("documents:attachments"))

        self.assertNotContains(response, manual.title)
        self.assertContains(response, "task.pdf")
