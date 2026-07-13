from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .forms import HabilitationForm, HabilitationRequestForm
from .models import (
    AuditLog,
    EmployeeMovement,
    Habilitation,
    HabilitationAccessType,
    HabilitationAssignment,
    HabilitationItem,
    HabilitationRequest,
)


def add_catalog_options(application, item_name="Habilitation test", type_name="Lecture"):
    item = HabilitationItem.objects.create(
        application=application,
        name=item_name,
    )
    access_type = HabilitationAccessType.objects.create(
        application=application,
        name=type_name,
    )
    return item, access_type


class HabilitationRequestDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="pass",
            name="Admin",
            role=User.Role.ADMIN,
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            password="pass",
            name="Member",
            role=User.Role.MEMBER,
        )
        self.habilitation = Habilitation.objects.create(
            application="SAP Demandes Test",
        )
        self.catalog_item, self.catalog_access_type = add_catalog_options(
            self.habilitation,
            "Acces SAP Achat",
            "Lecture",
        )
        start_date = timezone.localdate()
        self.access_request = HabilitationRequest.objects.create(
            requester=self.member,
            habilitation=self.habilitation,
            requested_access_type=self.catalog_access_type,
            justification="Besoin pour traiter les achats.",
            requested_start_date=start_date,
            requested_duration_days=30,
            requested_end_date=start_date + timedelta(days=30),
        )
        self.access_request.requested_habilitations.add(self.catalog_item)

    def test_admin_can_open_delete_confirmation(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("access_control:request_delete", args=[self.access_request.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supprimer la demande")

    def test_member_cannot_delete_request(self):
        self.client.force_login(self.member)

        response = self.client.post(
            reverse("access_control:request_delete", args=[self.access_request.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(HabilitationRequest.objects.filter(pk=self.access_request.pk).exists())


class AccessControlAdminDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-delete@example.com",
            password="pass",
            name="Admin Delete",
            role=User.Role.ADMIN,
        )
        self.member = User.objects.create_user(
            email="member-delete@example.com",
            password="pass",
            name="Member Delete",
            role=User.Role.MEMBER,
        )
        self.habilitation = Habilitation.objects.create(
            application="VPN",
        )
        self.catalog_item, self.catalog_access_type = add_catalog_options(
            self.habilitation,
            "Acces VPN standard",
            "Distant",
        )
        today = timezone.localdate()
        self.assignment = HabilitationAssignment.objects.create(
            user=self.member,
            habilitation=self.habilitation,
            start_date=today,
            end_date=today + timedelta(days=90),
            granted_by=self.admin,
        )
        self.movement = EmployeeMovement.objects.create(
            user=self.member,
            movement_type=EmployeeMovement.MovementType.ROLE_CHANGE,
            old_position="Support",
            new_position="Administrateur",
            effective_date=today,
        )
        self.audit_log = AuditLog.objects.create(
            user=self.admin,
            action="Test",
            entity_type="TestEntity",
            entity_id="1",
        )

    def test_admin_can_delete_catalog_item(self):
        free_habilitation = Habilitation.objects.create(
            application="Application libre",
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("access_control:catalog_delete", args=[free_habilitation.pk])
        )

        self.assertRedirects(response, reverse("access_control:catalog"))
        self.assertFalse(Habilitation.objects.filter(pk=free_habilitation.pk).exists())

    def test_admin_can_delete_assignment(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("access_control:assignment_delete", args=[self.assignment.pk])
        )

        self.assertRedirects(response, reverse("access_control:granted"))
        self.assertFalse(HabilitationAssignment.objects.filter(pk=self.assignment.pk).exists())

    def test_admin_can_delete_employee_movement(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("access_control:movement_delete", args=[self.movement.pk])
        )

        self.assertRedirects(response, reverse("access_control:hr_movements"))
        self.assertFalse(EmployeeMovement.objects.filter(pk=self.movement.pk).exists())

    def test_admin_can_delete_audit_log(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("access_control:audit_delete", args=[self.audit_log.pk])
        )

        self.assertRedirects(response, reverse("access_control:audit"))
        self.assertFalse(AuditLog.objects.filter(pk=self.audit_log.pk).exists())

    def test_admin_can_clear_all_audit_logs(self):
        AuditLog.objects.create(
            user=self.admin,
            action="Second test",
            entity_type="TestEntity",
            entity_id="2",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("access_control:audit_clear"))

        self.assertRedirects(response, reverse("access_control:audit"))
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_member_cannot_clear_audit_logs(self):
        self.client.force_login(self.member)

        response = self.client.post(reverse("access_control:audit_clear"))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(AuditLog.objects.exists())

    def test_member_cannot_delete_catalog_item(self):
        self.client.force_login(self.member)

        response = self.client.post(
            reverse("access_control:catalog_delete", args=[self.habilitation.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Habilitation.objects.filter(pk=self.habilitation.pk).exists())

    def test_admin_can_modify_catalog_assignment_and_movement_with_delete_option(self):
        self.client.force_login(self.admin)

        catalog_response = self.client.get(
            reverse("access_control:catalog_update", args=[self.habilitation.pk])
        )
        assignment_response = self.client.get(
            reverse("access_control:assignment_update", args=[self.assignment.pk])
        )
        movement_response = self.client.get(
            reverse("access_control:movement_update", args=[self.movement.pk])
        )

        self.assertContains(
            catalog_response,
            reverse("access_control:catalog_delete", args=[self.habilitation.pk]),
        )
        self.assertContains(
            assignment_response,
            reverse("access_control:assignment_delete", args=[self.assignment.pk]),
        )
        self.assertContains(
            movement_response,
            reverse("access_control:movement_delete", args=[self.movement.pk]),
        )

    def test_member_cannot_modify_admin_managed_access_records(self):
        self.client.force_login(self.member)

        responses = (
            self.client.get(
                reverse("access_control:catalog_update", args=[self.habilitation.pk])
            ),
            self.client.get(
                reverse("access_control:assignment_update", args=[self.assignment.pk])
            ),
            self.client.get(
                reverse("access_control:movement_update", args=[self.movement.pk])
            ),
        )

        self.assertTrue(all(response.status_code == 403 for response in responses))

    def test_admin_can_modify_submitted_request_and_delete_from_form(self):
        access_request = HabilitationRequest.objects.create(
            requester=self.member,
            habilitation=self.habilitation,
            requested_access_type=self.catalog_access_type,
            justification="Administration de la demande.",
            requested_start_date=timezone.localdate(),
            status=HabilitationRequest.Status.SUBMITTED,
        )
        access_request.requested_habilitations.add(self.catalog_item)
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("access_control:request_update", args=[access_request.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("access_control:request_delete", args=[access_request.pk]),
        )

    def test_member_cannot_modify_another_users_request(self):
        other_user = User.objects.create_user(
            email="other-request@example.com",
            password="pass",
            name="Other User",
            role=User.Role.MEMBER,
        )
        access_request = HabilitationRequest.objects.create(
            requester=other_user,
            habilitation=self.habilitation,
            requested_access_type=self.catalog_access_type,
            justification="Demande d'un autre utilisateur.",
            requested_start_date=timezone.localdate(),
        )
        access_request.requested_habilitations.add(self.catalog_item)
        self.client.force_login(self.member)

        response = self.client.get(
            reverse("access_control:request_update", args=[access_request.pk])
        )

        self.assertEqual(response.status_code, 403)


class HabilitationRequestDateFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="dates@example.com",
            password="pass",
            name="Dates User",
            role=User.Role.MEMBER,
        )
        self.habilitation = Habilitation.objects.create(
            application="Application date",
        )
        self.catalog_item, self.catalog_access_type = add_catalog_options(
            self.habilitation,
            "Acces date",
            "Lecture",
        )

    def form_data(self, **overrides):
        data = {
            "requester": self.user.pk,
            "habilitation": self.habilitation.pk,
            "project": "",
            "requested_habilitations": [self.catalog_item.pk],
            "requested_access_type": self.catalog_access_type.pk,
            "urgency": HabilitationRequest.Urgency.MEDIUM,
            "justification": "Besoin temporaire.",
            "requested_start_date": "2026-07-08",
            "requested_end_date": "",
            "submit_action": "draft",
        }
        data.update(overrides)
        return data

    def test_end_date_is_optional_and_duration_is_null(self):
        form = HabilitationRequestForm(data=self.form_data())

        self.assertTrue(form.is_valid(), form.errors)
        access_request = form.save()

        self.assertIsNone(access_request.requested_end_date)
        self.assertIsNone(access_request.requested_duration_days)

    def test_duration_is_calculated_from_start_and_end_dates(self):
        form = HabilitationRequestForm(
            data=self.form_data(requested_end_date="2026-07-18")
        )

        self.assertTrue(form.is_valid(), form.errors)
        access_request = form.save()

        self.assertEqual(access_request.requested_duration_days, 10)

    def test_end_date_cannot_be_before_start_date(self):
        form = HabilitationRequestForm(
            data=self.form_data(requested_end_date="2026-07-07")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("requested_end_date", form.errors)

    def test_multiple_habilitations_from_application_are_accepted(self):
        second_item = HabilitationItem.objects.create(
            application=self.habilitation,
            name="Acces date avance",
            position=1,
        )
        form = HabilitationRequestForm(
            data=self.form_data(
                requested_habilitations=[
                    self.catalog_item.pk,
                    second_item.pk,
                ]
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        access_request = form.save()
        self.assertEqual(access_request.requested_habilitations.count(), 2)

    def test_options_from_another_application_are_rejected(self):
        other_application = Habilitation.objects.create(
            application="Autre application",
        )
        other_item, other_access_type = add_catalog_options(
            other_application,
            "Acces externe",
            "Administration",
        )
        form = HabilitationRequestForm(
            data=self.form_data(
                requested_habilitations=[other_item.pk],
                requested_access_type=other_access_type.pk,
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("requested_habilitations", form.errors)
        self.assertIn("requested_access_type", form.errors)


class HabilitationCatalogFormTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="catalog@example.com",
            password="pass",
            name="Catalog Admin",
            role=User.Role.ADMIN,
        )

    def form_data(self, **overrides):
        data = {
            "application": "SAP Catalogue Test",
            "habilitation_names": [
                "Acces SAP Achat",
                "Acces SAP Finance",
                "Acces SAP Consultation",
            ],
            "access_type_names": [
                "Lecture / ecriture",
                "Lecture seule",
            ],
            "responsible": self.admin.pk,
            "status": Habilitation.Status.ACTIVE,
        }
        data.update(overrides)
        return data

    def test_form_creates_application_with_multiple_habilitations(self):
        form = HabilitationForm(data=self.form_data())

        self.assertTrue(form.is_valid(), form.errors)
        application = form.save()

        self.assertEqual(application.application, "SAP Catalogue Test")
        self.assertEqual(
            list(application.items.values_list("name", flat=True)),
            [
                "Acces SAP Achat",
                "Acces SAP Finance",
                "Acces SAP Consultation",
            ],
        )
        self.assertEqual(
            list(application.access_types.values_list("name", flat=True)),
            ["Lecture / ecriture", "Lecture seule"],
        )

    def test_form_requires_at_least_one_habilitation(self):
        form = HabilitationForm(data=self.form_data(habilitation_names=[]))

        self.assertFalse(form.is_valid())
        self.assertIn("habilitation_names", form.errors)

    def test_form_requires_at_least_one_access_type(self):
        form = HabilitationForm(data=self.form_data(access_type_names=[]))

        self.assertFalse(form.is_valid())
        self.assertIn("access_type_names", form.errors)

    def test_update_replaces_application_habilitations(self):
        application = Habilitation.objects.create(
            application="Oracle Catalogue Test",
        )
        HabilitationItem.objects.create(
            application=application,
            name="Ancienne habilitation",
        )
        HabilitationAccessType.objects.create(
            application=application,
            name="Ancien type",
        )
        form = HabilitationForm(
            data=self.form_data(
                application="Oracle Catalogue Test",
                habilitation_names=[
                    "Acces Oracle Production",
                    "Acces Oracle Administration",
                ],
                access_type_names=["Administration", "Lecture seule"],
            ),
            instance=application,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertEqual(
            list(application.items.values_list("name", flat=True)),
            ["Acces Oracle Production", "Acces Oracle Administration"],
        )
        self.assertEqual(
            list(application.access_types.values_list("name", flat=True)),
            ["Administration", "Lecture seule"],
        )
