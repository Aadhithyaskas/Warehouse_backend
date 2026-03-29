from rest_framework import serializers
from django.core.exceptions import ValidationError
from .models import (
    Inventory, PurchaseRequest, PurchaseOrder, ASN, ASNItem, 
    GRN, GRNItem, Zone, Rack, Shelf, Bin, StockMovement,
    inbound_trans, outbound_trans
)
from products.models import Product
from vendors.models import Vendor


# ================= BIN SERIALIZERS =================

class BinSerializer(serializers.ModelSerializer):
    """Serializer for Bin model with validation"""
    
    available_capacity = serializers.IntegerField(read_only=True)
    zone_id = serializers.CharField(source='shelf.rack.zone.zone_id', read_only=True)
    rack_id = serializers.CharField(source='shelf.rack.rack_id', read_only=True)
    shelf_id = serializers.CharField(source='shelf.shelf_id', read_only=True)
    
    class Meta:
        model = Bin
        fields = [
            'bin_id', 'shelf', 'capacity', 'current_load', 
            'distance_from_dispatch', 'pick_count', 'last_picked_at',
            'available_capacity', 'zone_id', 'rack_id', 'shelf_id'
        ]
        read_only_fields = ['bin_id', 'pick_count', 'last_picked_at']
    
    def validate_capacity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Capacity must be greater than 0")
        return value
    
    def validate_current_load(self, value):
        if value < 0:
            raise serializers.ValidationError("Current load cannot be negative")
        return value
    
    def validate(self, data):
        if 'capacity' in data and 'current_load' in data:
            if data['current_load'] > data['capacity']:
                raise serializers.ValidationError({
                    "current_load": f"Current load ({data['current_load']}) cannot exceed capacity ({data['capacity']})"
                })
        elif 'current_load' in data and hasattr(self.instance, 'capacity'):
            if data['current_load'] > self.instance.capacity:
                raise serializers.ValidationError({
                    "current_load": f"Current load ({data['current_load']}) cannot exceed capacity ({self.instance.capacity})"
                })
        return data


# ================= INVENTORY SERIALIZERS =================

class InventorySerializer(serializers.ModelSerializer):
    """Serializer for Inventory model with nested details"""
    
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    bin_location = serializers.CharField(source='bin.bin_id', read_only=True)
    zone_type = serializers.CharField(source='bin.shelf.rack.zone.zone_type', read_only=True)
    available_space = serializers.SerializerMethodField()
    
    class Meta:
        model = Inventory
        fields = [
            'inventory_id', 'product', 'product_name', 'product_sku',
            'bin', 'bin_location', 'zone_type', 'quantity', 
            'available_space', 'created_at', 'updated_at'
        ]
        read_only_fields = ['inventory_id', 'created_at', 'updated_at']
    
    def get_available_space(self, obj):
        if obj.bin:
            return obj.bin.capacity - obj.bin.current_load
        return None
    
    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative")
        return value
    
    def validate(self, data):
        # Check if product and bin combination already exists
        if not self.instance:  # Only for create operations
            product = data.get('product')
            bin_obj = data.get('bin')
            if product and bin_obj:
                if Inventory.objects.filter(product=product, bin=bin_obj).exists():
                    raise serializers.ValidationError(
                        "Inventory record already exists for this product in this bin"
                    )
        
        # Validate bin capacity
        if 'quantity' in data and 'bin' in data:
            bin_obj = data['bin']
            current_quantity = data['quantity']
            
            # Get total in bin including this new inventory
            other_inventory = Inventory.objects.filter(bin=bin_obj)
            if self.instance:
                other_inventory = other_inventory.exclude(inventory_id=self.instance.inventory_id)
            
            total_in_bin = other_inventory.aggregate(total=sum('quantity'))['total'] or 0
            total_in_bin += current_quantity
            
            if total_in_bin > bin_obj.capacity:
                raise serializers.ValidationError({
                    "quantity": f"Total quantity in bin ({total_in_bin}) would exceed bin capacity ({bin_obj.capacity})"
                })
        
        return data


# ================= PURCHASE REQUEST SERIALIZER =================

class PurchaseRequestSerializer(serializers.ModelSerializer):
    """Serializer for PurchaseRequest with validation"""
    
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True)
    
    class Meta:
        model = PurchaseRequest
        fields = [
            'pr_id', 'product', 'product_name', 'vendor', 'vendor_name',
            'requested_quantity', 'total_amount', 'status', 'created_by',
            'created_by_username', 'approved_by', 'approved_by_username',
            'approved_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['pr_id', 'created_at', 'updated_at', 'total_amount']
    
    def validate_requested_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Requested quantity must be greater than 0")
        return value
    
    def validate(self, data):
        # Calculate total amount if not provided
        if 'requested_quantity' in data and 'product' in data:
            product = data.get('product')
            if product and hasattr(product, 'unit_price'):
                data['total_amount'] = data['requested_quantity'] * product.unit_price
        
        # Validate status transitions
        if self.instance and 'status' in data:
            old_status = self.instance.status
            new_status = data['status']
            valid_transitions = {
                'PENDING': ['MANAGER_APPROVED', 'FINANCE_PENDING', 'REJECTED'],
                'MANAGER_APPROVED': ['APPROVED', 'FINANCE_PENDING'],
                'FINANCE_PENDING': ['APPROVED', 'REJECTED'],
                'APPROVED': [],
                'REJECTED': []
            }
            
            if new_status not in valid_transitions.get(old_status, []):
                raise serializers.ValidationError({
                    "status": f"Cannot transition from '{old_status}' to '{new_status}'"
                })
        
        return data


# ================= PURCHASE ORDER SERIALIZER =================

class PurchaseOrderSerializer(serializers.ModelSerializer):
    """Serializer for PurchaseOrder with nested PR details"""
    
    pr_id = serializers.CharField(source='pr.pr_id', read_only=True)
    product_name = serializers.CharField(source='pr.product.product_name', read_only=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'po_id', 'pr', 'pr_id', 'product_name', 'vendor', 'vendor_name',
            'order_quantity', 'total_amount', 'status', 'created_by',
            'created_by_username', 'created_at', 'updated_at'
        ]
        read_only_fields = ['po_id', 'created_at', 'updated_at']
    
    def validate_order_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Order quantity must be greater than 0")
        return value
    
    def validate(self, data):
        # Validate that order quantity matches PR requested quantity
        if 'pr' in data and 'order_quantity' in data:
            pr = data['pr']
            if data['order_quantity'] != pr.requested_quantity:
                raise serializers.ValidationError({
                    "order_quantity": f"Order quantity ({data['order_quantity']}) must match PR requested quantity ({pr.requested_quantity})"
                })
        
        return data


# ================= ASN SERIALIZERS =================

class ASNItemSerializer(serializers.ModelSerializer):
    """Serializer for ASNItem with product details"""
    
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = ASNItem
        fields = [
            'asn_item_id', 'asn', 'product', 'product_name', 'product_sku',
            'expected_quantity', 'shipped_quantity', 'received_quantity',
            'created_at'
        ]
        read_only_fields = ['asn_item_id', 'created_at']
    
    def validate_shipped_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Shipped quantity cannot be negative")
        return value
    
    def validate(self, data):
        # Validate shipped quantity vs expected quantity
        if 'shipped_quantity' in data:
            shipped = data['shipped_quantity']
            expected = data.get('expected_quantity', 
                               self.instance.expected_quantity if self.instance else None)
            
            if expected and shipped > expected:
                raise serializers.ValidationError({
                    "shipped_quantity": f"Shipped quantity ({shipped}) cannot exceed expected quantity ({expected})"
                })
        
        return data


class ASNSerializer(serializers.ModelSerializer):
    """Serializer for ASN with nested items"""
    
    po_id = serializers.CharField(source='po.po_id', read_only=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    items = ASNItemSerializer(many=True, read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = ASN
        fields = [
            'asn_id', 'po', 'po_id', 'asn_number', 'vendor', 'vendor_name',
            'shipment_date', 'expected_arrival_date', 'actual_arrival_date',
            'vehicle_num', 'driver_name', 'driver_phone', 'status',
            'created_by', 'created_by_username', 'created_at', 'updated_at',
            'items'
        ]
        read_only_fields = ['asn_id', 'created_at', 'updated_at']
    
    def validate_expected_arrival_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Expected arrival date cannot be in the past")
        return value
    
    def validate_shipment_date(self, value):
        if value > timezone.now().date():
            raise serializers.ValidationError("Shipment date cannot be in the future")
        return value


# ================= GRN SERIALIZERS =================

class GRNCreateSerializer(serializers.ModelSerializer):
    """
    Used by SupervisorCreateGRN.
    - Writable: po, asn, receipt_date, grn_number
    - Auto-set by view: received_by, status (QC_PENDING)
    """
    
    class Meta:
        model = GRN
        fields = [
            "grn_id", "grn_number", "po", "asn", "receipt_date",
            "received_by", "qc_verified_by", "status", "notes", "created_at"
        ]
        read_only_fields = ["grn_id", "received_by", "qc_verified_by", "status", "created_at"]
    
    def validate_receipt_date(self, value):
        if value > timezone.now().date():
            raise serializers.ValidationError("Receipt date cannot be in the future")
        return value
    
    def validate(self, data):
        # Validate that PO exists and is in correct status
        po = data.get('po')
        if po and po.status not in ['SHIPPED', 'RECEIVED']:
            raise serializers.ValidationError({
                "po": f"PO must be in SHIPPED or RECEIVED status. Current status: {po.status}"
            })
        
        # Validate that ASN matches PO if provided
        asn = data.get('asn')
        if asn and asn.po != po:
            raise serializers.ValidationError({
                "asn": "ASN must belong to the same PO"
            })
        
        return data


class GRNItemCreateSerializer(serializers.ModelSerializer):
    """
    Used by SupervisorAddGRNItems.
    - Writable: grn, product, received_quantity
    - QC fields are rejected at input
    """
    
    class Meta:
        model = GRNItem
        fields = [
            "grn_item_id", "grn", "product", "received_quantity",
            "accepted_quantity", "rejected_quantity", "qc_status", "qc_notes"
        ]
        read_only_fields = [
            "grn_item_id", "accepted_quantity", "rejected_quantity", 
            "qc_status", "qc_notes"
        ]
    
    def validate_received_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Received quantity must be greater than 0")
        return value
    
    def validate(self, data):
        # Validate that GRN is in correct status
        grn = data.get('grn')
        if grn and grn.status != 'QC_PENDING':
            raise serializers.ValidationError({
                "grn": f"GRN must be in QC_PENDING status. Current status: {grn.status}"
            })
        
        # Check for duplicate product in same GRN
        if grn and 'product' in data:
            if GRNItem.objects.filter(grn=grn, product=data['product']).exists():
                raise serializers.ValidationError({
                    "product": "This product already exists in this GRN"
                })
        
        return data


class GRNItemQCSerializer(serializers.ModelSerializer):
    """
    Used by QCUpdateGRNItem.
    - Writable: accepted_quantity, rejected_quantity, qc_notes
    """
    
    class Meta:
        model = GRNItem
        fields = [
            "grn_item_id", "grn", "product", "received_quantity",
            "accepted_quantity", "rejected_quantity", "qc_status", "qc_notes"
        ]
        read_only_fields = ["grn_item_id", "grn", "product", "received_quantity"]
    
    def validate(self, data):
        accepted = data.get("accepted_quantity", self.instance.accepted_quantity)
        rejected = data.get("rejected_quantity", self.instance.rejected_quantity)
        qc_notes = data.get("qc_notes", self.instance.qc_notes)
        received = self.instance.received_quantity
        
        if accepted < 0:
            raise serializers.ValidationError({"accepted_quantity": "Accepted quantity cannot be negative"})
        
        if rejected < 0:
            raise serializers.ValidationError({"rejected_quantity": "Rejected quantity cannot be negative"})
        
        if accepted + rejected > received:
            raise serializers.ValidationError(
                f"Accepted + rejected ({accepted + rejected}) exceeds received ({received})."
            )
        
        # If everything is rejected, maybe require notes
        if accepted == 0 and rejected > 0 and not qc_notes:
            raise serializers.ValidationError({
                "qc_notes": "Please provide reason for rejection"
            })
        
        return data


class GRNItemReadSerializer(serializers.ModelSerializer):
    """Full detail for reading GRN items"""
    
    product_name = serializers.CharField(source="product.product_name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    unit_price = serializers.DecimalField(source="product.unit_price", read_only=True, max_digits=10, decimal_places=2)
    
    class Meta:
        model = GRNItem
        fields = [
            "grn_item_id", "grn", "product", "product_name", "product_sku",
            "received_quantity", "accepted_quantity", "rejected_quantity",
            "qc_status", "qc_notes", "unit_price", "created_at", "updated_at"
        ]


class GRNReadSerializer(serializers.ModelSerializer):
    """Full detail for reading GRN with nested items and summary"""
    
    items = GRNItemReadSerializer(many=True, read_only=True)
    po_id = serializers.CharField(source="po.po_id", read_only=True)
    po_number = serializers.CharField(source="po.po_id", read_only=True)
    asn_id = serializers.CharField(source="asn.asn_id", read_only=True, allow_null=True)
    asn_number = serializers.CharField(source="asn.asn_number", read_only=True, allow_null=True)
    received_by_username = serializers.CharField(
        source="received_by.username", read_only=True, allow_null=True
    )
    qc_verified_by_username = serializers.CharField(
        source="qc_verified_by.username", read_only=True, allow_null=True
    )
    total_received = serializers.SerializerMethodField()
    total_accepted = serializers.SerializerMethodField()
    total_rejected = serializers.SerializerMethodField()
    acceptance_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = GRN
        fields = [
            "grn_id", "grn_number", "po_id", "po_number", "asn_id", "asn_number",
            "receipt_date", "received_by_username", "qc_verified_by_username",
            "status", "notes", "created_at", "completed_at", "items",
            "total_received", "total_accepted", "total_rejected", "acceptance_rate"
        ]
    
    def get_total_received(self, obj):
        return obj.items.aggregate(total=models.Sum('received_quantity'))['total'] or 0
    
    def get_total_accepted(self, obj):
        return obj.items.aggregate(total=models.Sum('accepted_quantity'))['total'] or 0
    
    def get_total_rejected(self, obj):
        return obj.items.aggregate(total=models.Sum('rejected_quantity'))['total'] or 0
    
    def get_acceptance_rate(self, obj):
        received = self.get_total_received(obj)
        if received > 0:
            accepted = self.get_total_accepted(obj)
            return round((accepted / received) * 100, 2)
        return 0


# ================= STOCK MOVEMENT SERIALIZER =================

class StockMovementSerializer(serializers.ModelSerializer):
    """Serializer for stock movement tracking"""
    
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    bin_location = serializers.CharField(source='bin.bin_id', read_only=True)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = StockMovement
        fields = [
            'movement_id', 'product', 'product_name', 'product_sku',
            'bin', 'bin_location', 'movement_type', 'movement_type_display',
            'quantity', 'previous_stock', 'new_stock', 'reference',
            'created_by', 'created_by_username', 'created_at'
        ]
        read_only_fields = ['movement_id', 'created_at']


# ================= INBOUND/OUTBOUND TRANSACTION SERIALIZERS =================

class InboundTransSerializer(serializers.ModelSerializer):
    """Serializer for inbound transactions"""
    
    received_by_username = serializers.CharField(source='received_by.username', read_only=True)
    
    class Meta:
        model = inbound_trans
        fields = [
            'inbound_id', 'po_id', 'received_by', 'received_by_username',
            'status', 'created_at', 'completed_at'
        ]
        read_only_fields = ['inbound_id', 'created_at']


class OutboundTransSerializer(serializers.ModelSerializer):
    """Serializer for outbound transactions"""
    
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    product_name = serializers.SerializerMethodField()
    
    class Meta:
        model = outbound_trans
        fields = [
            'outbound_id', 'product_id', 'product_name', 'quantity',
            'created_by', 'created_by_username', 'status', 'created_at', 'completed_at'
        ]
        read_only_fields = ['outbound_id', 'created_at']
    
    def get_product_name(self, obj):
        try:
            product = Product.objects.get(product_id=obj.product_id)
            return product.product_name
        except Product.DoesNotExist:
            return None


# ================= HELPER FUNCTIONS =================

def validate_unique_together(instance, field1, field2, model):
    """Helper to validate unique_together constraints"""
    queryset = model.objects.filter(**{field1: getattr(instance, field1)})
    queryset = queryset.filter(**{field2: getattr(instance, field2)})
    
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    
    if queryset.exists():
        raise serializers.ValidationError(
            f"{field1} and {field2} must be unique together."
        )