from django.db import models


class Supplier(models.Model):

    supplier_id = models.CharField(
        primary_key=True,
        max_length=10,
        editable=False
    )

    supplier_name = models.CharField(max_length=255)

    contact_personname = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    email = models.EmailField(
        blank=True,
        null=True
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    address = models.TextField(
        blank=True,
        null=True
    )

    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "supplier"
        ordering = ["supplier_name"]

    def save(self, *args, **kwargs):

        if not self.supplier_id:
            last_supplier = Supplier.objects.order_by('-supplier_id').first()

            if last_supplier:
                last_id = int(last_supplier.supplier_id[3:])
                new_id = last_id + 1
            else:
                new_id = 1

            self.supplier_id = f"SUP{new_id:04d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.supplier_id} - {self.supplier_name}"