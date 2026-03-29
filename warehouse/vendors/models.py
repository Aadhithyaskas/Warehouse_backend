from django.db import models
from django.core.exceptions import ValidationError
import re

class Warehouse(models.Model):
    warehouse_id = models.CharField(primary_key=True, max_length=10, editable=False)
    warehouse_name = models.CharField(max_length=150)
    warehouse_email = models.EmailField()
    warehouse_phone = models.CharField(max_length=15)
    address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.warehouse_id and Warehouse.objects.exists():
            raise ValueError("Only one warehouse is allowed in the system.")
        if not self.warehouse_id:
            self.warehouse_id = "WH0001"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.warehouse_name} ({self.warehouse_id})"


class Vendor(models.Model):
    vendor_id = models.CharField(primary_key=True, max_length=10, editable=False)
    vendor_name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20)
    lead_time = models.IntegerField(help_text="Lead time in days")
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="vendors")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.vendor_id:
            last_vendor = Vendor.objects.all().order_by("created_at").last()
            if last_vendor:
                last_id = int(last_vendor.vendor_id[3:])
                new_id = last_id + 1
            else:
                new_id = 1
            self.vendor_id = f"VEN{new_id:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vendor_name} ({self.vendor_id})"


class VendorProductMapping(models.Model):
    """Maps vendor products to internal products with vendor-specific pricing"""
    
    mapping_id = models.CharField(max_length=15, primary_key=True, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="product_mappings")
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name="vendor_mappings")
    
    # Vendor's product identifiers
    vendor_product_code = models.CharField(max_length=100, help_text="Vendor's SKU/Product Code")
    vendor_product_name = models.CharField(max_length=255, help_text="Product name as per vendor")
    vendor_description = models.TextField(blank=True, help_text="Vendor's product description")
    
    # Pricing
    agreed_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Agreed purchase price")
    last_purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Business terms
    min_order_quantity = models.IntegerField(default=1)
    lead_time = models.IntegerField(null=True, blank=True, help_text="Lead time in days for this product")
    is_preferred = models.BooleanField(default=False, help_text="Preferred vendor for this product")
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['vendor', 'vendor_product_code']
        indexes = [
            models.Index(fields=['vendor', 'vendor_product_code']),
            models.Index(fields=['product', 'vendor']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.mapping_id:
            import uuid
            self.mapping_id = f"MAP-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.vendor.vendor_name} - {self.vendor_product_code} -> {self.product.product_name}"


class PurchasePriceHistory(models.Model):
    """Tracks purchase prices from different vendors over time"""
    
    history_id = models.CharField(max_length=15, primary_key=True, editable=False)
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name="price_history")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="price_history")
    purchase_order = models.ForeignKey('inventory.PurchaseOrder', on_delete=models.CASCADE, null=True, blank=True)
    
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    purchase_date = models.DateField()
    invoice_number = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-purchase_date']
        indexes = [
            models.Index(fields=['product', 'vendor']),
            models.Index(fields=['purchase_date']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.history_id:
            import uuid
            self.history_id = f"PRC-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.product.product_name} - {self.vendor.vendor_name} @ {self.unit_price}"