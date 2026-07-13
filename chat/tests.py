import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from tasks.models import Task

from .models import (
    ChatChannel,
    ChatChannelMember,
    ChatChannelTask,
    ChatMessage,
    ChatMessageAttachment,
    ChatMessageReaction,
    ChatMessageReadReceipt,
    ChatUserPresence,
)

User = get_user_model()


class ChatApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="123",
            name="Owner User",
            role=User.Role.ADMIN,
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            password="123",
            name="Member User",
        )
        self.viewer = User.objects.create_user(
            email="viewer@example.com",
            password="123",
            name="Viewer User",
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com",
            password="123",
            name="Outsider User",
        )
        self.channel = ChatChannel.objects.create(name="Support IT", created_by=self.owner)
        ChatChannelMember.objects.create(
            channel=self.channel,
            user=self.owner,
            role=ChatChannelMember.Role.OWNER,
        )
        ChatChannelMember.objects.create(
            channel=self.channel,
            user=self.member,
            role=ChatChannelMember.Role.MEMBER,
        )
        ChatChannelMember.objects.create(
            channel=self.channel,
            user=self.viewer,
            role=ChatChannelMember.Role.VIEWER,
        )
        self.client = Client(HTTP_HOST="127.0.0.1:8000")

    def _login(self, user):
        self.client.force_login(user)

    def _json_put(self, url, payload):
        return self.client.put(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_HOST="127.0.0.1:8000",
        )

    def _json_post(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_HOST="127.0.0.1:8000",
        )

    def _json_delete(self, url, payload=None):
        return self.client.delete(
            url,
            data=json.dumps(payload or {}),
            content_type="application/json",
            HTTP_HOST="127.0.0.1:8000",
        )

    def test_authenticated_user_can_list_own_channels(self):
        self._login(self.member)

        response = self.client.get("/api/chat/channels/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["name"], "Support IT")

    def test_user_cannot_access_channel_where_they_are_not_member(self):
        self._login(self.outsider)

        response = self.client.get(f"/api/chat/channels/{self.channel.pk}/messages/")

        self.assertEqual(response.status_code, 403)

    def test_member_can_send_message(self):
        self._login(self.member)

        response = self.client.post(
            f"/api/chat/channels/{self.channel.pk}/messages/",
            {"content": "Bonjour @Owner"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(response.json()["sender"]["id"], self.member.pk)

    def test_viewer_cannot_send_message(self):
        self._login(self.viewer)

        response = self.client.post(
            f"/api/chat/channels/{self.channel.pk}/messages/",
            {"content": "Je lis seulement."},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ChatMessage.objects.count(), 0)

    def test_user_can_edit_own_message(self):
        message = ChatMessage.objects.create(channel=self.channel, sender=self.member, content="Avant")
        self._login(self.member)

        response = self._json_put(f"/api/chat/messages/{message.pk}/", {"content": "Apres"})

        self.assertEqual(response.status_code, 200)
        message.refresh_from_db()
        self.assertEqual(message.content, "Apres")
        self.assertTrue(message.is_edited)

    def test_user_cannot_edit_another_users_message(self):
        message = ChatMessage.objects.create(channel=self.channel, sender=self.owner, content="Owner")
        self._login(self.member)

        response = self._json_put(f"/api/chat/messages/{message.pk}/", {"content": "Nope"})

        self.assertEqual(response.status_code, 403)

    def test_reaction_toggle_works(self):
        message = ChatMessage.objects.create(channel=self.channel, sender=self.owner, content="Salut")
        self._login(self.member)

        first = self.client.post(f"/api/chat/messages/{message.pk}/reactions/", {"emoji": "+1"})
        second = self.client.post(f"/api/chat/messages/{message.pk}/reactions/", {"emoji": "+1"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(ChatMessageReaction.objects.count(), 0)

    def test_mark_read_works(self):
        message = ChatMessage.objects.create(channel=self.channel, sender=self.owner, content="A lire")
        self._login(self.member)

        response = self.client.post(f"/api/chat/channels/{self.channel.pk}/mark-read/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ChatMessageReadReceipt.objects.filter(message=message, user=self.member).exists())

    def test_unread_count_endpoint_counts_unread_messages(self):
        ChatMessage.objects.create(channel=self.channel, sender=self.owner, content="A lire")
        read_message = ChatMessage.objects.create(channel=self.channel, sender=self.owner, content="Deja lu")
        ChatMessageReadReceipt.objects.create(message=read_message, user=self.member)
        ChatMessage.objects.create(channel=self.channel, sender=self.member, content="Mon message")
        self._login(self.member)

        response = self.client.get("/api/chat/unread-count/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 1)

    def test_message_payload_lists_users_who_read_it(self):
        message = ChatMessage.objects.create(channel=self.channel, sender=self.owner, content="A lire")
        ChatMessageReadReceipt.objects.create(message=message, user=self.member)
        self._login(self.owner)

        response = self.client.get(f"/api/chat/channels/{self.channel.pk}/messages/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["read_by"][0]["id"], self.member.pk)

    def test_presence_heartbeat_marks_user_online(self):
        self._login(self.member)

        response = self._json_post("/api/chat/presence/", {"status": "online"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_online"])
        self.assertTrue(ChatUserPresence.objects.get(user=self.member).is_online)

    def test_presence_can_mark_user_offline(self):
        ChatUserPresence.objects.create(
            user=self.member,
            is_available=True,
        )
        self._login(self.member)

        response = self._json_post("/api/chat/presence/", {"status": "offline"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_online"])

    def test_presence_expires_after_timeout(self):
        presence = ChatUserPresence.objects.create(
            user=self.member,
            is_available=True,
            last_seen_at=timezone.now() - timedelta(minutes=3),
        )

        self.assertFalse(presence.is_online)

    def test_shared_files_endpoint_returns_attachments(self):
        message = ChatMessage.objects.create(channel=self.channel, sender=self.owner, content="Fichier")
        attachment = ChatMessageAttachment.objects.create(
            message=message,
            uploaded_by=self.owner,
            file=SimpleUploadedFile("logs.txt", b"hello", content_type="text/plain"),
            original_name="logs.txt",
            file_type="TXT",
            file_size=5,
        )
        self._login(self.member)

        response = self.client.get(f"/api/chat/channels/{self.channel.pk}/shared-files/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], attachment.pk)
        self.assertEqual(response.json()[0]["original_name"], "logs.txt")

    def test_attachment_opens_inline_for_channel_member(self):
        message = ChatMessage.objects.create(channel=self.channel, sender=self.owner, content="Fichier")
        attachment = ChatMessageAttachment.objects.create(
            message=message,
            uploaded_by=self.owner,
            file=SimpleUploadedFile("rapport.pdf", b"%PDF-1.4", content_type="application/pdf"),
            original_name="rapport.pdf",
            file_type="PDF",
            file_size=8,
        )
        self._login(self.member)

        response = self.client.get(f"/api/chat/attachments/{attachment.pk}/download/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))

    def test_linked_tasks_endpoint_returns_related_tasks(self):
        task = Task.objects.create(title="Acces serveur", assigned_to=self.member, created_by=self.owner)
        ChatChannelTask.objects.create(channel=self.channel, task=task, created_by=self.owner)
        self._login(self.member)

        response = self.client.get(f"/api/chat/channels/{self.channel.pk}/linked-tasks/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], task.pk)

    def test_direct_conversation_creates_and_reuses_channel(self):
        ChatUserPresence.objects.create(
            user=self.outsider,
            is_available=True,
        )
        self._login(self.owner)

        first = self._json_post("/api/chat/direct-conversations/", {"user_id": self.outsider.pk})
        second = self._json_post("/api/chat/direct-conversations/", {"user_id": self.outsider.pk})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(first.json()["channel_type"], "direct")
        self.assertTrue(first.json()["direct_user"]["is_online"])

    def test_owner_can_rename_channel(self):
        self._login(self.owner)

        response = self._json_put(
            f"/api/chat/channels/{self.channel.pk}/",
            {"name": "Support Technique", "description": "Nouveau sujet"},
        )

        self.assertEqual(response.status_code, 200)
        self.channel.refresh_from_db()
        self.assertEqual(self.channel.name, "Support Technique")
        self.assertEqual(self.channel.description, "Nouveau sujet")

    def test_owner_can_add_and_remove_member(self):
        self._login(self.owner)

        add_response = self._json_post(
            f"/api/chat/channels/{self.channel.pk}/members/",
            {"user_ids": [self.outsider.pk], "role": "member"},
        )
        remove_response = self._json_delete(
            f"/api/chat/channels/{self.channel.pk}/members/{self.outsider.pk}/"
        )

        self.assertEqual(add_response.status_code, 201)
        self.assertEqual(remove_response.status_code, 200)
        self.assertFalse(
            ChatChannelMember.objects.filter(channel=self.channel, user=self.outsider).exists()
        )
