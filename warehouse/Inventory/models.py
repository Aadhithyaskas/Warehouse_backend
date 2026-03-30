from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from products.models import Product
from vendors.models import Vendor


class Zone(models.Model):
    ZONE_TYPES = [
        ("RECEIVING", "Receiving"),
        ("STORAGE", "Storage"),
        ("PICKING", "Picking"),
        ("SHIPPING", "Shipping"),
        ("RETURNS", "Returns"),
    ]
    
    zone_id = models.CharField(primary_key=True, max_length=10, editable=False)
    zone_type = models.CharField(max_length=20, choices=ZONE_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.zone_id:
            with transaction.atomic():
                last = Zone.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.zone_id[3:]) + 1) if last else 1
                self.zone_id = f"ZON{new_id:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.zone_id} - {self.get_zone_type_display()}"


class Rack(models.Model):
    rack_id = models.CharField(primary_key=True, max_length=10, editable=False)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="racks")
    created_at = models.DateTimeField(auto_now_add=True)
   
    
    class Meta:
        unique_together = ['zone', 'rack_id']

    
    def save(self, *args, **kwargs):
        if not self.rack_id:
            with transaction.atomic():
                last = Rack.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.rack_id[3:]) + 1) if last else 1
                self.rack_id = f"RCK{new_id:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.rack_id} - {self.zone.zone_id}"


class Shelf(models.Model):
    shelf_id = models.CharField(primary_key=True, max_length=10, editable=False)
    rack = models.ForeignKey(Rack, on_delete=models.CASCADE, related_name="shelves")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['rack', 'shelf_id']
    
    def save(self, *args, **kwargs):
        if not self.shelf_id:
            with transaction.atomic():
                last = Shelf.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.shelf_id[3:]) + 1) if last else 1
                self.shelf_id = f"SHF{new_id:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.shelf_id} - {self.rack.rack_id}"


class Bin(models.Model):
    bin_id = models.CharField(primary_key=True, max_length=10, editable=False)
    shelf = models.ForeignKey(Shelf, on_delete=models.CASCADE, related_name="bins")
    
    capacity = models.IntegerField(help_text="Maximum quantity this bin can hold")
    current_load = models.IntegerField(default=0, help_text="Current quantity in bin")
    
    distance_from_dispatch = models.FloatField(help_text="Distance in meters from dispatch area")
    
    pick_count = models.IntegerField(default=0, help_text="Number of times items were picked from this bin")
    last_picked_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(current_load__gte=0),
                name="current_load_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(current_load__lte=models.F('capacity')),
                name="load_not_exceed_capacity"
            ),
        ]

    
    def save(self, *args, **kwargs):
        # Validate capacity
        if self.capacity <= 0:
            raise ValidationError({"capacity": "Capacity must be greater than 0"})
        
        if self.current_load < 0:
            raise ValidationError({"current_load": "Current load cannot be negative"})
        
        if self.current_load > self.capacity:
            raise ValidationError({
                "current_load": f"Current load ({self.current_load}) cannot exceed capacity ({self.capacity})"
            })
        
        if not self.bin_id:
            with transaction.atomic():
                last = Bin.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.bin_id[3:]) + 1) if last else 1
                self.bin_id = f"BIN{new_id:04d}"
        super().save(*args, **kwargs)
    
    @property
    def available_capacity(self):
        return self.capacity - self.current_load
    
    def __str__(self):
        return f"{self.bin_id} (Load: {self.current_load}/{self.capacity})"

class Inventory(models.Model):
    inventory_id = models.CharField(max_length=10, primary_key=True, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    bin = models.ForeignKey(Bin, on_delete=models.CASCADE)

    quantity = models.IntegerField(default=0)

    class Meta:
        unique_together = ['product', 'bin']

    def save(self, *args, **kwargs):
        if self.quantity < 0:
            raise ValidationError("Quantity cannot be negative")

        super().save(*args, **kwargs)

        # Sync bin load
        total = Inventory.objects.filter(bin=self.bin).aggregate(
            total=models.Sum("quantity")
        )['total'] or 0

        self.bin.current_load = total
        self.bin.save(update_fields=["current_load"])


class PurchaseRequest(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("MANAGER_APPROVED", "Manager Approved"),
        ("FINANCE_PENDING", "Finance Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]
    
    pr_id = models.CharField(max_length=10, primary_key=True, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="purchase_requests")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="purchase_requests")
    requested_quantity = models.IntegerField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)  # Changed to Decimal
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, related_name="created_prs")
    approved_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_prs")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def clean(self):
        if self.requested_quantity <= 0:
            raise ValidationError("Quantity must be greater than 0")

        if self.product.vendor != self.vendor:
            raise ValidationError("Vendor must match product vendor")

    
    def save(self, *args, **kwargs):
        self.clean()
        
        if not self.pr_id:
            with transaction.atomic():
                last = PurchaseRequest.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.pr_id[2:]) + 1) if last else 1
                self.pr_id = f"PR{new_id:04d}"
        
        if not self.total_amount and self.product and self.requested_quantity:
            self.total_amount = self.requested_quantity * self.product.unit_price
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.pr_id} - {self.product.product_name} ({self.status})"


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ("CREATED", "Created"),
        ("SENT", "Sent to Vendor"),
        ("CONFIRMED", "Confirmed"),
        ("SHIPPED", "Shipped"),
        ("RECEIVED", "Received"),
        ("CANCELLED", "Cancelled"),
    ]
    
    po_id = models.CharField(max_length=10, primary_key=True, editable=False)
    pr = models.OneToOneField(PurchaseRequest, on_delete=models.CASCADE, related_name="purchase_order")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="purchase_orders")
    order_quantity = models.IntegerField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="CREATED")
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, related_name="created_pos")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.po_id:
            with transaction.atomic():
                last = PurchaseOrder.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.po_id[2:]) + 1) if last else 1
                self.po_id = f"PO{new_id:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.po_id} - {self.vendor.name} ({self.status})"

    def clean(self):
    if self.order_quantity <= 0:
        raise ValidationError("Order quantity must be greater than 0")

    if self.pr.vendor != self.vendor:
        raise ValidationError("Vendor mismatch with PR")



class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ("INBOUND", "Inbound"),
        ("OUTBOUND", "Outbound"),
        ("STOCK_ADDITION", "Stock Addition"),
        ("STOCK_REMOVAL", "Stock Removal"),
        ("TRANSFER", "Transfer"),
        ("ADJUSTMENT", "Adjustment"),
    ]
    
    movement_id = models.CharField(max_length=10, primary_key=True, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_movements")
    bin = models.ForeignKey(Bin, on_delete=models.CASCADE, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()
    previous_stock = models.IntegerField()
    new_stock = models.IntegerField()
    reference = models.CharField(max_length=50, blank=True, help_text="Reference document (e.g., GRN-001, PO-001)")
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['product', '-created_at']),
            models.Index(fields=['movement_type']),
            models.Index(fields=['reference']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.movement_id:
            with transaction.atomic():
                last = StockMovement.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.movement_id[2:]) + 1) if last else 1
                self.movement_id = f"SM{new_id:04d}"
        super().save(*args, **kwargs)
    
    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("Quantity must be greater than 0")

        if self.new_stock < 0:
            raise ValidationError("Stock cannot go negative")
    class Meta:
        ordering = ['-created_at']


    def __str__(self):
        return f"{self.movement_id} - {self.product.product_name} ({self.movement_type})"


class ASN(models.Model):
    STATUS_CHOICES = [
        ("CREATED", "Created"),
        ("SHIPPED", "Shipped"),
        ("IN_TRANSIT", "In Transit"),
        ("RECEIVED", "Received"),
        ("CANCELLED", "Cancelled"),
    ]
    
    asn_id = models.CharField(max_length=10, primary_key=True, editable=False)
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="asns")
    asn_number = models.CharField(max_length=50, unique=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="asns")
    shipment_date = models.DateField()
    expected_arrival_date = models.DateField()
    actual_arrival_date = models.DateField(null=True, blank=True)
    vehicle_num = models.CharField(max_length=13)
    driver_name = models.CharField(max_length=25)
    driver_phone = models.CharField(max_length=15)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="CREATED")
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, related_name="created_asns")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['expected_arrival_date']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.asn_id:
            with transaction.atomic():
                last = ASN.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.asn_id[3:]) + 1) if last else 1
                self.asn_id = f"ASN{new_id:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.asn_id} - {self.asn_number}"

    def clean(self):
        if self.expected_arrival_date < self.shipment_date:
            raise ValidationError("Arrival date cannot be before shipment date")



class ASNItem(models.Model):
    asn_item_id = models.CharField(max_length=20, primary_key=True, editable=False)
    asn = models.ForeignKey(ASN, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="asn_items")
    expected_quantity = models.IntegerField()
    shipped_quantity = models.IntegerField()
    received_quantity = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['asn', 'product']
    
    def clean(self):
        if self.shipped_quantity > self.expected_quantity:
            raise ValidationError({
                "shipped_quantity": f"Shipped quantity ({self.shipped_quantity}) cannot exceed expected quantity ({self.expected_quantity})"
            })
    
    def save(self, *args, **kwargs):
        self.clean()
        
        if not self.asn_item_id:
            with transaction.atomic():
                last = ASNItem.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.asn_item_id.split('-')[-1]) + 1) if last else 1
                self.asn_item_id = f"ASN-ITM-{new_id:03d}"
        super().save(*args, **kwargs)

    def clean(self):
        if self.expected_quantity <= 0:
            raise ValidationError("Expected quantity must be > 0")

        if self.shipped_quantity < 0 or self.received_quantity < 0:
            raise ValidationError("Quantities cannot be negative")

    
    def __str__(self):
        return f"{self.asn_item_id} - {self.product.product_name}"


class GRN(models.Model):
    STATUS_CHOICES = [
        ("RECEIVED", "Received by Supervisor"),
        ("QC_PENDING", "QC Pending"),
        ("COMPLETED", "Completed"),
        ("REJECTED", "Rejected"),
    ]
    
    grn_id = models.CharField(primary_key=True, max_length=10, editable=False)
    grn_number = models.CharField(max_length=50, unique=True)
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="grns")
    asn = models.ForeignKey(ASN, on_delete=models.CASCADE, null=True, blank=True, related_name="grns")
    receipt_date = models.DateField()
    received_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="grn_received"
    )
    qc_verified_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="grn_verified"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="RECEIVED")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['receipt_date']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.grn_id:
            with transaction.atomic():
                last = GRN.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.grn_id.split('-')[-1]) + 1) if last else 1
                self.grn_id = f"GRN-{new_id:04d}"
        super().save(*args, **kwargs)

    def clean(self):
        if self.asn and self.asn.po != self.po:
            raise ValidationError("ASN must belong to same PO")

    
    def __str__(self):
        return f"{self.grn_id} - {self.po.po_id} ({self.status})"


class GRNItem(models.Model):
    QC_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]
    
    grn_item_id = models.CharField(primary_key=True, max_length=15, editable=False)
    grn = models.ForeignKey(GRN, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="grn_items")
    received_quantity = models.IntegerField()
    accepted_quantity = models.IntegerField(default=0)
    rejected_quantity = models.IntegerField(default=0)
    qc_status = models.CharField(max_length=15, choices=QC_STATUS_CHOICES, default="PENDING")
    qc_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['qc_status']),
        ]
    
    def clean(self):
        if self.received_quantity <= 0:
            raise ValidationError({"received_quantity": "Received quantity must be greater than 0"})
        
        if self.accepted_quantity < 0 or self.rejected_quantity < 0:
            raise ValidationError("Accepted and rejected quantities cannot be negative")
        
        if self.accepted_quantity + self.rejected_quantity > self.received_quantity:
            raise ValidationError({
                "accepted_quantity": f"Accepted + Rejected ({self.accepted_quantity + self.rejected_quantity}) cannot exceed Received ({self.received_quantity})"
            })
    
    def save(self, *args, **kwargs):
        self.clean()
        
        if not self.grn_item_id:
            with transaction.atomic():
                last = GRNItem.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.grn_item_id.split('-')[-1]) + 1) if last else 1
                self.grn_item_id = f"GRN-ITM-{new_id:04d}"
        super().save(*args, **kwargs)
    
    @property
    def qc_complete(self):
        return self.qc_status == "COMPLETED"
    
    def __str__(self):
        return f"{self.grn_item_id} - {self.product.product_name} (Received: {self.received_quantity})"


# ================= INBOUND/OUTBOUND TRANSACTIONS =================

class inbound_trans(models.Model):
    STATUS_CHOICES = [
        ("CREATED", "Created"),
        ("PLANNED", "Putaway Planned"),
        ("COMPLETED", "Completed"),
    ]
    
    inbound_id = models.CharField(max_length=10, primary_key=True, editable=False)
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE)
    received_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="CREATED")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.inbound_id:
            with transaction.atomic():
                last = inbound_trans.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.inbound_id[2:]) + 1) if last else 1
                self.inbound_id = f"IB{new_id:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.inbound_id} - PO: {self.po_id} ({self.status})"


class outbound_trans(models.Model):
    STATUS_CHOICES = [
        ("CREATED", "Created"),
        ("PLANNED", "Pick Planned"),
        ("DISPATCHED", "Dispatched"),
    ]
    
    outbound_id = models.CharField(max_length=10, primary_key=True, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="CREATED")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.outbound_id:
            with transaction.atomic():
                last = outbound_trans.objects.select_for_update().order_by('-created_at').first()
                new_id = (int(last.outbound_id[2:]) + 1) if last else 1
                self.outbound_id = f"OB{new_id:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.outbound_id} - Product: {self.product_id} ({self.status})"