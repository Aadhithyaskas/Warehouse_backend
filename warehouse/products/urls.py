from django.urls import path
from .views import *

app_name = 'products'

urlpatterns = [
    # Product CRUD
    path('', ListProductsView.as_view(), name='list'),
    path('create/', CreateProductView.as_view(), name='create'),
    path('process-invoice/', ProcessVendorInvoiceView.as_view(), name='process-invoice'),
    path('<str:product_id>/', ProductDetailView.as_view(), name='detail'),
    path('<str:product_id>/update/', UpdateProductView.as_view(), name='update'),
    path('<str:product_id>/delete/', DeleteProductView.as_view(), name='delete'),
    
    # Invoice Processing
    
    
    # Categories (if needed)

]