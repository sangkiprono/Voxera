from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

from .security import decrypt_totp_secret, encrypt_totp_secret


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")

        email = self.normalize_email(email).strip().lower()
        extra_fields.setdefault("email_verified", True)
        user = self.model(email=email, **extra_fields)

        if password is not None:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("A superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("A superuser must have is_superuser=True.")

        return self.create_user(email, password=password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class MFADevice(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="mfa_device"
    )
    encrypted_secret = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_verified_step = models.BigIntegerField(default=-1)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_secret(self, secret):
        self.encrypted_secret = encrypt_totp_secret(secret)

    def get_secret(self):
        return decrypt_totp_secret(self.encrypted_secret)

    @property
    def is_confirmed(self):
        return self.confirmed_at is not None


class MFALoginChallenge(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="mfa_login_challenges"
    )
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_usable(self):
        return (
            self.consumed_at is None
            and self.expires_at > timezone.now()
            and self.attempts < 5
        )


class MFARecoveryCode(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="mfa_recovery_codes"
    )
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AccountSecurityToken(models.Model):
    class Purpose(models.TextChoices):
        EMAIL_VERIFICATION = "email_verification", "Email verification"
        PASSWORD_RESET = "password_reset", "Password reset"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="security_tokens"
    )
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_usable(self):
        return self.consumed_at is None and self.expires_at > timezone.now()
