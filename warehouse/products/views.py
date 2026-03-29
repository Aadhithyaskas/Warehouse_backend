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
    """
    Process vendor invoice with intelligent product matching
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Validate file
        invoice_file = request.FILES.get('invoice')
        if not invoice_file:
            return Response({"error": "No file uploaded"}, status=400)
        
        if not invoice_file.name.lower().endswith('.pdf'):
            return Response({"error": "Only PDF files are supported"}, status=400)
        
        if invoice_file.size > 10 * 1024 * 1024:
            return Response({"error": "File size exceeds 10MB limit"}, status=400)
        
        # Validate profit margin
        try:
            profit_percentage = float(request.data.get('profit_margin', 20))
            if profit_percentage < 0 or profit_percentage > 100:
                return Response({"error": "Profit margin must be between 0 and 100"}, status=400)
        except ValueError:
            return Response({"error": "Invalid profit margin value"}, status=400)
        
        # Get vendor if specified
        vendor_id = request.data.get('vendor_id')
        vendor = None
        if vendor_id:
            try:
                vendor = Vendor.objects.get(vendor_id=vendor_id)
            except Vendor.DoesNotExist:
                return Response({"error": f"Vendor with ID {vendor_id} not found"}, status=400)
        
        logger.info(f"Processing vendor invoice from user {request.user.id}, margin: {profit_percentage}%")
        
        try:
            # Parse PDF
            raw_items = parse_vendor_invoice(invoice_file)
            if not raw_items:
                return Response({"error": "No valid items found in invoice"}, status=400)
            
            processed_items = []
            updated_products = []
            skipped_items = []
            matched_items = []
            new_mappings = []
            
            with transaction.atomic():
                for entry in raw_items:
                    product = None
                    vendor_code = entry.get('sku', '')
                    product_name = entry.get('product_name', '')
                    quantity = entry.get('quantity', 0)
                    price = entry.get('price', 0)
                    
                    # Stage 1: Try to match by vendor product code
                    if vendor and vendor_code:
                        mapping = VendorProductMapping.objects.filter(
                            vendor=vendor,
                            vendor_product_code=vendor_code,
                            is_active=True
                        ).first()
                        
                        if mapping:
                            product = mapping.product
                            matched_items.append({
                                'method': 'vendor_code',
                                'vendor_code': vendor_code,
                                'product': product.product_name
                            })
                    
                    # Stage 2: Try fuzzy matching by product name
                    if not product and vendor and product_name:
                        product = self.match_by_product_name(product_name, vendor)
                        if product:
                            matched_items.append({
                                'method': 'fuzzy_name',
                                'vendor_name': product_name,
                                'product': product.product_name
                            })
                    
                    # Stage 3: Try matching by product name without vendor
                    if not product and product_name:
                        product = self.match_by_product_name_global(product_name)
                        if product:
                            matched_items.append({
                                'method': 'global_name',
                                'vendor_name': product_name,
                                'product': product.product_name
                            })
                    
                    if product:
                        # Record purchase price history
                        PurchasePriceHistory.objects.create(
                            product=product,
                            vendor=vendor,
                            quantity=quantity,
                            unit_price=price,
                            total_amount=price * quantity,
                            purchase_date=datetime.now().date(),
                            invoice_number=entry.get('invoice_number', '')
                        )
                        
                        # Update vendor product mapping with last price
                        if vendor and vendor_code:
                            mapping, created = VendorProductMapping.objects.update_or_create(
                                vendor=vendor,
                                vendor_product_code=vendor_code,
                                defaults={
                                    'product': product,
                                    'vendor_product_name': entry.get('product_name', product.product_name),
                                    'last_purchase_price': price,
                                    'agreed_price': price if not created else mapping.agreed_price
                                }
                            )
                            if created:
                                new_mappings.append(vendor_code)
                        
                        # Update product quantity
                        product.quantity += quantity
                        product.save(update_fields=['quantity'])
                        
                        # Update average purchase cost
                        product.update_avg_purchase_cost()
                        
                        # Calculate new price with profit
                        new_price = price * (1 + profit_percentage / 100)
                        
                        updated_products.append({
                            'sku': product.sku_code,
                            'name': product.product_name,
                            'purchase_price': price,
                            'new_price': round(new_price, 2)
                        })
                        
                        processed_items.append({
                            "product_name": product.product_name,
                            "quantity": quantity,
                            "purchase_price": price,
                            "new_price": round(new_price, 2),
                            "total": round(new_price * quantity, 2)
                        })
                    else:
                        skipped_items.append({
                            'sku': vendor_code,
                            'name': product_name,
                            'quantity': quantity,
                            'price': price
                        })
                        logger.warning(f"Product not found: SKU: {vendor_code}, Name: {product_name}")
            
            # Generate PDF after transaction
            pdf_path = generate_supplier_invoice_pdf(
                processed_items,
                request.user.username,
                profit_percentage
            )
            
            response_data = {
                "message": "Invoice processed successfully",
                "supplier_invoice_url": pdf_path,
                "items_processed": len(processed_items),
                "items_skipped": len(skipped_items),
                "profit_margin_applied": profit_percentage,
                "matched_items": matched_items
            }
            
            if updated_products:
                response_data["updated_products"] = updated_products
            
            if skipped_items:
                response_data["skipped_items"] = skipped_items
            
            if new_mappings:
                response_data["new_mappings_created"] = new_mappings
            
            logger.info(f"Invoice processed: {len(processed_items)} items, {len(skipped_items)} skipped")
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Invoice processing failed: {str(e)}", exc_info=True)
            return Response({"error": str(e)}, status=500)
    
    def match_by_product_name(self, product_name, vendor):
        """Match product by name with vendor-specific mapping"""
        # Get all vendor product mappings
        mappings = VendorProductMapping.objects.filter(
            vendor=vendor,
            is_active=True
        ).select_related('product')
        
        best_match = None
        best_score = 0
        
        for mapping in mappings:
            # Calculate similarity score
            score = SequenceMatcher(None, 
                product_name.lower(), 
                mapping.vendor_product_name.lower()
            ).ratio()
            
            # Also check product name
            product_score = SequenceMatcher(None,
                product_name.lower(),
                mapping.product.product_name.lower()
            ).ratio()
            
            max_score = max(score, product_score)
            
            if max_score > best_score and max_score > 0.6:
                best_score = max_score
                best_match = mapping.product
        
        return best_match
    
    def match_by_product_name_global(self, product_name):
        """Match product by name globally"""
        products = Product.objects.filter(is_active=True)
        
        best_match = None
        best_score = 0
        
        for product in products:
            score = SequenceMatcher(None, 
                product_name.lower(), 
                product.product_name.lower()
            ).ratio()
            
            if score > best_score and score > 0.6:
                best_score = score
                best_match = product
        
        return best_match

class ListProductsView(APIView):
    """List all products with pagination"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Add filtering options
        products = Product.objects.filter(is_active=True)
        
        # Filter by category
        category = request.query_params.get('category')
        if category:
            products = products.filter(category=category)
        
        # Filter by ABC classification
        abc = request.query_params.get('abc')
        if abc:
            products = products.filter(ABC=abc)
        
        # Search by name or SKU
        search = request.query_params.get('search')
        if search:
            products = products.filter(
                models.Q(product_name__icontains=search) |
                models.Q(sku_code__icontains=search) |
                models.Q(brand_name__icontains=search)
            )
        
        # Order by
        ordering = request.query_params.get('ordering', '-created_at')
        products = products.order_by(ordering)
        
        # Paginate
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(products, request)
        serializer = ProductSerializer(page, many=True)
        
        return paginator.get_paginated_response({
            "products": serializer.data,
            "filters_applied": {
                "category": category,
                "abc": abc,
                "search": search
            }
        })


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