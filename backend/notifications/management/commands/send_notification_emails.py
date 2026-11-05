import logging
import smtplib
from datetime import timedelta

from django.conf import settings
from django.core.mail import BadHeaderError, send_mail
from django.core.management.base import BaseCommand
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from notifications.models import NotificationEmail

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
STALE_DELIVERY_AFTER = timedelta(minutes=30)


class Command(BaseCommand):
    help = "Send queued Voxera notification emails and record delivery results."

    def handle(self, *args, **options):
        stale_before = timezone.now() - STALE_DELIVERY_AFTER
        deliveries = NotificationEmail.objects.filter(
            attempts__lt=MAX_ATTEMPTS
        ).select_related(
            "notification__recipient",
            "notification__actor",
        )
        candidate_ids = list(
            deliveries.filter(
                status__in=(
                    NotificationEmail.Status.PENDING,
                    NotificationEmail.Status.FAILED,
                )
            )
            .values_list("pk", flat=True)
        )
        candidate_ids.extend(
            deliveries.filter(
                status=NotificationEmail.Status.SENDING,
                last_attempt_at__lt=stale_before,
            ).values_list("pk", flat=True)
        )
        sent = 0
        failed = 0

        for delivery_id in candidate_ids:
            with transaction.atomic():
                delivery = (
                    NotificationEmail.objects.select_for_update()
                    .filter(pk=delivery_id)
                    .first()
                )
                if (
                    delivery is None
                    or delivery.attempts >= MAX_ATTEMPTS
                    or delivery.status == NotificationEmail.Status.SENT
                    or (
                        delivery.status == NotificationEmail.Status.SENDING
                        and delivery.last_attempt_at is not None
                        and delivery.last_attempt_at >= stale_before
                    )
                ):
                    continue
                delivery.status = NotificationEmail.Status.SENDING
                delivery.attempts += 1
                delivery.last_attempt_at = timezone.now()
                delivery.save(
                    update_fields=("status", "attempts", "last_attempt_at")
                )
            notification = delivery.notification
            actor_name = (
                notification.actor.get_full_name() or "A Voxera member"
                if notification.actor_id
                else "Voxera"
            )
            body = (
                f"Hello {notification.recipient.get_full_name() or 'Voxera member'},\n\n"
                f"{actor_name}: {notification.message}\n\n"
                "Sign in to Voxera to view this update."
            )
            try:
                delivered = send_mail(
                    subject=f"Voxera: {notification.message}",
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[notification.recipient.email],
                    fail_silently=False,
                )
                if delivered != 1:
                    delivery.status = NotificationEmail.Status.FAILED
                    delivery.last_error = "Email backend did not confirm delivery."
                    delivery.save(update_fields=("status", "last_error"))
                    failed += 1
                    logger.error(
                        "Notification email %s was not accepted by the email backend.",
                        delivery.pk,
                    )
                    continue
            except (
                BadHeaderError,
                ImproperlyConfigured,
                OSError,
                smtplib.SMTPException,
            ) as error:
                delivery.status = NotificationEmail.Status.FAILED
                delivery.last_error = str(error)[:500]
                delivery.save(update_fields=("status", "last_error"))
                failed += 1
                logger.exception("Could not send notification email %s.", delivery.pk)
                continue

            delivery.status = NotificationEmail.Status.SENT
            delivery.sent_at = timezone.now()
            delivery.last_error = ""
            delivery.save(update_fields=("status", "sent_at", "last_error"))
            sent += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Notification emails sent: {sent}; failed: {failed}; "
                f"retry limit: {MAX_ATTEMPTS}."
            )
        )
