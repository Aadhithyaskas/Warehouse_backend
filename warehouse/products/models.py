from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from vendors.models import Vendor
from supplier.models import Supplier


class Product(models.Model):
    # Classification Choices
    ABC_CHOICES = [
        ('A', 'A - High Value'),
        ('B', 'B - Medium Value'),
        ('C', 'C - Low Value'),
    ]
    
    VED_CHOICES = [
        ('V', 'V - Vital'),
        ('E', 'E - Essential'),
        ('D', 'D - Desirable'),
    ]
    
    XYZ_CHOICES = [
        ('X', 'X - High Demand'),
        ('Y', 'Y - Medium Demand'),
        ('Z', 'Z - Low Demand'),
    ]
    
    # Primary Key
    product_id = models.CharField(max_length=10, primary_key=True, editable=False)
    
    # Basic Information
    product_name = models.CharField(max_length=255, db_index=True)
    brand_name = models.CharField(max_length=100)
    size = models.CharField(max_length=10, blank=True, default='')
    sku_code = models.CharField(max_length=100, unique=True, editable=False, db_index=True)
    description = models.TextField(blank=True, default='')
    
    # REMOVED: category = models.CharField(max_length=100)  # ← DELETE THIS LINE
    
    # Classification
    ABC = models.CharField(max_length=1, choices=ABC_CHOICES, db_index=True)
    VED = models.CharField(max_length=1, choices=VED_CHOICES, db_index=True)
    XYZ = models.CharField(max_length=1, choices=XYZ_CHOICES, db_index=True)
    
    # Inventory
    quantity = models.IntegerField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, db_index=True)
    re_order = models.IntegerField(default=0, help_text="Reorder level")
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_products')
    updated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_products')
    
    # Relationships
    vendor = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='products'
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products'
    )
    avg_purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # NEW: Preferred vendor for this product
    preferred_vendor = models.ForeignKey(
        'vendors.Vendor', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='preferred_products'
    )
    
    # Add method to calculate average cost
    def update_avg_purchase_cost(self):
        """Update average purchase cost based on price history"""
        from vendors.models import PurchasePriceHistory
        
        history = PurchasePriceHistory.objects.filter(product=self).order_by('-purchase_date')[:10]
        if history.exists():
            total_cost = sum(h.unit_price * h.quantity for h in history)
            total_qty = sum(h.quantity for h in history)
            self.avg_purchase_cost = total_cost / total_qty if total_qty > 0 else 0
            self.save(update_fields=['avg_purchase_cost'])
            
    class Meta:
        indexes = [
            models.Index(fields=['product_name']),
            models.Index(fields=['sku_code']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
    
    def clean(self):
        """Model validation"""
        if self.quantity < 0:
            raise ValidationError({'quantity': 'Quantity cannot be negative'})
        
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative'})
        
        if self.re_order < 0:
            raise ValidationError({'re_order': 'Reorder level cannot be negative'})
    
    def save(self, *args, **kwargs):
        self.clean()
        
        if not self.product_id:
            with transaction.atomic():
                last_product = Product.objects.select_for_update().order_by('product_id').last()
                if last_product:
                    last_id = int(last_product.product_id[3:])
                    new_id = last_id + 1
                else:
                    new_id = 1
                self.product_id = f"PRO{new_id:03d}"
        
        if not self.sku_code:
            brand_code = self.brand_name[:3].upper()
            product_code = ''.join([word[0] for word in self.product_name.split()]).upper()
            size_part = self.size.upper() if self.size else 'NA'
            sku_base = f"{brand_code}-{product_code}-{size_part}"
            
            # Ensure uniqueness
            sku = sku_base
            counter = 1
            while Product.objects.filter(sku_code=sku).exclude(product_id=self.product_id).exists():
                sku = f"{sku_base}-{counter}"
                counter += 1
            self.sku_code = sku
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.product_name} ({self.product_id})"