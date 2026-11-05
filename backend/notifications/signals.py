from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification, NotificationEmail


@receiver(post_save, sender=Notification)
def queue_notification_email(sender, instance, created, **kwargs):
    if created and settings.NOTIFICATIONS_EMAIL_ENABLED:
        NotificationEmail.objects.create(notification=instance)
