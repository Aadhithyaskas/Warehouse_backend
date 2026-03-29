from django.urls import path
from .views import *

urlpatterns = [

    # Warehouse
    path("warehouse/", GetWarehouse.as_view()),
    path("Warehouse/create/", CreateWarehouse.as_view()),
    path("Warehouse/update/", UpdateWarehouse.as_view()),

    # Vendor
    path("create/", CreateVendorView.as_view()),
    path("list_all/", ListVendorView.as_view()),
    path("<str:vendor_id>/", GetVendorView.as_view()),
    path("update/<str:vendor_id>/", UpdateVendor.as_view()),
    path("delete/<str:vendor_id>/", DeleteVendor.as_view()),

    path('mappings/create/', CreateVendorProductMappingView.as_view(), name='mapping-create'),
    path('mappings/', ListVendorProductMappingsView.as_view(), name='mapping-list'),
    path('mappings/<str:mapping_id>/update/', UpdateVendorProductMappingView.as_view(), name='mapping-update'),
    path('mappings/<str:mapping_id>/delete/', DeleteVendorProductMappingView.as_view(), name='mapping-delete'),
    path('<str:vendor_id>/catalog-upload/', VendorCatalogUploadView.as_view(), name='catalog-upload'),

]