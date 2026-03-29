from django.contrib.auth import get_user_model, authenticate, login
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from django.core.mail import send_mail
from django.contrib.auth.models import User
from .models import WMSAdmin
from .models import Role, UserRole, OTP, LoginLogs
from .services import send_otp_email, generate_random_password
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    ResetPasswordSerializer,
    ForgotPasswordSerializer,
    WMSAdminSerializer,
    AdminLoginSerializer
)

User = get_user_model()


@ensure_csrf_cookie
def get_csrf_token(request):
    return JsonResponse({"message": "CSRF cookie set"})

class CreateAdminView(APIView):

    def post(self, request):

        serializer = WMSAdminSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()

            return Response({
                "message": "Admin created successfully",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):

    def post(self, request):

        log = LoginLogs.objects.filter(
            user=request.user,
            login_status=True
        ).last()

        if log:
            log.logout_time = now()
            log.save()

        return Response(
            {"message": "Logged out successfully"},
            status=status.HTTP_200_OK
        )


class ListEmployeeView(APIView):

    def get(self, request):

        employees = UserRole.objects.select_related('user', 'role').all()

        data = []

        for emp in employees:
            data.append({
                "id": emp.user.id,
                "employee_id": emp.employee_id,
                "username": emp.user.username,
                "email": emp.user.email,
                "role": emp.role.name,
                "is_first_login": emp.is_first_login
            })

        return Response(data, status=status.HTTP_200_OK)


class UpdateEmployeeView(APIView):

    def put(self, request, employee_id):

        try:
            user_role = UserRole.objects.select_related('user').get(employee_id=employee_id)
            user = user_role.user

            new_username = request.data.get("username", user.username)
            new_email = request.data.get("email", user.email)
            new_role_name = request.data.get("role")

            user.username = new_username
            user.email = new_email
            user.save()

            if new_role_name:
                role_obj, _ = Role.objects.get_or_create(name=new_role_name)
                user_role.role = role_obj
                user_role.save()

            return Response({
                "message": f"Employee {employee_id} updated successfully",
                "employee_id": employee_id
            }, status=status.HTTP_200_OK)

        except UserRole.DoesNotExist:
            return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)


class DeleteUserView(APIView):

    def delete(self, request, employee_id):

        try:
            userrole = UserRole.objects.get(employee_id=employee_id)
            user = userrole.user

            user.delete()

            return Response(
                {"message": "User deleted successfully"},
                status=200
            )

        except UserRole.DoesNotExist:
            return Response(
                {"error": "Employee not found"},
                status=404
            )


class AdminCreateUserView(APIView):

    def post(self, request):

        username = request.data.get("username")
        email = request.data.get("email")
        role_name = request.data.get("role")
        firstname = request.data.get("f_name")
        lastname = request.data.get("l_name")

        if not username or not email or not role_name:
            return Response({"error": "All fields required"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"error": "User already exists"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already registered"}, status=status.HTTP_400_BAD_REQUEST)

        # Prevent creating another admin
        if role_name.lower() == "admin":
            if UserRole.objects.filter(role__name="admin").exists():
                return Response(
                    {"error": "Admin already exists. Cannot create another Admin."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        password = generate_random_password()
        role, _ = Role.objects.get_or_create(name=role_name)

        last_user = User.objects.order_by('-id').first()
        next_id = last_user.id + 1 if last_user else 1
        custom_id = f"EMP{next_id:04d}"

        user = User.objects.create_user(
            username=username,
            first_name=firstname,
            last_name=lastname,
            email=email,
            password=password
        )

        user_role = UserRole.objects.create(
            employee_id=custom_id,
            user=user,
            role=role,
            is_first_login=True
        )

        send_mail(
            subject="Your Account Password",
            message=f"Your login password is: {password} and your Employee ID is: {user_role.employee_id}",
            from_email=None,
            recipient_list=[email],
        )

        return Response({
            "message": "User created and password sent",
            "employee_id": user_role.employee_id
        }, status=status.HTTP_201_CREATED)

from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import authenticate
from .models import WMSAdmin, UserRole, LoginLogs
class LoginView(APIView):

    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')

    def post(self, request):
        # Extract all possible identifiers from request
        email = request.data.get("email")
        password = request.data.get("password")
        employee_id = request.data.get("employee_id")
        admin_id = request.data.get("admin_id")  # Added this line

        ip = self.get_client_ip(request)
        device = request.META.get('HTTP_USER_AGENT')

        # -------- EMPLOYEE LOGIN --------
        if employee_id:
            if not password:
                return Response(
                    {"error": "Password required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                user_role = UserRole.objects.select_related(
                    'user', 'role'
                ).get(employee_id=employee_id)
                user = user_role.user
            except UserRole.DoesNotExist:
                return Response(
                    {"error": "Invalid employee ID"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Validate password (Django's hashed password check)
            if not user.check_password(password):
                return Response(
                    {"error": "Invalid credentials"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Founder Admin Login (Bypasses OTP as per your original logic)
            if user_role.role.name.lower() == "admin":
                return Response({
                    "message": "Founder Admin login successful",
                    "role": "FOUNDER_ADMIN"
                }, status=status.HTTP_200_OK)

            # Standard Employee Flow: Send OTP
            send_otp_email(user.email, "LOGIN")

            # Save login log
            LoginLogs.objects.create(
                user=user,
                ip_address=ip,
                device_info=device,
                login_status=False
            )

            return Response({
                "message": "OTP sent",
                "employee_id": employee_id,
                "email": user.email,
                "role": user_role.role.name
            }, status=status.HTTP_200_OK)


        # -------- ADMIN LOGIN --------
        elif admin_id or email:
            # 1. Validate that ALL required fields for Admin are present
            missing_fields = []
            if not admin_id:
                missing_fields.append("Admin ID")
            if not email:
                missing_fields.append("Email")
            if not password:
                missing_fields.append("Password")

            if missing_fields:
                return Response(
                    {"error": f"Missing required fields: {', '.join(missing_fields)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 2. Lookup the admin using BOTH email and admin_id
            admin = WMSAdmin.objects.filter(admin_id=admin_id, email=email).first()

            # 3. If no record matches both criteria
            if not admin:
                return Response(
                    {"error": "Admin not found or ID/Email mismatch"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 4. Check the password (Plain text check as per your model)
            if admin.password != password:
                return Response(
                    {"error": "Invalid credentials"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # 5. Success Flow: Send OTP
            send_otp_email(admin.email, "ADMIN_LOGIN")

            return Response({
                "message": "OTP sent to admin email",
                "admin_id": admin.admin_id,
                "email": admin.email,
                "role": admin.role
            }, status=status.HTTP_200_OK)


        # -------- INVALID REQUEST --------
        return Response(
            {"error": "Provide employee_id (employee) or email and admin_id (admin)"},
            status=status.HTTP_400_BAD_REQUEST
        )
class VerifyLoginOTPView(APIView):

    def post(self, request):

        otp_code = request.data.get("otp")

        if not otp_code:
            return Response({"error": "OTP is required"}, status=400)

        otp = OTP.objects.filter(
            otp_code=otp_code,
            is_used=False
        ).order_by("-created_at").first()

        if not otp:
            return Response({"error": "Invalid OTP"}, status=400)

        if otp.is_expired():
            return Response({"error": "OTP expired"}, status=400)

        email = otp.email

        # -------- CHECK ADMIN --------
        admin = WMSAdmin.objects.filter(email=email).first()

        if admin:

            otp.is_used = True
            otp.save()

            return Response({
                "message": "Admin login successful",
                "admin_id": admin.admin_id,
                "email": admin.email,
                "role": admin.role
            })

        # -------- CHECK EMPLOYEE --------
        user = User.objects.filter(email=email).first()

        if not user:
            return Response({"error": "User not found"}, status=404)

        user_role = UserRole.objects.get(user=user)

        otp.is_used = True
        otp.save()

        login(request, user)

        log = LoginLogs.objects.filter(
            user=user,
            login_status=False
        ).last()

        if log:
            log.login_status = True
            log.save()

        return Response({
            "message": "Login successful",
            "employee_id": user_role.employee_id,
            "role": user_role.role.name,
            "force_change_password": user_role.is_first_login
        })

class ForceChangePasswordView(APIView):

    def post(self, request):

        if not request.user.is_authenticated:
            return Response({"error": "Not authenticated"}, status=401)

        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if new_password != confirm_password:
            return Response({"error": "Passwords do not match"}, status=400)

        request.user.set_password(new_password)
        request.user.save()

        user_role = UserRole.objects.get(user=request.user)
        user_role.is_first_login = False
        user_role.save()

        return Response({"message": "Password changed successfully"})


class ForgotPasswordOTPView(APIView):

    def post(self, request):

        serializer = ForgotPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        email = serializer.validated_data["email"]

        if not User.objects.filter(email=email).exists() and not WMSAdmin.objects.filter(email=email).exists():

            return Response({"error": "User not found"}, status=404)

        send_otp_email(email, "RESET_PASSWORD")

        return Response({"message": "OTP sent for password reset"})

class ResetPasswordView(APIView):

    def post(self, request):

        serializer = ResetPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data

        otp = OTP.objects.filter(
            email=data["email"],
            otp_code=data["otp"],
            purpose="RESET_PASSWORD",
            is_used=False
        ).last()

        if not otp:
            return Response({"error": "Invalid OTP"}, status=400)

        if otp.is_expired():
            return Response({"error": "OTP expired"}, status=400)

        email = data["email"]

        # -------- EMPLOYEE PASSWORD RESET --------
        user = User.objects.filter(email=email).first()

        if user:
            user.set_password(data["new_password"])
            user.save()

            otp.is_used = True
            otp.save()

            return Response({"message": "Employee password reset successful"})


        # -------- ADMIN PASSWORD RESET --------
        admin = WMSAdmin.objects.filter(email=email).first()

        if admin:
            admin.password = data["new_password"]   # if plain text
            admin.save()

            otp.is_used = True
            otp.save()

            return Response({"message": "Admin password reset successful"})


        return Response({"error": "User not found"}, status=404)
