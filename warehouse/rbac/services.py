import random
from .models import UserRole, Permission
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from .models import OTP
import string

def generate_random_password(length=10):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))



def has_permission(user, model_name, action):

    if not user.is_authenticated:
        return False

    # Superuser bypass (very important)
    if user.is_superuser:
        return True

    try:
        user_role = UserRole.objects.select_related("role").get(user=user)
    except UserRole.DoesNotExist:
        return False

    return Permission.objects.filter(
        role=user_role.role,
        model_name=model_name,
        action=action
    ).exists()


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email, purpose):

    otp_code = generate_otp()
    expiry = timezone.now() + timedelta(minutes=5)
    print(otp_code)

    OTP.objects.create(
        email=email,
        otp_code=otp_code,
        purpose=purpose,
        expiry_time=expiry,
        is_used=False
    )

    send_mail(
        subject="Your OTP Code",
        message=f"Your OTP is {otp_code}. It expires in 5 minutes.",
        from_email=None,
        recipient_list=[email],
    )
