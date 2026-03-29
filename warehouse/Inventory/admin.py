from django.contrib import admin
from .models import (
    Inventory, PurchaseRequest, PurchaseOrder, 
    ASN, ASNItem, GRN, GRNItem, StockMovement,
    Zone, Rack, Shelf, Bin
)


class InventoryAdmin(admin.ModelAdmin):
    """Admin configuration for Inventory model"""
    
    list_display = [
        'inventory_id', 
        'product', 
        'bin', 
        'quantity',
        'display_bin_location'
    ]
    
    search_fields = [
        'inventory_id', 
        'product__product_name',
        'bin__bin_id'
    ]
    
    list_filter = [
        'product',
        'bin__shelf__rack__zone',
        'bin__shelf__rack',
        'bin__shelf'
    ]
    
    readonly_fields = ['inventory_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('inventory_id', 'product', 'quantity')
        }),
        ('Location Information', {
            'fields': ('bin',)
        }),
        ('Audit Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def display_bin_location(self, obj):
        """Display full bin location"""
        try:
            zone = obj.bin.shelf.rack.zone.zone_type
            rack = obj.bin.shelf.rack.rack_id
            shelf = obj.bin.shelf.shelf_id
            return f"{obj.bin.bin_id} ({zone}/{rack}/{shelf})"
        except AttributeError:
            return obj.bin.bin_id
    display_bin_location.short_description = 'Bin Location'
    
    def get_queryset(self, request):
        """Optimize queries with select_related"""
        return super().get_queryset(request).select_related(
            'product', 'bin', 'bin__shelf', 'bin__shelf__rack', 'bin__shelf__rack__zone'
        )


class BinAdmin(admin.ModelAdmin):
    """Admin configuration for Bin model"""
    
    list_display = [
        'bin_id', 
        'shelf', 
        'capacity', 
        'current_load', 
        'available_capacity',
        'distance_from_dispatch',
        'pick_count',
        'last_picked_at'
    ]
    
    list_filter = [
        'shelf__rack__zone',
        'shelf__rack',
        'shelf'
    ]
    
    search_fields = ['bin_id', 'shelf__shelf_id']
    
    readonly_fields = ['pick_count', 'last_picked_at', 'created_at', 'updated_at']
    
    def available_capacity(self, obj):
        """Calculate available capacity"""
        return obj.capacity - obj.current_load
    available_capacity.short_description = 'Available Capacity'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('bin_id', 'shelf', 'capacity', 'current_load', 'distance_from_dispatch')
        }),
        ('Performance Metrics', {
            'fields': ('pick_count', 'last_picked_at'),
            'classes': ('collapse',)
        }),
        ('Audit Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('shelf__rack__zone')


class ZoneAdmin(admin.ModelAdmin):
    """Admin configuration for Zone model"""
    
    list_display = ['zone_id', 'zone_type', 'created_at']
    list_filter = ['zone_type']
    search_fields = ['zone_id']
    readonly_fields = ['zone_id', 'created_at', 'updated_at']


class RackAdmin(admin.ModelAdmin):
    """Admin configuration for Rack model"""
    
    list_display = ['rack_id', 'zone', 'zone_type', 'created_at']
    search_fields = ['rack_id', 'zone__zone_id']
    list_filter = ['zone__zone_type']
    readonly_fields = ['rack_id', 'created_at']
    
    def zone_type(self, obj):
        """Display zone type"""
        return obj.zone.zone_type
    zone_type.short_description = 'Zone Type'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('zone')


class ShelfAdmin(admin.ModelAdmin):
    """Admin configuration for Shelf model"""
    
    list_display = ['shelf_id', 'rack', 'zone', 'rack_id_display', 'created_at']
    search_fields = ['shelf_id', 'rack__rack_id']
    list_filter = ['rack__zone']
    readonly_fields = ['shelf_id', 'created_at']
    
    def zone(self, obj):
        """Display zone"""
        return obj.rack.zone.zone_id
    zone.short_description = 'Zone'
    
    def rack_id_display(self, obj):
        """Display rack ID"""
        return obj.rack.rack_id
    rack_id_display.short_description = 'Rack ID'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('rack__zone')


class PurchaseRequestAdmin(admin.ModelAdmin):
    """Admin configuration for PurchaseRequest model"""
    
    list_display = [
        'pr_id', 'product', 'vendor', 'requested_quantity', 
        'total_amount', 'status', 'created_by', 'created_at'
    ]
    
    list_filter = ['status', 'created_at']
    search_fields = ['pr_id', 'product__product_name', 'vendor__vendor_name']
    readonly_fields = ['pr_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('pr_id', 'product', 'vendor', 'requested_quantity', 'total_amount')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Approval Information', {
            'fields': ('created_by', 'approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
        ('Audit Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'vendor', 'created_by', 'approved_by')


class PurchaseOrderAdmin(admin.ModelAdmin):
    """Admin configuration for PurchaseOrder model"""
    
    list_display = [
        'po_id', 'pr', 'vendor', 'order_quantity', 
        'total_amount', 'status', 'created_at'
    ]
    
    list_filter = ['status', 'created_at']
    search_fields = ['po_id', 'pr__pr_id', 'vendor__vendor_name']
    readonly_fields = ['po_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('po_id', 'pr', 'vendor', 'order_quantity', 'total_amount')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Audit Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('pr', 'vendor', 'created_by')


class ASNAdmin(admin.ModelAdmin):
    """Admin configuration for ASN model"""
    
    list_display = [
        'asn_id', 'po', 'asn_number', 'vendor', 'shipment_date',
        'expected_arrival_date', 'status', 'created_at'
    ]
    
    list_filter = ['status', 'shipment_date', 'expected_arrival_date']
    search_fields = ['asn_id', 'asn_number', 'po__po_id', 'vendor__vendor_name']
    readonly_fields = ['asn_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('asn_id', 'po', 'asn_number', 'vendor')
        }),
        ('Shipping Information', {
            'fields': ('shipment_date', 'expected_arrival_date', 'actual_arrival_date')
        }),
        ('Transport Information', {
            'fields': ('vehicle_num', 'driver_name', 'driver_phone')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Audit Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('po', 'vendor', 'created_by')


class ASNItemAdmin(admin.ModelAdmin):
    """Admin configuration for ASNItem model"""
    
    list_display = [
        'asn_item_id', 'asn', 'product', 'expected_quantity', 
        'shipped_quantity', 'received_quantity', 'created_at'
    ]
    
    list_filter = ['created_at']
    search_fields = ['asn_item_id', 'asn__asn_id', 'product__product_name']
    readonly_fields = ['asn_item_id', 'created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('asn', 'product')


class GRNAdmin(admin.ModelAdmin):
    """Admin configuration for GRN model"""
    
    list_display = [
        'grn_id', 'grn_number', 'po', 'asn', 'receipt_date', 
        'status', 'received_by', 'created_at'
    ]
    
    list_filter = ['status', 'receipt_date', 'created_at']
    search_fields = ['grn_id', 'grn_number', 'po__po_id', 'asn__asn_number']
    readonly_fields = ['grn_id', 'created_at', 'completed_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('grn_id', 'grn_number', 'po', 'asn', 'receipt_date')
        }),
        ('Status', {
            'fields': ('status', 'notes')
        }),
        ('Personnel', {
            'fields': ('received_by', 'qc_verified_by')
        }),
        ('Audit Information', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('po', 'asn', 'received_by', 'qc_verified_by')


class GRNItemAdmin(admin.ModelAdmin):
    """Admin configuration for GRNItem model"""
    
    list_display = [
        'grn_item_id', 'grn', 'product', 'received_quantity', 
        'accepted_quantity', 'rejected_quantity', 'qc_status', 'qc_complete'
    ]
    
    list_filter = ['qc_status', 'created_at']
    search_fields = ['grn_item_id', 'grn__grn_id', 'product__product_name']
    readonly_fields = ['grn_item_id', 'created_at', 'updated_at']
    
    def qc_complete(self, obj):
        """Display if QC is complete"""
        return obj.qc_status == 'COMPLETED'
    qc_complete.boolean = True
    qc_complete.short_description = 'QC Complete'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('grn', 'product')


class StockMovementAdmin(admin.ModelAdmin):
    """Admin configuration for StockMovement model"""
    
    # FIXED: Changed from 'id' to 'movement_id'
    list_display = [
        'movement_id', 
        'product', 
        'bin', 
        'movement_type', 
        'quantity', 
        'previous_stock', 
        'new_stock', 
        'created_at',
        'movement_direction'
    ]
    
    list_filter = ['movement_type', 'created_at']
    search_fields = [
        'movement_id', 
        'product__product_name', 
        'bin__bin_id',
        'reference'
    ]
    
    readonly_fields = ['movement_id', 'created_at']
    
    def movement_direction(self, obj):
        """Display movement direction with icon"""
        if obj.movement_type in ['INBOUND', 'STOCK_ADDITION']:
            return '⬆️ In'
        elif obj.movement_type in ['OUTBOUND', 'STOCK_REMOVAL']:
            return '⬇️ Out'
        return '🔄 Transfer'
    movement_direction.short_description = 'Direction'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('movement_id', 'product', 'bin', 'movement_type', 'quantity')
        }),
        ('Stock Details', {
            'fields': ('previous_stock', 'new_stock')
        }),
        ('Reference', {
            'fields': ('reference', 'created_by'),
            'classes': ('collapse',)
        }),
        ('Audit Information', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'bin', 'created_by')
    
    def has_add_permission(self, request):
        """Stock movements should not be created manually in admin"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Stock movements should not be changed manually in admin"""
        return False


# Register all models with their admin classes
admin.site.register(Inventory, InventoryAdmin)
admin.site.register(Bin, BinAdmin)
admin.site.register(Zone, ZoneAdmin)
admin.site.register(Rack, RackAdmin)
admin.site.register(Shelf, ShelfAdmin)
admin.site.register(PurchaseRequest, PurchaseRequestAdmin)
admin.site.register(PurchaseOrder, PurchaseOrderAdmin)
admin.site.register(ASN, ASNAdmin)
admin.site.register(ASNItem, ASNItemAdmin)
admin.site.register(GRN, GRNAdmin)
admin.site.register(GRNItem, GRNItemAdmin)
admin.site.register(StockMovement, StockMovementAdmin)