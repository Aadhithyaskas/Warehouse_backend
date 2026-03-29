from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.apps import apps
from .models import Role, Permission


@receiver(post_save, sender=Role)
def assign_default_permissions(sender, instance, created, **kwargs):

    if not created:
        return

    if instance.name == "inventory_manager":
        for action in ["create", "read", "update", "delete"]:
            Permission.objects.get_or_create(
                role=instance,
                model_name="inventory",
                action=action
            )

    elif instance.name == "quality_assistant":
        Permission.objects.get_or_create(
            role=instance,
            model_name="quality",
            action="read"
        )


