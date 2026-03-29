from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Role, UserRole, OTP, WMSAdmin

User = get_user_model()


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']
        
class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    role = serializers.CharField()
    otp = serializers.CharField()

class LoginSerializer(serializers.Serializer):
    user_id = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

class WMSAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = WMSAdmin
        fields = ['username', 'email', 'password', 'role', 'admin_id']
        read_only_fields = ['admin_id'] # This ensures 'self.admin_id' is None when save() starts

class AdminLoginSerializer(serializers.Serializer):

    username = serializers.CharField()
    password = serializers.CharField()