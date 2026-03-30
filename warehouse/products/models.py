from django.db import models, transaction
from django.core.exceptions import ValidationError
from vendors.models import Vendor


class Product(models.Model):
    ABC_CHOICES = [
        ('A', 'High Value'),
        ('B', 'Medium Value'),
        ('C', 'Low Value'),
    ]

    product_id = models.CharField(primary_key=True, max_length=10, editable=False)
    product_name = models.CharField(max_length=255)

    sku = models.CharField(max_length=100, unique=True)

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        null=True,
        related_name="products"
    )

    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    re_order = models.IntegerField(default=10)
    min_order_quantity = models.IntegerField(default=10)

    ABC = models.CharField(max_length=1, choices=ABC_CHOICES, default='C')

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.product_id:
            last = Product.objects.order_by('-created_at').first()
            new_id = int(last.product_id[3:]) + 1 if last else 1
            self.product_id = f"PRD{new_id:04d}"
        super().save(*args, **kwargs)

