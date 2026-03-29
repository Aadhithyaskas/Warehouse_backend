from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Sum
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin configuration for Product model"""
    
    # List display
    list_display = [
        'product_id',
        'product_name',
        'brand_name',
        'size',
        'sku_code',
        'quantity_display',
        'unit_price_display',
        're_order',
        'abc_display',
        'ved_display',
        'xyz_display',
        'status_badge',
        'vendor_link',
        'avg_purchase_cost_display',
        'created_at'
    ]
    
    # List filters
    list_filter = [
        'ABC',
        'VED',
        'XYZ',
        'is_active',
        'brand_name',
        'created_at',
        ('vendor', admin.RelatedOnlyFieldListFilter),
    ]
    
    # Search fields
    search_fields = [
        'product_id',
        'product_name',
        'brand_name',
        'sku_code',
        'description',
        'vendor__vendor_name'
    ]
    
    # Read-only fields
    readonly_fields = [
        'product_id',
        'sku_code',
        'created_at',
        'updated_at',
        'avg_purchase_cost',
        'total_stock_value_display',
        'vendor_mappings_link'
    ]
    
    # Editable fields in list view
    list_editable = [
        'quantity',
        'unit_price',
        're_order',
        'is_active'
    ]
    
    # List per page
    list_per_page = 50
    
    # Date hierarchy
    date_hierarchy = 'created_at'
    
    # Fieldsets for detail view
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'product_id',
                'product_name',
                'brand_name',
                'size',
                'sku_code',
                'description'
            )
        }),
        ('Classification', {
            'fields': (
                'ABC',
                'VED',
                'XYZ'
            ),
            'description': 'Product classification for inventory management'
        }),
        ('Inventory Details', {
            'fields': (
                'quantity',
                'unit_price',
                're_order',
                'avg_purchase_cost',
                'total_stock_value_display'
            )
        }),
        ('Supplier Information', {
            'fields': (
                'vendor',
                'preferred_vendor',
                'vendor_mappings_link'
            ),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': (
                'is_active',
            )
        }),
        ('Audit Information', {
            'fields': (
                'created_by',
                'updated_by',
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )
    
    # Custom display methods
    def quantity_display(self, obj):
        """Display quantity with color coding for low stock"""
        if obj.quantity <= obj.re_order:
            return format_html(
                '<span style="color: red; font-weight: bold;">⚠️ {}</span>',
                obj.quantity
            )
        return format_html(
            '<span style="color: green;">✅ {}</span>',
            obj.quantity
        )
    quantity_display.short_description = 'Quantity'
    quantity_display.admin_order_field = 'quantity'
    
    def unit_price_display(self, obj):
        """Display unit price with currency"""
        return format_html('₹{:.2f}', obj.unit_price)
    unit_price_display.short_description = 'Unit Price'
    unit_price_display.admin_order_field = 'unit_price'
    
    def avg_purchase_cost_display(self, obj):
        """Display average purchase cost"""
        return format_html('₹{:.2f}', obj.avg_purchase_cost)
    avg_purchase_cost_display.short_description = 'Avg Purchase Cost'
    
    def total_stock_value_display(self, obj):
        """Calculate total stock value"""
        total_value = obj.quantity * obj.unit_price
        return format_html('<strong>₹{:.2f}</strong>', total_value)
    total_stock_value_display.short_description = 'Total Stock Value'
    
    def abc_display(self, obj):
        """Display ABC classification with colors"""
        colors = {
            'A': '#28a745',  # Green
            'B': '#ffc107',  # Yellow
            'C': '#dc3545',  # Red
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.ABC, '#6c757d'),
            obj.get_ABC_display()
        )
    abc_display.short_description = 'ABC'
    abc_display.admin_order_field = 'ABC'
    
    def ved_display(self, obj):
        """Display VED classification with colors"""
        colors = {
            'V': '#28a745',  # Green
            'E': '#ffc107',  # Yellow
            'D': '#dc3545',  # Red
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.VED, '#6c757d'),
            obj.get_VED_display()
        )
    ved_display.short_description = 'VED'
    ved_display.admin_order_field = 'VED'
    
    def xyz_display(self, obj):
        """Display XYZ classification with colors"""
        colors = {
            'X': '#28a745',  # Green
            'Y': '#ffc107',  # Yellow
            'Z': '#dc3545',  # Red
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.XYZ, '#6c757d'),
            obj.get_XYZ_display()
        )
    xyz_display.short_description = 'XYZ'
    xyz_display.admin_order_field = 'XYZ'
    
    def status_badge(self, obj):
        """Display status badge"""
        if obj.is_active:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 8px; border-radius: 12px;">Active</span>'
            )
        return format_html(
            '<span style="background-color: #dc3545; color: white; padding: 2px 8px; border-radius: 12px;">Inactive</span>'
        )
    status_badge.short_description = 'Status'
    
    def vendor_link(self, obj):
        """Link to vendor details"""
        if obj.vendor:
            url = reverse('admin:vendors_vendor_change', args=[obj.vendor.vendor_id])
            return format_html(
                '<a href="{}" style="text-decoration: none;">{} ({})</a>',
                url,
                obj.vendor.vendor_name,
                obj.vendor.vendor_id
            )
        return '-'
    vendor_link.short_description = 'Vendor'
    
    def vendor_mappings_link(self, obj):
        """Link to vendor product mappings"""
        from vendors.models import VendorProductMapping
        count = VendorProductMapping.objects.filter(product=obj).count()
        if count > 0:
            url = reverse('admin:vendors_vendorproductmapping_changelist') + f'?product__id={obj.product_id}'
            return format_html(
                '<a href="{}" style="text-decoration: none;">{} Vendor(s)</a>',
                url,
                count
            )
        return 'No vendors mapped'
    vendor_mappings_link.short_description = 'Vendor Mappings'
    
    # Actions
    actions = ['make_active', 'make_inactive', 'update_prices', 'export_products']
    
    def make_active(self, request, queryset):
        """Bulk activate products"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} products were successfully activated.')
    make_active.short_description = 'Activate selected products'
    
    def make_inactive(self, request, queryset):
        """Bulk deactivate products"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} products were successfully deactivated.')
    make_inactive.short_description = 'Deactivate selected products'
    
    def update_prices(self, request, queryset):
        """Bulk update prices"""
        # This would need additional logic
        self.message_user(request, 'Price update feature coming soon.')
    update_prices.short_description = 'Update prices for selected products'
    
    def export_products(self, request, queryset):
        """Export selected products to CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="products_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'Name', 'Brand', 'SKU', 'Quantity', 'Price', 'ABC', 'VED', 'XYZ', 'Status'])
        
        for product in queryset:
            writer.writerow([
                product.product_id,
                product.product_name,
                product.brand_name,
                product.sku_code,
                product.quantity,
                product.unit_price,
                product.ABC,
                product.VED,
                product.XYZ,
                'Active' if product.is_active else 'Inactive'
            ])
        
        return response
    export_products.short_description = 'Export selected products to CSV'
    
    # Override methods
    def get_queryset(self, request):
        """Optimize queries with select_related"""
        return super().get_queryset(request).select_related(
            'vendor',
            'preferred_vendor',
            'created_by',
            'updated_by'
        )
    
    def save_model(self, request, obj, form, change):
        """Set created_by and updated_by automatically"""
        if not obj.pk:  # New object
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_readonly_fields(self, request, obj=None):
        """Make certain fields readonly after creation"""
        if obj:  # Existing object
            return self.readonly_fields + ['product_id', 'sku_code']
        return self.readonly_fields