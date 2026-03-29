from rest_framework import serializers
from .models import Vendor, Warehouse, VendorProductMapping, PurchasePriceHistory


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = "__all__"
        read_only_fields = ["warehouse_id", "created_at"]


class VendorSerializer(serializers.ModelSerializer):
    contact_person = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Vendor
        fields = "__all__"
        read_only_fields = ["vendor_id", "created_at", "updated_at", "warehouse"]


class VendorProductMappingSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.vendor_name', read_only=True)
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_sku = serializers.CharField(source='product.sku_code', read_only=True)
    
    class Meta:
        model = VendorProductMapping
        fields = "__all__"
        read_only_fields = ["mapping_id", "created_at", "updated_at", "last_purchase_price"]
    
    def validate_agreed_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value
    
    def validate_min_order_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Minimum order quantity must be at least 1")
        return value


class PurchasePriceHistorySerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.vendor_name', read_only=True)
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    
    class Meta:
        model = PurchasePriceHistory
        fields = "__all__"
        read_only_fields = ["history_id", "created_at"]