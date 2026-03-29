from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # JWT Authentication
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # RBAC APIs
    path('api/auth/', include('rbac.urls')),

    # Vendor APIs
    path('api/vendors/', include('vendors.urls')),

    # Supplier APIs
    path('api/suppliers/', include('supplier.urls')),

    # Product APIs
    path('api/products/', include('products.urls')),

    path('api/inventory/',include('Inventory.urls')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)