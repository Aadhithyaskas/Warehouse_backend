from django.urls import path
from .views import  CreateAdminView
from .views import (
  
    LoginView,
    ForgotPasswordOTPView,
    ResetPasswordView,
    AdminCreateUserView,
    VerifyLoginOTPView,
    ForceChangePasswordView,
    LogoutView,DeleteUserView,ListEmployeeView,UpdateEmployeeView,get_csrf_token,
)

urlpatterns = [
    
    #admin login
    # Registration
    path('delete-user/<str:employee_id>/', DeleteUserView.as_view()),
    #Login
    path('login/', LoginView.as_view(), name='login'),
    #Forgot Password
    path('forgot-password-otp/', ForgotPasswordOTPView.as_view(), name='forgot-password-otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('admin-create-user/', AdminCreateUserView.as_view(), name='admin-create-user'),
    path('verify-login-otp/', VerifyLoginOTPView.as_view(), name='verify-login-otp'),
    path('force-change-password/', ForceChangePasswordView.as_view(), name='force-change-password'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('list_employees/',ListEmployeeView.as_view(),name="employees"),
    path('update-user/<str:employee_id>/', UpdateEmployeeView.as_view(), name='update-user'),
    path("csrf/", get_csrf_token),
    path('create-admin/', CreateAdminView.as_view()),
    # path("admin-login/", AdminLoginView.as_view()),


]
