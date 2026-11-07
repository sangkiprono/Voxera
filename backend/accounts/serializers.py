from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    mfa_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "email_verified",
            "mfa_enrolled",
        )
        read_only_fields = ("id", "email", "email_verified")

    def get_mfa_enrolled(self, user):
        return hasattr(user, "mfa_device") and user.mfa_device.is_confirmed


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "password")
        read_only_fields = ("id",)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with this email address already exists."
            )
        return value

    def validate(self, attrs):
        user = User(
            email=attrs["email"],
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        validate_password(attrs["password"], user)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(
            email=validated_data["email"],
            password=password,
            email_verified=False,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        return value.strip().lower()


class MFACodeSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Za-z0-9-]{6,40}$", trim_whitespace=True)

    def validate_code(self, value):
        return value.replace("-", "").upper()


class MFALoginSerializer(MFACodeSerializer):
    challenge_id = serializers.CharField(max_length=64)


class MFASetupConfirmSerializer(MFACodeSerializer):
    code = serializers.RegexField(r"^\d{6}$", trim_whitespace=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_password(self, value):
        validate_password(value)
        return value
