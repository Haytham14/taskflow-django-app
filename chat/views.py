import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from tasks.models import Task

from .models import (
    ChatChannel,
    ChatChannelMember,
    ChatChannelTask,
    ChatMention,
    ChatMessage,
    ChatMessageAttachment,
    ChatMessageReaction,
    ChatMessageReadReceipt,
    ChatUserPresence,
)

User = get_user_model()


def _json(payload, status=200, safe=True):
    return JsonResponse(
        payload,
        status=status,
        safe=safe,
        json_dumps_params={"ensure_ascii": False},
    )


def _error(message, status=400):
    return _json({"ok": False, "error": message}, status=status)


def _request_data(request):
    content_type = request.content_type or ""
    if content_type.startswith("application/json"):
        if not request.body:
            return {}
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
    return request.POST


def _get_values(data, *keys):
    values = []
    for key in keys:
        if hasattr(data, "getlist"):
            values.extend(data.getlist(key))
        else:
            value = data.get(key)
            if isinstance(value, list):
                values.extend(value)
            elif value not in (None, ""):
                values.extend(str(value).split(","))
    return [value for value in values if str(value).strip()]


def _parse_id_list(data, *keys):
    ids = []
    for value in _get_values(data, *keys):
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _uploaded_files(request):
    files = []
    for key in ("attachments", "attachments[]", "files", "file"):
        files.extend(request.FILES.getlist(key))
    return files


def _initials(user):
    if not user:
        return "?"
    name = (user.name or user.email or "").strip()
    parts = name.split()
    if parts:
        return "".join(part[:1] for part in parts[:2]).upper()
    return (user.email[:1] or "?").upper()


def _user_payload(user):
    if not user:
        return {
            "id": None,
            "name": "Utilisateur supprime",
            "email": "",
            "initials": "?",
            "is_online": False,
            "presence": "offline",
            "last_seen_at": None,
        }
    presence = getattr(user, "chat_presence", None)
    is_online = bool(presence and presence.is_online)
    return {
        "id": user.pk,
        "name": user.name,
        "email": user.email,
        "initials": _initials(user),
        "is_online": is_online,
        "presence": "online" if is_online else "offline",
        "last_seen_at": (
            presence.last_seen_at.isoformat() if presence else None
        ),
    }


def _member_for(user, channel):
    return (
        ChatChannelMember.objects.select_related("user", "channel")
        .filter(channel=channel, user=user)
        .first()
    )


def _channel_or_404(channel_id):
    return get_object_or_404(
        ChatChannel.objects.select_related("project", "task", "created_by"),
        pk=channel_id,
    )


def _require_channel_member(user, channel):
    membership = _member_for(user, channel)
    if not membership:
        return None, _error("Vous n'avez pas acces a ce canal.", status=403)
    return membership, None


def _is_channel_admin(user, membership):
    return bool(membership and (membership.can_admin or user.is_admin_role))


def _can_send_message(channel, membership):
    return bool(membership and membership.can_send and not channel.is_archived)


def _reaction_summary(message, user):
    counts = {}
    reacted_by_me = set()
    for reaction in message.reactions.select_related("user"):
        counts[reaction.emoji] = counts.get(reaction.emoji, 0) + 1
        if reaction.user_id == user.id:
            reacted_by_me.add(reaction.emoji)
    return [
        {"emoji": emoji, "count": count, "reacted_by_me": emoji in reacted_by_me}
        for emoji, count in sorted(counts.items())
    ]


def _serialize_attachment(attachment):
    return {
        "id": attachment.pk,
        "original_name": attachment.original_name,
        "file_type": attachment.file_type,
        "file_size": attachment.file_size,
        "url": f"/api/chat/attachments/{attachment.pk}/download/",
        "uploaded_by": _user_payload(attachment.uploaded_by),
        "created_at": attachment.created_at.isoformat(),
    }


def _serialize_message(message, user):
    content = "Message supprimé" if message.is_deleted else message.content
    read_by = [
        {
            **_user_payload(receipt.user),
            "read_at": receipt.read_at.isoformat(),
        }
        for receipt in message.read_receipts.all()
        if receipt.user_id != message.sender_id
    ]
    return {
        "id": message.pk,
        "channel": message.channel_id,
        "sender": _user_payload(message.sender),
        "parent_message": message.parent_message_id,
        "content": content,
        "message_type": message.message_type,
        "is_edited": message.is_edited,
        "is_deleted": message.is_deleted,
        "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
        "attachments": [_serialize_attachment(item) for item in message.attachments.all()],
        "reactions": _reaction_summary(message, user),
        "read_by": read_by,
        "mentions": [
            _user_payload(mention.mentioned_user) for mention in message.mentions.select_related("mentioned_user")
        ],
    }


def _last_message_payload(channel):
    message = (
        channel.messages.select_related("sender")
        .filter(is_deleted=False)
        .order_by("-created_at")
        .first()
    )
    if not message:
        return None
    return {
        "id": message.pk,
        "content": message.content,
        "sender_id": message.sender_id,
        "sender": message.sender.name if message.sender else "Utilisateur supprime",
        "created_at": message.created_at.isoformat(),
    }


def _unread_count(channel, user):
    return (
        channel.messages.filter(is_deleted=False)
        .exclude(sender=user)
        .exclude(read_receipts__user=user)
        .count()
    )


def _serialize_channel(channel, user, include_members=False):
    direct_user = None
    display_name = channel.name
    if channel.channel_type == ChatChannel.ChannelType.DIRECT:
        direct_membership = (
            channel.memberships.select_related("user", "user__chat_presence")
            .exclude(user=user)
            .order_by("user__name")
            .first()
        )
        if direct_membership:
            direct_user = _user_payload(direct_membership.user)
            display_name = direct_user["name"]

    payload = {
        "id": channel.pk,
        "name": channel.name,
        "display_name": display_name,
        "slug": channel.slug,
        "description": channel.description,
        "channel_type": channel.channel_type,
        "direct_user": direct_user,
        "project": channel.project_id,
        "task": channel.task_id,
        "is_archived": channel.is_archived,
        "created_by": _user_payload(channel.created_by),
        "created_at": channel.created_at.isoformat(),
        "updated_at": channel.updated_at.isoformat(),
        "unread_count": _unread_count(channel, user),
        "members_count": channel.memberships.count(),
        "last_message": _last_message_payload(channel),
    }
    if include_members:
        payload["members"] = [
            _serialize_member(member)
            for member in channel.memberships.select_related(
                "user", "user__chat_presence"
            )
        ]
    return payload


def _total_unread_count(user):
    channel_ids = ChatChannelMember.objects.filter(
        user=user,
        channel__is_archived=False,
    ).values_list("channel_id", flat=True)
    return (
        ChatMessage.objects.filter(channel_id__in=channel_ids, is_deleted=False)
        .exclude(sender=user)
        .exclude(read_receipts__user=user)
        .count()
    )


def _find_direct_channel(user, target_user):
    channels = (
        ChatChannel.objects.filter(
            channel_type=ChatChannel.ChannelType.DIRECT,
            is_archived=False,
            memberships__user=user,
        )
        .prefetch_related("memberships")
        .distinct()
    )
    expected_member_ids = {user.pk, target_user.pk}
    for channel in channels:
        member_ids = {membership.user_id for membership in channel.memberships.all()}
        if member_ids == expected_member_ids:
            return channel
    return None


def _serialize_member(member):
    return {
        "id": member.pk,
        "channel": member.channel_id,
        "user": _user_payload(member.user),
        "role": member.role,
        "is_muted": member.is_muted,
        "joined_at": member.joined_at.isoformat(),
        "last_seen_at": member.last_seen_at.isoformat() if member.last_seen_at else None,
    }


def _serialize_task(task):
    return {
        "id": task.pk,
        "code": f"TASK-{task.pk:04d}",
        "title": task.title,
        "status": task.status,
        "status_display": task.get_status_display(),
        "priority": task.priority,
        "priority_display": task.get_priority_display(),
        "project": task.project_id,
        "assigned_to": _user_payload(task.assignees.first()),
        "assignees": [_user_payload(user) for user in task.assignees.all()],
        "created_at": task.created_at.isoformat(),
    }


def _sync_mentions(message):
    ChatMention.objects.filter(message=message).delete()
    content = (message.content or "").lower()
    if not content:
        return

    mentioned_ids = set()
    for user in User.objects.filter(is_active=True):
        name = (user.name or "").strip()
        aliases = [name, user.email.split("@", 1)[0]]
        if name:
            aliases.append(name.split()[0])
        for alias in aliases:
            alias = alias.strip()
            if alias and f"@{alias.lower()}" in content:
                mentioned_ids.add(user.pk)
                break

    ChatMention.objects.bulk_create(
        [ChatMention(message=message, mentioned_user_id=user_id) for user_id in mentioned_ids],
        ignore_conflicts=True,
    )


def _save_attachments(message, request):
    attachments = []
    for uploaded_file in _uploaded_files(request):
        attachment = ChatMessageAttachment(
            message=message,
            file=uploaded_file,
            original_name=uploaded_file.name,
            file_type=Path(uploaded_file.name).suffix.lower().lstrip(".").upper() or "FILE",
            file_size=uploaded_file.size,
            uploaded_by=message.sender,
        )
        attachment.full_clean()
        attachment.save()
        attachments.append(attachment)
    return attachments


@login_required
@require_http_methods(["GET", "POST"])
def channels(request):
    if request.method == "GET":
        memberships = ChatChannelMember.objects.filter(user=request.user, channel__is_archived=False)
        channel_ids = memberships.values_list("channel_id", flat=True)
        queryset = (
            ChatChannel.objects.select_related("project", "task", "created_by")
            .filter(pk__in=channel_ids)
            .order_by("name")
        )
        return _json([_serialize_channel(channel, request.user) for channel in queryset], safe=False)

    data = _request_data(request)
    name = (data.get("name") or "").strip()
    if not name:
        return _error("Le nom du canal est obligatoire.")

    channel_type = data.get("channel_type") or ChatChannel.ChannelType.TEAM
    if channel_type not in ChatChannel.ChannelType.values:
        return _error("Type de canal invalide.")

    channel = ChatChannel.objects.create(
        name=name,
        description=(data.get("description") or "").strip(),
        channel_type=channel_type,
        project_id=data.get("project_id") or None,
        task_id=data.get("task_id") or None,
        created_by=request.user,
    )
    ChatChannelMember.objects.create(
        channel=channel,
        user=request.user,
        role=ChatChannelMember.Role.OWNER,
    )

    member_ids = set(_parse_id_list(data, "member_ids", "member_ids[]", "members", "members[]"))
    member_ids.discard(request.user.pk)
    for user in User.objects.filter(pk__in=member_ids, is_active=True):
        ChatChannelMember.objects.get_or_create(channel=channel, user=user)

    return _json(_serialize_channel(channel, request.user, include_members=True), status=201)


@login_required
@require_http_methods(["GET"])
def unread_count(request):
    return _json({"unread_count": _total_unread_count(request.user)})


@login_required
@require_http_methods(["POST"])
def direct_conversation(request):
    data = _request_data(request)
    user_id = data.get("user_id")
    if not user_id:
        return _error("Utilisateur obligatoire.")

    target_user = get_object_or_404(User, pk=user_id, is_active=True)
    if target_user.pk == request.user.pk:
        return _error("Vous ne pouvez pas creer une conversation directe avec vous-meme.")

    channel = _find_direct_channel(request.user, target_user)
    if not channel:
        channel = ChatChannel.objects.create(
            name=f"{request.user.name} / {target_user.name}",
            description="Conversation directe",
            channel_type=ChatChannel.ChannelType.DIRECT,
            created_by=request.user,
        )
        ChatChannelMember.objects.create(
            channel=channel,
            user=request.user,
            role=ChatChannelMember.Role.OWNER,
        )
        ChatChannelMember.objects.create(
            channel=channel,
            user=target_user,
            role=ChatChannelMember.Role.MEMBER,
        )

    return _json(_serialize_channel(channel, request.user, include_members=True), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def channel_detail(request, channel_id):
    channel = _channel_or_404(channel_id)
    membership, response = _require_channel_member(request.user, channel)
    if response:
        return response

    if request.method == "GET":
        return _json(_serialize_channel(channel, request.user, include_members=True))

    if not request.user.is_admin_role:
        return _error("Seuls les administrateurs peuvent modifier ou supprimer ce canal.", status=403)

    if request.method == "DELETE":
        channel.is_archived = True
        channel.save(update_fields=["is_archived", "updated_at"])
        return _json({"ok": True, "is_archived": True})

    data = _request_data(request)
    for field in ("name", "description"):
        if field in data:
            setattr(channel, field, (data.get(field) or "").strip())
    if data.get("channel_type") in ChatChannel.ChannelType.values:
        channel.channel_type = data["channel_type"]
    if "project_id" in data:
        channel.project_id = data.get("project_id") or None
    if "task_id" in data:
        channel.task_id = data.get("task_id") or None
    if "is_archived" in data:
        channel.is_archived = bool(data.get("is_archived"))
    channel.save()
    return _json(_serialize_channel(channel, request.user, include_members=True))


@login_required
@require_http_methods(["GET", "POST"])
def channel_members(request, channel_id):
    channel = _channel_or_404(channel_id)
    membership, response = _require_channel_member(request.user, channel)
    if response:
        return response

    if request.method == "GET":
        members = channel.memberships.select_related(
            "user", "user__chat_presence"
        ).order_by("user__name")
        return _json([_serialize_member(member) for member in members], safe=False)

    if not request.user.is_admin_role:
        return _error("Seuls les administrateurs peuvent ajouter des membres.", status=403)

    data = _request_data(request)
    role = data.get("role") or ChatChannelMember.Role.MEMBER
    if role not in ChatChannelMember.Role.values:
        return _error("Role invalide.")

    user_ids = set(_parse_id_list(data, "user_id", "user_ids", "member_ids", "member_ids[]"))
    if not user_ids:
        return _error("Aucun utilisateur fourni.")

    members = []
    for user in User.objects.filter(pk__in=user_ids, is_active=True):
        member, _created = ChatChannelMember.objects.update_or_create(
            channel=channel,
            user=user,
            defaults={"role": role},
        )
        members.append(member)
    return _json([_serialize_member(member) for member in members], status=201, safe=False)


@login_required
@require_http_methods(["DELETE"])
def channel_member_detail(request, channel_id, user_id):
    channel = _channel_or_404(channel_id)
    membership, response = _require_channel_member(request.user, channel)
    if response:
        return response
    if not request.user.is_admin_role:
        return _error("Seuls les administrateurs peuvent retirer des membres.", status=403)

    deleted, _details = ChatChannelMember.objects.filter(channel=channel, user_id=user_id).delete()
    return _json({"ok": True, "deleted": bool(deleted)})


@login_required
@require_http_methods(["GET", "POST"])
def channel_messages(request, channel_id):
    channel = _channel_or_404(channel_id)
    membership, response = _require_channel_member(request.user, channel)
    if response:
        return response

    if request.method == "GET":
        try:
            page = max(1, int(request.GET.get("page", 1)))
            per_page = min(100, max(1, int(request.GET.get("per_page", 50))))
        except ValueError:
            return _error("Pagination invalide.")

        queryset = (
            channel.messages.select_related(
                "sender", "sender__chat_presence", "parent_message"
            )
            .prefetch_related(
                "attachments",
                "reactions",
                "mentions__mentioned_user",
                "read_receipts__user__chat_presence",
            )
            .order_by("-created_at")
        )
        total = queryset.count()
        start = (page - 1) * per_page
        messages = list(queryset[start : start + per_page])
        messages.reverse()
        return _json(
            {
                "results": [_serialize_message(message, request.user) for message in messages],
                "pagination": {"page": page, "per_page": per_page, "total": total},
            }
        )

    if not _can_send_message(channel, membership):
        return _error("Vous ne pouvez pas envoyer de message dans ce canal.", status=403)

    data = _request_data(request)
    content = (data.get("content") or "").strip()
    files = _uploaded_files(request)
    if not content and not files:
        return _error("Le message ou une piece jointe est obligatoire.")

    parent_message = None
    parent_id = data.get("parent_message_id") or data.get("parent_message")
    if parent_id:
        parent_message = get_object_or_404(ChatMessage, pk=parent_id, channel=channel)

    message_type = data.get("message_type") or (ChatMessage.MessageType.ATTACHMENT if files else ChatMessage.MessageType.TEXT)
    if message_type not in ChatMessage.MessageType.values:
        return _error("Type de message invalide.")

    message = ChatMessage.objects.create(
        channel=channel,
        sender=request.user,
        parent_message=parent_message,
        content=content,
        message_type=message_type,
    )
    try:
        _save_attachments(message, request)
    except ValidationError as exc:
        message.delete()
        return _error(exc.messages[0] if exc.messages else "Piece jointe invalide.")
    _sync_mentions(message)
    ChatMessageReadReceipt.objects.get_or_create(message=message, user=request.user)
    return _json(_serialize_message(message, request.user), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def message_detail(request, message_id):
    message = get_object_or_404(
        ChatMessage.objects.select_related(
            "channel", "sender", "sender__chat_presence"
        ).prefetch_related(
            "attachments",
            "reactions",
            "mentions__mentioned_user",
            "read_receipts__user__chat_presence",
        ),
        pk=message_id,
    )
    membership, response = _require_channel_member(request.user, message.channel)
    if response:
        return response

    if request.method == "GET":
        return _json(_serialize_message(message, request.user))

    if request.method == "PUT":
        if message.sender_id != request.user.id:
            return _error("Vous ne pouvez modifier que vos propres messages.", status=403)
        if message.channel.is_archived or message.is_deleted:
            return _error("Ce message ne peut plus etre modifie.", status=403)
        data = _request_data(request)
        content = (data.get("content") or "").strip()
        if not content:
            return _error("Le contenu du message est obligatoire.")
        message.content = content
        message.is_edited = True
        message.save(update_fields=["content", "is_edited", "updated_at"])
        _sync_mentions(message)
        return _json(_serialize_message(message, request.user))

    can_delete = message.sender_id == request.user.id or _is_channel_admin(request.user, membership)
    if not can_delete:
        return _error("Vous ne pouvez pas supprimer ce message.", status=403)
    if message.channel.is_archived and not _is_channel_admin(request.user, membership):
        return _error("Ce canal est archive.", status=403)
    message.soft_delete()
    return _json(_serialize_message(message, request.user))


@login_required
@require_http_methods(["POST", "DELETE"])
def message_reactions(request, message_id):
    message = get_object_or_404(ChatMessage.objects.select_related("channel"), pk=message_id)
    membership, response = _require_channel_member(request.user, message.channel)
    if response:
        return response
    if not _can_send_message(message.channel, membership):
        return _error("Vous ne pouvez pas reagir dans ce canal.", status=403)

    data = _request_data(request)
    emoji = (data.get("emoji") or "").strip()
    if not emoji:
        return _error("Emoji obligatoire.")

    if request.method == "POST":
        try:
            _reaction, created = ChatMessageReaction.objects.get_or_create(
                message=message,
                user=request.user,
                emoji=emoji,
            )
        except IntegrityError:
            created = False
        if not created:
            ChatMessageReaction.objects.filter(message=message, user=request.user, emoji=emoji).delete()
    else:
        ChatMessageReaction.objects.filter(message=message, user=request.user, emoji=emoji).delete()

    return _json({"ok": True, "reactions": _reaction_summary(message, request.user)})


@login_required
@require_http_methods(["POST"])
def mark_channel_read(request, channel_id):
    channel = _channel_or_404(channel_id)
    membership, response = _require_channel_member(request.user, channel)
    if response:
        return response

    now = timezone.now()
    receipts = [
        ChatMessageReadReceipt(message=message, user=request.user, read_at=now)
        for message in channel.messages.exclude(sender=request.user)
        if not ChatMessageReadReceipt.objects.filter(message=message, user=request.user).exists()
    ]
    ChatMessageReadReceipt.objects.bulk_create(receipts, ignore_conflicts=True)
    membership.last_seen_at = now
    membership.save(update_fields=["last_seen_at"])
    return _json({"ok": True, "marked_read": len(receipts), "last_seen_at": now.isoformat()})


@login_required
@require_http_methods(["GET", "POST"])
def linked_tasks(request, channel_id):
    channel = _channel_or_404(channel_id)
    membership, response = _require_channel_member(request.user, channel)
    if response:
        return response

    if request.method == "POST":
        if not _is_channel_admin(request.user, membership):
            return _error("Seuls les proprietaires et administrateurs peuvent lier une tache.", status=403)
        data = _request_data(request)
        task_id = data.get("task_id") or data.get("task")
        if not task_id:
            return _error("Tache obligatoire.")
        task = get_object_or_404(Task, pk=task_id)
        ChatChannelTask.objects.get_or_create(channel=channel, task=task, defaults={"created_by": request.user})

    task_ids = set(channel.task_links.values_list("task_id", flat=True))
    if channel.project_id:
        task_ids.update(Task.objects.filter(project=channel.project).values_list("id", flat=True))
    if channel.task_id:
        task_ids.add(channel.task_id)

    tasks = Task.objects.select_related("assigned_to", "project").prefetch_related("assignees").filter(pk__in=task_ids).order_by("-created_at")
    return _json([_serialize_task(task) for task in tasks], safe=False)


@login_required
@require_http_methods(["GET"])
def shared_files(request, channel_id):
    channel = _channel_or_404(channel_id)
    _membership, response = _require_channel_member(request.user, channel)
    if response:
        return response

    attachments = (
        ChatMessageAttachment.objects.select_related("message", "uploaded_by")
        .filter(message__channel=channel, message__is_deleted=False)
        .order_by("-created_at")
    )
    return _json([_serialize_attachment(attachment) for attachment in attachments], safe=False)


@login_required
@require_http_methods(["GET", "POST"])
def presence(request):
    if request.method == "GET":
        users = User.objects.filter(is_active=True).select_related(
            "chat_presence"
        ).order_by("name")
        return _json([_user_payload(user) for user in users], safe=False)

    data = _request_data(request)
    requested_status = (data.get("status") or "online").lower()
    online = requested_status != "offline"
    user_presence, _created = ChatUserPresence.objects.get_or_create(
        user=request.user
    )
    user_presence.set_online(online)
    return _json(_user_payload(request.user))


@login_required
@require_http_methods(["GET"])
def attachment_download(request, attachment_id):
    attachment = get_object_or_404(
        ChatMessageAttachment.objects.select_related("message", "message__channel"),
        pk=attachment_id,
    )
    _membership, response = _require_channel_member(request.user, attachment.message.channel)
    if response:
        return response

    filename = attachment.original_name or attachment.file.name.rsplit("/", 1)[-1]
    return FileResponse(attachment.file.open("rb"), as_attachment=False, filename=filename)
