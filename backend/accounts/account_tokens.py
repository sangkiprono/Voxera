import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import AccountSecurityToken

logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_LIFETIME = timedelta(hours=24)
PASSWORD_RESET_LIFETIME = timedelta(minutes=30)


def issue_account_token(user, purpose):
    lifetime = (
        EMAIL_VERIFICATION_LIFETIME
        if purpose == AccountSecurityToken.Purpose.EMAIL_VERIFICATION
        else PASSWORD_RESET_LIFETIME
    )
    raw_token = secrets.token_urlsafe(32)
    with transaction.atomic():
        AccountSecurityToken.objects.filter(
            user=user,
            purpose=purpose,
            consumed_at__isnull=True,
        ).update(consumed_at=timezone.now())
        AccountSecurityToken.objects.create(
            user=user,
            purpose=purpose,
            token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
            expires_at=timezone.now() + lifetime,
        )
    return raw_token


def send_account_action_email(user, purpose, raw_token):
    if purpose == AccountSecurityToken.Purpose.EMAIL_VERIFICATION:
        query_name = "verify_email"
        subject = "Verify your Voxera email address"
        instruction = "Confirm your email address"
    else:
        query_name = "reset_password"
        subject = "Reset your Voxera password"
        instruction = "Choose a new password"
    link = f"{settings.FRONTEND_BASE_URL}/?{query_name}={raw_token}"
    sent = send_mail(
        subject,
        f"{instruction} using this one-time link (expires soon):\n\n{link}\n",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
    if sent != 1:
        raise RuntimeError("The account-action email could not be sent.")
    return True


def find_usable_account_token(raw_token, purpose):
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    return (
        AccountSecurityToken.objects.select_for_update()
        .select_related("user")
        .filter(
            token_digest=digest,
            purpose=purpose,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
