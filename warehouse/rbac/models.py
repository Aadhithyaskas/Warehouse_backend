from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction, IntegrityError

class Role(models.Model):

    ROLE_CHOICES = (
        ("inventory_manager", "Inventory Manager"),
        ("quality_assistant", "Quality Assistant"),
        ("finance_director","Finance Director"),
        ("manager", "Manager"),
        ("supervisor","Supervisor")
    )

    name = models.CharField(max_length=50, choices=ROLE_CHOICES, unique=True)

    def __str__(self):
        return self.get_name_display()

class WMSAdmin(models.Model):

    admin_id = models.CharField(
        max_length=10,
        primary_key=True,
        editable=False
    )

    username = models.CharField(max_length=150)

    role = models.CharField(
        max_length=20,
        default="admin"
    )

    email = models.EmailField(unique=True)

    password = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.admin_id:
            with transaction.atomic():
                # select_for_update() locks the row so no other request can generate the same ID simultaneously
                last_admin = WMSAdmin.objects.select_for_update().order_by("-admin_id").first()
                
                if last_admin:
                    # Use a regex or slice to ensure you only get the digits
                    last_id_str = last_admin.admin_id[3:] 
                    new_id = int(last_id_str) + 1
                else:
                    new_id = 1
                
                self.admin_id = f"ADM{new_id:04d}"
        super().save(*args, **kwargs)

class Permission(models.Model):
    ACTION_CHOICES = (
        ("create", "Create"),
        ("read", "Read"),
        ("update", "Update"),
        ("delete", "Delete"),
    )

    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    model_name = models.CharField(max_length=100)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    def __str__(self):
        return f"{self.role.name} - {self.model_name} - {self.action}"


class UserRole(models.Model):
    employee_id = models.CharField(max_length=100, unique=True, primary_key=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_role")
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    is_first_login = models.BooleanField(default=True)   # ADD THIS

    def __str__(self):
        return f"{self.user.username} - {self.role.name}"

    
    

User = get_user_model()

class OTP(models.Model):

    PURPOSE_CHOICES = (
        ("REGISTER", "Register"),
        ("RESET_PASSWORD", "Reset Password"),
        ("LOGIN", "Login"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField()
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    expiry_time = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.expiry_time

    def __str__(self):
        return f"{self.email} - {self.purpose}"



class LoginLogs(models.Model):

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # admin = models.ForeignKey(
    #     "WMSAdmin",
    #     on_delete=models.CASCADE,
    #     null=True,
    #     blank=True
    # )

    login_time = models.DateTimeField(auto_now_add=True)

    logout_time = models.DateTimeField(null=True, blank=True)

    ip_address = models.GenericIPAddressField()

    device_info = models.CharField(max_length=255)

    login_status = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user} - {self.login_time}"
