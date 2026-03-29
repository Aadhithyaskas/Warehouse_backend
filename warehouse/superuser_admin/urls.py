from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import register, AuthViewSet
from .views import SendRegisterOTPView, VerifyRegisterOTPView

router = DefaultRouter()
router.register('auth', AuthViewSet, basename='auth')

urlpatterns = [
    path('register/', register, name='register'),
    path('', include(router.urls)),
    path("send-register-otp/", SendRegisterOTPView.as_view()),
    path("verify-register-otp/", VerifyRegisterOTPView.as_view()),
]