import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from .models import MFADevice, MFALoginChallenge, MFARecoveryCode
from .mfa import consume_mfa_code
from .security import (
    encrypt_totp_secret,
    matching_totp_step,
    new_totp_secret,
    provisioning_uri,
)
from .serializers import (
    LoginSerializer,
    MFALoginSerializer,
    MFASetupConfirmSerializer,
    RegistrationSerializer,
    UserSerializer,
)


def _new_recovery_codes():
    codes = []
    for _ in range(10):
        raw_code = secrets.token_hex(16).upper()
        codes.append("-".join(raw_code[offset : offset + 8] for offset in range(0, 32, 8)))
    return codes


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        device = MFADevice.objects.filter(
            user=user, confirmed_at__isnull=False
        ).first()
        if device is not None:
            challenge_id = secrets.token_urlsafe(32)
            MFALoginChallenge.objects.create(
                user=user,
                token_digest=hashlib.sha256(challenge_id.encode()).hexdigest(),
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            return Response(
                {"mfa_required": True, "challenge_id": challenge_id},
                status=status.HTTP_202_ACCEPTED,
            )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


class MFALoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa"

    def post(self, request):
        serializer = MFALoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        challenge_digest = hashlib.sha256(
            serializer.validated_data["challenge_id"].encode()
        ).hexdigest()
        code = serializer.validated_data["code"]
        response = None

        with transaction.atomic():
            challenge = (
                MFALoginChallenge.objects.select_for_update()
                .select_related("user")
                .filter(token_digest=challenge_digest)
                .first()
            )
            if challenge is None or not challenge.is_usable:
                return Response(
                    {"detail": "This sign-in challenge is invalid or expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            challenge.attempts += 1
            challenge.save(update_fields=["attempts"])
            valid = consume_mfa_code(challenge.user, code)
            if not valid:
                response = Response(
                    {"detail": "The authenticator or recovery code is invalid."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            else:
                challenge.consumed_at = timezone.now()
                challenge.save(update_fields=["consumed_at"])
                token, _ = Token.objects.get_or_create(user=challenge.user)
                response = Response(
                    {
                        "token": token.key,
                        "user": UserSerializer(challenge.user).data,
                    }
                )
        return response


class MFASetupView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa"

    def post(self, request):
        secret = new_totp_secret()
        device, created = MFADevice.objects.get_or_create(
            user=request.user,
            defaults={"encrypted_secret": encrypt_totp_secret(secret)},
        )
        if device is not None and device.is_confirmed:
            return Response(
                {"detail": "An authenticator is already configured."},
                status=status.HTTP_409_CONFLICT,
            )
        if not created:
            secret = device.get_secret()
        return Response(
            {
                "secret": secret,
                "provisioning_uri": provisioning_uri(secret, request.user.email),
            }
        )


class MFASetupConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa"

    def post(self, request):
        serializer = MFASetupConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        recovery_codes = []

        with transaction.atomic():
            device = (
                MFADevice.objects.select_for_update()
                .filter(user=request.user)
                .first()
            )
            if device is None or device.is_confirmed:
                return Response(
                    {"detail": "Start authenticator setup before confirming it."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            matched_step = matching_totp_step(device.get_secret(), code)
            if matched_step is None or matched_step <= device.last_verified_step:
                return Response(
                    {"detail": "The authenticator code is invalid or expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()
            device.confirmed_at = now
            device.last_verified_step = matched_step
            device.save(update_fields=["confirmed_at", "last_verified_step"])

            recovery_codes = _new_recovery_codes()
            MFARecoveryCode.objects.bulk_create(
                [
                    MFARecoveryCode(
                        user=request.user,
                        code_hash=hashlib.sha256(
                            code.replace("-", "").encode()
                        ).hexdigest(),
                    )
                    for code in recovery_codes
                ]
            )
            Token.objects.filter(user=request.user).delete()
            token = Token.objects.create(user=request.user)

        return Response(
            {
                "token": token.key,
                "user": UserSerializer(request.user).data,
                "recovery_codes": recovery_codes,
            }
        )


class LogoutView(APIView):
    def post(self, request):
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
