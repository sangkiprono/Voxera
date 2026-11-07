import hmac

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
import pyotp


def _cipher():
    try:
        return Fernet(settings.MFA_ENCRYPTION_KEY.encode("ascii"))
    except (AttributeError, UnicodeEncodeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "MFA_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


def encrypt_totp_secret(secret):
    return _cipher().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(encrypted_secret):
    try:
        return _cipher().decrypt(encrypted_secret.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ImproperlyConfigured(
            "The stored MFA secret could not be decrypted; verify MFA_ENCRYPTION_KEY."
        ) from exc


def new_totp_secret():
    return pyotp.random_base32()


def provisioning_uri(secret, email):
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Voxera")


def matching_totp_step(secret, code, now=None):
    now = now or timezone.now()
    totp = pyotp.TOTP(secret)
    current_step = totp.timecode(now)
    for step in (current_step, current_step - 1):
        expected = totp.at(step * totp.interval)
        if hmac.compare_digest(expected, code):
            return step
    return None
