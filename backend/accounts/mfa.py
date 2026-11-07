import hashlib

from django.utils import timezone

from .models import MFADevice, MFARecoveryCode
from .security import matching_totp_step


def normalize_mfa_code(code):
    return code.strip().replace("-", "").upper()


def consume_mfa_code(user, code):
    code = normalize_mfa_code(code)
    device = (
        MFADevice.objects.select_for_update()
        .filter(user=user, confirmed_at__isnull=False)
        .first()
    )
    if device is None:
        return False

    matched_step = matching_totp_step(device.get_secret(), code)
    if matched_step is not None and matched_step > device.last_verified_step:
        device.last_verified_step = matched_step
        device.save(update_fields=["last_verified_step"])
        return True

    recovery = (
        MFARecoveryCode.objects.select_for_update()
        .filter(
            user=user,
            code_hash=hashlib.sha256(code.encode()).hexdigest(),
            used_at__isnull=True,
        )
        .first()
    )
    if recovery is None:
        return False
    recovery.used_at = timezone.now()
    recovery.save(update_fields=["used_at"])
    return True
