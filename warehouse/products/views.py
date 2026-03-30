from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser,AllowAny
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError
import logging
import magic
from .models import Product
from .serializers import ProductSerializer
from .utils import parse_vendor_invoice, generate_supplier_invoice_pdf 
from vendors.models import Vendor, VendorProductMapping, PurchasePriceHistory
from Inventory.models import PurchaseOrder
from difflib import SequenceMatcher
import re
from datetime import datetime
from django.db import transaction
from django.db.models import Q
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class CreateProductView(APIView):
    """Create a new product"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        
        if serializer.is_valid():
            product = serializer.save()
            logger.info(f"Product created: {product.product_id} by user {request.user.id}")
            return Response({
                "message": "Product created successfully",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


from django.db.models import F
class ProcessVendorInvoiceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        invoice_file = request.FILES.get('invoice')

        if not invoice_file:
            return Response({"error": "No file uploaded"}, status=400)

        if not invoice_file.name.lower().endswith('.pdf'):
            return Response({"error": "Only PDF files allowed"}, status=400)

        # Profit margin
        try:
            profit_percentage = float(request.data.get('profit_margin', 20))
            if not (0 <= profit_percentage <= 100):
                return Response({"error": "Invalid profit margin"}, status=400)
        except:
            return Response({"error": "Invalid profit margin"}, status=400)

        try:
            # ✅ Parse invoice
            parsed_data = parse_vendor_invoice(invoice_file)

            vendor_email = parsed_data.get("vendor_email")
            invoice_number = parsed_data.get("invoice_number")
            raw_items = parsed_data.get("items", [])

            if not raw_items:
                return Response({"error": "No items found in invoice"}, status=400)

            # ✅ Vendor identification
            vendor = Vendor.objects.filter(email__iexact=vendor_email).first()

            if not vendor:
                return Response(
                    {"error": f"Vendor not found for email: {vendor_email}"},
                    status=400
                )

            processed_items = []
            skipped_items = []
            matched_items = []

            with transaction.atomic():

                for entry in raw_items:
                    product = None

                    sku = entry.get("sku", "").strip()
                    name = entry.get("product_name", "").strip()
                    qty = entry.get("quantity", 0)
                    price = entry.get("price", 0)

                    # =========================
                    # 1. MATCH BY VENDOR SKU
                    # =========================
                    if sku:
                        mapping = VendorProductMapping.objects.filter(
                            vendor=vendor,
                            vendor_product_code=sku,
                            is_active=True
                        ).select_related("product").first()

                        if mapping:
                            product = mapping.product
                            matched_items.append({
                                "method": "vendor_sku",
                                "sku": sku,
                                "product": product.product_name
                            })

                    # =========================
                    # 2. MATCH BY VENDOR NAME
                    # =========================
                    if not product and name:
                        product = self.match_vendor_products(name, vendor)

                        if product:
                            matched_items.append({
                                "method": "vendor_name",
                                "name": name,
                                "product": product.product_name
                            })

                    # =========================
                    # 3. GLOBAL MATCH (STRICT)
                    # =========================
                    if not product and name:
                        product = self.match_global_products(name)

                        if product:
                            matched_items.append({
                                "method": "global_name",
                                "name": name,
                                "product": product.product_name
                            })

                    # =========================
                    # NOT FOUND → SKIP
                    # =========================
                    if not product:
                        skipped_items.append({
                            "sku": sku,
                            "name": name,
                            "reason": "Product not found"
                        })
                        continue

                    # =========================
                    # SAVE DATA
                    # =========================

                    # Price history
                    PurchasePriceHistory.objects.create(
                        product=product,
                        vendor=vendor,
                        quantity=qty,
                        unit_price=price,
                        total_amount=qty * price,
                        purchase_date=datetime.now().date(),
                        invoice_number=invoice_number
                    )

                    # Vendor mapping (FIXED)
                    mapping, created = VendorProductMapping.objects.get_or_create(
                        vendor=vendor,
                        vendor_product_code=sku,
                        defaults={
                            "product": product,
                            "vendor_product_name": name or product.product_name,
                            "last_purchase_price": price,
                            "agreed_price": price
                        }
                    )

                    if not created:
                        mapping.last_purchase_price = price
                        mapping.save()

                    # Update stock
                    product.quantity += qty
                    product.save(update_fields=["quantity"])

                    product.update_avg_purchase_cost()

                    # Selling price
                    new_price = price * (1 + profit_percentage / 100)

                    processed_items.append({
                        "product_name": product.product_name,
                        "quantity": qty,
                        "purchase_price": price,
                        "new_price": round(new_price, 2),
                        "total": round(new_price * qty, 2)
                    })

            # ✅ Generate invoice PDF
            pdf_url = generate_supplier_invoice_pdf(
                processed_items,
                vendor.name,
                profit_percentage
            )

            return Response({
                "message": "Invoice processed successfully",
                "vendor": vendor.name,
                "items_processed": len(processed_items),
                "items_skipped": len(skipped_items),
                "matched_items": matched_items,
                "invoice_url": pdf_url,
                "skipped_items": skipped_items
            })

        except Exception as e:
            logger.error(str(e), exc_info=True)
            return Response({"error": str(e)}, status=500)

class ProductDetailView(APIView):
    """Get single product details"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, product_id):
        try:
            product = Product.objects.get(product_id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ProductSerializer(product)
        return Response(serializer.data)


class UpdateProductView(APIView):
    """Update product details"""
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def put(self, request, product_id):
        try:
            product = Product.objects.get(product_id=product_id)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ProductSerializer(product, data=request.data, partial=True)
        if serializer.is_valid():
            updated_product = serializer.save()
            logger.info(f"Product updated: {product_id} by user {request.user.id}")
            return Response({
                "message": "Product updated successfully",
                "data": serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteProductView(APIView):
    """Soft delete or hard delete product"""
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def delete(self, request, product_id):
        try:
            product = Product.objects.get(product_id=product_id)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Option 1: Soft delete (recommended)
        product.is_active = False
        product.save()
        logger.info(f"Product soft deleted: {product_id} by user {request.user.id}")
        return Response({"message": "Product deactivated successfully"}, status=200)
        
        # Option 2: Hard delete (use with caution)
        # product.delete()
        # return Response({"message": "Product deleted successfully"}, status=200)