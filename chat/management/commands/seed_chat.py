from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from chat.models import ChatChannel, ChatChannelMember, ChatChannelTask, ChatMessage
from tasks.models import Task

User = get_user_model()


class Command(BaseCommand):
    help = "Create sample Team Chat data for the Support IT channel."

    def handle(self, *args, **options):
        users = {
            user.name: user
            for user in User.objects.filter(
                name__in=["Haytam Hafid", "Mohamed Ghayati", "Adnan Motawakil"],
                is_active=True,
            )
        }
        fallback_user = User.objects.filter(is_active=True).order_by("id").first()
        if not fallback_user:
            self.stdout.write(self.style.WARNING("No active user found. Seed skipped."))
            return

        owner = users.get("Haytam Hafid") or fallback_user
        channel, _created = ChatChannel.objects.get_or_create(
            slug="support-it",
            defaults={
                "name": "Support IT",
                "description": "Canal equipe pour les demandes et incidents IT.",
                "channel_type": ChatChannel.ChannelType.SUPPORT,
                "created_by": owner,
            },
        )

        for role_name, user in users.items():
            role = ChatChannelMember.Role.OWNER if user == owner else ChatChannelMember.Role.MEMBER
            ChatChannelMember.objects.get_or_create(channel=channel, user=user, defaults={"role": role})
        ChatChannelMember.objects.get_or_create(
            channel=channel,
            user=owner,
            defaults={"role": ChatChannelMember.Role.OWNER},
        )

        samples = [
            (
                users.get("Mohamed Ghayati") or owner,
                "Bonjour l'equipe\nMerci de verifier l'acces au serveur de test pour @Adnan Motawakil.\nIl rencontre une erreur 403 depuis ce matin.",
            ),
            (
                users.get("Adnan Motawakil") or owner,
                "Merci @Mohamed Ghayati, je regarde ca tout de suite.\nJe vous tiens au courant.",
            ),
            (
                owner,
                "Voici les journaux d'erreurs que j'ai recuperes sur le serveur.\nCa peut aider a diagnostiquer le probleme.",
            ),
        ]
        for sender, content in samples:
            ChatMessage.objects.get_or_create(channel=channel, sender=sender, content=content)

        task_specs = [
            ("Acces serveur de test", Task.Priority.CRITICAL),
            ("Mise a jour des droits VPN", Task.Priority.MEDIUM),
        ]
        for title, priority in task_specs:
            task, _created = Task.objects.get_or_create(
                title=title,
                defaults={
                    "description": "Tache creee pour tester le contexte du chat equipe.",
                    "priority": priority,
                    "assigned_to": users.get("Adnan Motawakil") or owner,
                    "created_by": owner,
                },
            )
            ChatChannelTask.objects.get_or_create(channel=channel, task=task, defaults={"created_by": owner})

        self.stdout.write(self.style.SUCCESS(f"Seeded chat channel #{channel.name} ({channel.pk})."))
