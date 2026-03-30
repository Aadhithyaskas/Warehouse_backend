# products/serializers.py
from rest_framework import serializers
from .models import Product
from vendors.models import Vendor
from supplier.models import Supplier

class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Product model"""

    # Read-only display fields
    vendor_details = serializers.SerializerMethodField(read_only=True)
    supplier_details = serializers.SerializerMethodField(read_only=True)

    # Write-only IDs
    vendor_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    supplier_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    # Classification display
    abc_display = serializers.CharField(source='get_ABC_display', read_only=True)
    ved_display = serializers.CharField(source='get_VED_display', read_only=True)
    xyz_display = serializers.CharField(source='get_XYZ_display', read_only=True)

    class Meta:
        model = Product
        fields = [
            'product_id',
            'product_name',
            'brand_name',
            'size',
            'sku_code',
            'description',
            'ABC',
            'abc_display',
            'VED',
            'ved_display',
            'XYZ',
            'xyz_display',
            'quantity',
            'unit_price',
            're_order',
            'is_active',
            'vendor',
            'vendor_details',
            'vendor_id',
            'supplier',
            'supplier_details',
            'supplier_id',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'product_id',
            'sku_code',
            'created_at',
            'updated_at',
            'abc_display',
            'ved_display',
            'xyz_display',
            'vendor_details',
            'supplier_details'
        ]

    # ---------- Display Helpers ----------

    def get_vendor_details(self, obj):
        if obj.vendor:
            return {
                "id": obj.vendor.vendor_id,
                "name": obj.vendor.vendor_name
            }
        return None

    def get_supplier_details(self, obj):
        if obj.supplier:
            return {
                "id": obj.supplier.supplier_id,
                "name": obj.supplier.supplier_name
            }
        return None

    # ---------- Validations ----------

    def validate_product_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Product name is required")
        return value.strip()

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Unit price must be greater than 0")
        return value

    def validate(self, data):
        # Handle vendor_id
        vendor_id = data.pop('vendor_id', None)
        if vendor_id is not None:
            try:
                data['vendor'] = Vendor.objects.get(vendor_id=vendor_id)
            except Vendor.DoesNotExist:
                raise serializers.ValidationError({'vendor_id': 'Vendor not found'})

        # Handle supplier_id
        supplier_id = data.pop('supplier_id', None)
        if supplier_id is not None:
            try:
                data['supplier'] = Supplier.objects.get(supplier_id=supplier_id)
            except Supplier.DoesNotExist:
                raise serializers.ValidationError({'supplier_id': 'Supplier not found'})

        return data