from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.conf import settings

from .models import Vendor, Warehouse
from .serializers import VendorSerializer 
from .models import Vendor, VendorProductMapping, PurchasePriceHistory
from .serializers import VendorProductMappingSerializer, PurchasePriceHistorySerializer
from products.models import Product

# ==============================
# GET WAREHOUSE (ONLY ONE)
# ==============================

class GetWarehouse(APIView):

    def get(self, request):

        warehouse = Warehouse.objects.first()

        if not warehouse:
            return Response(
                {"error": "Warehouse not created yet"},
                status=status.HTTP_404_NOT_FOUND
            )

        data = {
            "warehouse_id": warehouse.warehouse_id,
            "warehouse_name": warehouse.warehouse_name,
            "warehouse_email": warehouse.warehouse_email,
            "warehouse_phone": warehouse.warehouse_phone,
            "address": warehouse.address,
            "created_at": warehouse.created_at
        }

        return Response(data, status=status.HTTP_200_OK)


# ==============================
# CREATE WAREHOUSE (ONLY ONE)
# ==============================

class CreateWarehouse(APIView):

    def post(self, request):

        if Warehouse.objects.exists():
            return Response(
                {"error": "Warehouse already exists. Only one warehouse allowed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data

        warehouse = Warehouse.objects.create(
            warehouse_name=data.get("warehouse_name"),
            warehouse_email=data.get("warehouse_email"),
            warehouse_phone=data.get("warehouse_phone"),
            address=data.get("address")
        )

        return Response({
            "message": "Warehouse created successfully",
            "warehouse_id": warehouse.warehouse_id
        }, status=status.HTTP_201_CREATED)


# ==============================
# UPDATE WAREHOUSE
# ==============================

class UpdateWarehouse(APIView):

    def put(self, request):

        warehouse = Warehouse.objects.first()

        if not warehouse:
            return Response(
                {"error": "Warehouse not created yet"},
                status=status.HTTP_404_NOT_FOUND
            )

        data = request.data

        warehouse.warehouse_name = data.get(
            "warehouse_name", warehouse.warehouse_name
        )

        warehouse.warehouse_email = data.get(
            "warehouse_email", warehouse.warehouse_email
        )

        warehouse.warehouse_phone = data.get(
            "warehouse_phone", warehouse.warehouse_phone
        )

        warehouse.address = data.get(
            "address", warehouse.address
        )

        warehouse.save()

        return Response({
            "message": "Warehouse updated successfully"
        })


# ==============================
# CREATE VENDOR
# ==============================

class CreateVendorView(APIView):

    def post(self, request):

        warehouse = Warehouse.objects.first()

        if not warehouse:
            return Response(
                {"error": "Please create warehouse first"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = VendorSerializer(data=request.data)

        if serializer.is_valid():

            vendor = serializer.save(warehouse=warehouse)

            subject = "Welcome to Our Warehouse Management System"

            message = f"""
Hello {vendor.vendor_name},

You have been successfully registered as a Vendor.

Vendor Details
--------------
Vendor ID: {vendor.vendor_id}
Vendor Name: {vendor.vendor_name}
Lead Time: {vendor.lead_time} days

Warehouse Details
-----------------
Warehouse Name: {warehouse.warehouse_name}
Warehouse Email: {warehouse.warehouse_email}
Warehouse Phone: {warehouse.warehouse_phone}
Address: {warehouse.address}

Thank You
WMS Team
"""

            if vendor.email:
                send_mail(
                    subject,
                    message,
                    settings.EMAIL_HOST_USER,
                    [vendor.email],
                    fail_silently=True
                )

            return Response({
                "message": "Vendor created successfully",
                "vendor_id": vendor.vendor_id
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==============================
# LIST VENDORS
# ==============================

class ListVendorView(APIView):

    def get(self, request):

        vendors = Vendor.objects.all().order_by("lead_time")

        serializer = VendorSerializer(vendors, many=True)

        return Response(serializer.data)


# ==============================
# GET SINGLE VENDOR
# ==============================

class GetVendorView(APIView):

    def get(self, request, vendor_id):

        vendor = get_object_or_404(Vendor, vendor_id=vendor_id)

        serializer = VendorSerializer(vendor)

        return Response(serializer.data)


# ==============================
# UPDATE VENDOR
# ==============================

class UpdateVendor(APIView):

    def put(self, request, vendor_id):

        vendor = get_object_or_404(Vendor, vendor_id=vendor_id)

        serializer = VendorSerializer(
            vendor,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():

            serializer.save()

            return Response({
                "message": "Vendor updated successfully"
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==============================
# DELETE VENDOR
# ==============================

class DeleteVendor(APIView):

    def delete(self, request, vendor_id):

        vendor = get_object_or_404(Vendor, vendor_id=vendor_id)

        vendor.delete()

        return Response({
            "message": "Vendor deleted successfully"
        }, status=status.HTTP_200_OK)

class CreateVendorProductMappingView(APIView):
    """Create mapping between vendor product and internal product"""
    # permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request):
        serializer = VendorProductMappingSerializer(data=request.data)
        
        if serializer.is_valid():
            # Check if mapping already exists
            vendor = serializer.validated_data['vendor']
            vendor_product_code = serializer.validated_data['vendor_product_code']
            
            if VendorProductMapping.objects.filter(
                vendor=vendor, 
                vendor_product_code=vendor_product_code
            ).exists():
                return Response({
                    "error": f"Mapping already exists for vendor {vendor.vendor_name} with code {vendor_product_code}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            mapping = serializer.save()
            logger.info(f"Created mapping: {mapping.mapping_id} for vendor {vendor.vendor_name}")
            
            return Response({
                "message": "Product mapping created successfully",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListVendorProductMappingsView(APIView):
    """List all vendor product mappings"""
    # permission_classes = [IsAuthenticated]
    
    def get(self, request):
        vendor_id = request.query_params.get('vendor_id')
        product_id = request.query_params.get('product_id')
        
        mappings = VendorProductMapping.objects.select_related('vendor', 'product')
        
        if vendor_id:
            mappings = mappings.filter(vendor_id=vendor_id)
        if product_id:
            mappings = mappings.filter(product_id=product_id)
        
        serializer = VendorProductMappingSerializer(mappings, many=True)
        return Response({
            "count": mappings.count(),
            "data": serializer.data
        })


class UpdateVendorProductMappingView(APIView):
    """Update vendor product mapping"""
    # permission_classes = [IsAuthenticated, IsAdminUser]
    
    def put(self, request, mapping_id):
        mapping = get_object_or_404(VendorProductMapping, mapping_id=mapping_id)
        serializer = VendorProductMappingSerializer(mapping, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Mapping updated successfully",
                "data": serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteVendorProductMappingView(APIView):
    """Delete vendor product mapping"""
    # permission_classes = [IsAuthenticated, IsAdminUser]
    
    def delete(self, request, mapping_id):
        mapping = get_object_or_404(VendorProductMapping, mapping_id=mapping_id)
        mapping.delete()
        return Response({"message": "Mapping deleted successfully"}, status=status.HTTP_200_OK)


class VendorCatalogUploadView(APIView):
    """Upload vendor product catalog for bulk mapping"""
    # permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request, vendor_id):
        vendor = get_object_or_404(Vendor, vendor_id=vendor_id)
        
        # Expecting JSON array of products
        products_data = request.data.get('products', [])
        
        if not products_data:
            return Response({"error": "No products data provided"}, status=400)
        
        created_count = 0
        updated_count = 0
        errors = []
        
        with transaction.atomic():
            for item in products_data:
                vendor_code = item.get('vendor_product_code')
                product_name = item.get('product_name')
                agreed_price = item.get('agreed_price')
                min_order_qty = item.get('min_order_quantity', 1)
                
                if not vendor_code or not product_name or not agreed_price:
                    errors.append(f"Missing required fields for item: {item}")
                    continue
                
                # Try to find matching product by name
                product = Product.objects.filter(
                    product_name__icontains=product_name,
                    is_active=True
                ).first()
                
                if not product:
                    errors.append(f"Product not found: {product_name}")
                    continue
                
                # Create or update mapping
                mapping, created = VendorProductMapping.objects.update_or_create(
                    vendor=vendor,
                    vendor_product_code=vendor_code,
                    defaults={
                        'product': product,
                        'vendor_product_name': item.get('vendor_product_name', product_name),
                        'vendor_description': item.get('vendor_description', ''),
                        'agreed_price': agreed_price,
                        'min_order_quantity': min_order_qty,
                        'lead_time': item.get('lead_time', vendor.lead_time),
                        'is_preferred': item.get('is_preferred', False)
                    }
                )
                
                if created:
                    created_count += 1
                else:
                    updated_count += 1
        
        return Response({
            "message": "Catalog upload completed",
            "created": created_count,
            "updated": updated_count,
            "errors": errors
        }, status=status.HTTP_200_OK)