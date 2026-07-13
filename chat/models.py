from pathlib import Path
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from tasks.models import validate_attachment_extension, validate_attachment_size


class ChatUserPresence(models.Model):
    ONLINE_TIMEOUT_SECONDS = 35

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_presence",
    )
    is_available = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__name"]

    def __str__(self):
        return f"{self.user} - {'online' if self.is_online else 'offline'}"

    @property
    def is_online(self):
        if not self.is_available:
            return False
        threshold = timezone.now() - timedelta(
            seconds=self.ONLINE_TIMEOUT_SECONDS
        )
        return self.last_seen_at >= threshold

    def set_online(self, online=True):
        self.is_available = online
        self.last_seen_at = timezone.now()
        self.save(update_fields=["is_available", "last_seen_at", "updated_at"])


def chat_attachment_upload_path(instance, filename):
    return f"chat_attachments/{instance.message_id}/{filename}"


class ChatChannel(models.Model):
    class ChannelType(models.TextChoices):
        TEAM = "team", "Equipe"
        PROJECT = "project", "Projet"
        SUPPORT = "support", "Support"
        PRIVATE = "private", "Prive"
        DIRECT = "direct", "Direct"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    channel_type = models.CharField(
        max_length=20,
        choices=ChannelType.choices,
        default=ChannelType.TEAM,
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_channels",
    )
    task = models.ForeignKey(
        "tasks.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_channels",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_chat_channels",
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"#{self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "channel"
            slug = base_slug
            index = 2
            while ChatChannel.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{index}"
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)


class ChatChannelMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    channel = models.ForeignKey(ChatChannel, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_muted = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["user__name"]
        constraints = [
            models.UniqueConstraint(fields=["channel", "user"], name="unique_chat_channel_member")
        ]

    def __str__(self):
        return f"{self.user} in {self.channel}"

    @property
    def can_send(self):
        return self.role in {self.Role.OWNER, self.Role.ADMIN, self.Role.MEMBER}

    @property
    def can_admin(self):
        return self.role in {self.Role.OWNER, self.Role.ADMIN}


class ChatMessage(models.Model):
    class MessageType(models.TextChoices):
        TEXT = "text", "Texte"
        SYSTEM = "system", "Systeme"
        ATTACHMENT = "attachment", "Piece jointe"

    channel = models.ForeignKey(ChatChannel, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="chat_messages",
    )
    parent_message = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    content = models.TextField(blank=True)
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.TEXT,
    )
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["channel", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
        ]

    def __str__(self):
        return f"Message {self.pk} in {self.channel}"

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class ChatMessageAttachment(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(
        upload_to=chat_attachment_upload_path,
        validators=[validate_attachment_size, validate_attachment_extension],
    )
    original_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=40, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="chat_attachments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.original_name or self.file.name

    def save(self, *args, **kwargs):
        if self.file and not self.original_name:
            self.original_name = Path(self.file.name).name
        if self.file and not self.file_size:
            self.file_size = self.file.size
        if self.original_name and not self.file_type:
            self.file_type = Path(self.original_name).suffix.lower().lstrip(".").upper() or "FILE"
        super().save(*args, **kwargs)


class ChatMessageReaction(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_reactions",
    )
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["emoji", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["message", "user", "emoji"], name="unique_chat_reaction")
        ]

    def __str__(self):
        return f"{self.emoji} by {self.user}"


class ChatMessageReadReceipt(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="read_receipts")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_read_receipts",
    )
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-read_at"]
        constraints = [
            models.UniqueConstraint(fields=["message", "user"], name="unique_chat_read_receipt")
        ]

    def __str__(self):
        return f"{self.user} read message {self.message_id}"


class ChatMention(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="mentions")
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_mentions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["mentioned_user__name"]
        constraints = [
            models.UniqueConstraint(fields=["message", "mentioned_user"], name="unique_chat_mention")
        ]

    def __str__(self):
        return f"{self.mentioned_user} mentioned in {self.message_id}"


class ChatChannelTask(models.Model):
    channel = models.ForeignKey(ChatChannel, on_delete=models.CASCADE, related_name="task_links")
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="chat_links")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_chat_task_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["channel", "task"], name="unique_chat_channel_task")
        ]

    def __str__(self):
        return f"{self.task} linked to {self.channel}"
