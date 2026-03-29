from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import Warehouse, Vendor, VendorProductMapping, PurchasePriceHistory


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    """Admin configuration for Warehouse model"""
    
    list_display = [
        'warehouse_id',
        'warehouse_name',
        'warehouse_email',
        'warehouse_phone',
        'address_preview',
        'vendor_count',
        'created_at'
    ]
    
    search_fields = [
        'warehouse_id',
        'warehouse_name',
        'warehouse_email',
        'address'
    ]
    
    readonly_fields = ['warehouse_id', 'created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('warehouse_id', 'warehouse_name', 'warehouse_email', 'warehouse_phone')
        }),
        ('Address', {
            'fields': ('address',)
        }),
        ('Audit Information', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def address_preview(self, obj):
        """Preview address"""
        return obj.address[:50] + '...' if len(obj.address) > 50 else obj.address
    address_preview.short_description = 'Address'
    
    def vendor_count(self, obj):
        """Count vendors in this warehouse"""
        count = obj.vendors.count()
        url = reverse('admin:vendors_vendor_changelist') + f'?warehouse__id={obj.warehouse_id}'
        return format_html('<a href="{}">{} Vendor(s)</a>', url, count)
    vendor_count.short_description = 'Vendors'


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    """Admin configuration for Vendor model"""
    
    list_display = [
        'vendor_id',
        'vendor_name',
        'contact_person',
        'email',
        'phone',
        'lead_time',
        'status_badge',
        'verification_badge',
        'product_count',
        'warehouse_link',
        'created_at'
    ]
    
    list_filter = [
        'status',
        'is_email_verified',
        'is_active',
        'country',
        'state',
        'created_at',
        ('warehouse', admin.RelatedOnlyFieldListFilter),
    ]
    
    search_fields = [
        'vendor_id',
        'vendor_name',
        'contact_person',
        'email',
        'phone',
        'gst_number',
        'pan_number'
    ]
    
    readonly_fields = [
        'vendor_id',
        'created_at',
        'updated_at',
        'verification_token',
        'verification_token_created_at',
        'email_verified_at',
        'verification_status_display',
        'product_mappings_link',
        'price_history_link'
    ]
    
    list_editable = ['is_active']
    
    list_per_page = 50
    
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'vendor_id',
                'vendor_name',
                'contact_person',
                'email',
                'phone',
                'lead_time'
            )
        }),
        ('Address', {
            'fields': (
                'address',
                'city',
                'state',
                'country'
            )
        }),
        ('Tax Information', {
            'fields': (
                'gst_number',
                'pan_number'
            ),
            'classes': ('collapse',)
        }),
        ('Verification & Status', {
            'fields': (
                'status',
                'is_active',
                'is_email_verified',
                'verification_status_display',
                'email_verified_at',
                'verification_token',
                'verification_token_created_at'
            ),
            'classes': ('wide',)
        }),
        ('Relationships', {
            'fields': (
                'warehouse',
                'product_mappings_link',
                'price_history_link'
            )
        }),
        ('Audit Information', {
            'fields': (
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status badge"""
        colors = {
            'ACTIVE': '#28a745',
            'PENDING': '#ffc107',
            'SUSPENDED': '#dc3545',
            'REJECTED': '#6c757d',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.status
        )
    status_badge.short_description = 'Status'
    
    def verification_badge(self, obj):
        """Display verification badge"""
        if obj.is_email_verified:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 8px; border-radius: 12px;">✓ Verified</span>'
            )
        elif obj.verification_token and not obj.is_verification_token_expired():
            return format_html(
                '<span style="background-color: #ffc107; color: black; padding: 2px 8px; border-radius: 12px;">⏳ Pending</span>'
            )
        elif obj.verification_token and obj.is_verification_token_expired():
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 2px 8px; border-radius: 12px;">⚠️ Expired</span>'
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 2px 8px; border-radius: 12px;">✗ Not Verified</span>'
        )
    verification_badge.short_description = 'Verification'
    
    def verification_status_display(self, obj):
        """Display detailed verification status"""
        if obj.is_email_verified:
            return format_html(
                '<div><strong>✅ Verified</strong><br>'
                'Verified at: {}</div>',
                obj.email_verified_at.strftime('%Y-%m-%d %H:%M:%S') if obj.email_verified_at else 'N/A'
            )
        elif obj.verification_token:
            expires_at = obj.verification_token_created_at + timezone.timedelta(hours=48)
            is_expired = obj.is_verification_token_expired()
            return format_html(
                '<div><strong>⏳ Verification Pending</strong><br>'
                'Token: {}<br>'
                'Expires: {}<br>'
                'Status: {}</div>',
                obj.verification_token[:20] + '...',
                expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                '<span style="color: red;">Expired</span>' if is_expired else '<span style="color: green;">Active</span>'
            )
        return '<div><strong>✗ Not Verified</strong><br>No verification initiated</div>'
    verification_status_display.short_description = 'Verification Details'
    
    def warehouse_link(self, obj):
        """Link to warehouse details"""
        url = reverse('admin:vendors_warehouse_change', args=[obj.warehouse.warehouse_id])
        return format_html(
            '<a href="{}" style="text-decoration: none;">{} ({})</a>',
            url,
            obj.warehouse.warehouse_name,
            obj.warehouse.warehouse_id
        )
    warehouse_link.short_description = 'Warehouse'
    
    def product_count(self, obj):
        """Count products mapped to this vendor"""
        from vendors.models import VendorProductMapping
        count = VendorProductMapping.objects.filter(vendor=obj).count()
        if count > 0:
            url = reverse('admin:vendors_vendorproductmapping_changelist') + f'?vendor__id={obj.vendor_id}'
            return format_html('<a href="{}">{} Product(s)</a>', url, count)
        return '0 Products'
    product_count.short_description = 'Products'
    
    def product_mappings_link(self, obj):
        """Link to product mappings"""
        url = reverse('admin:vendors_vendorproductmapping_changelist') + f'?vendor__id={obj.vendor_id}'
        return format_html('<a href="{}">View All Mappings</a>', url)
    product_mappings_link.short_description = 'Product Mappings'
    
    def price_history_link(self, obj):
        """Link to price history"""
        url = reverse('admin:vendors_purchasepricehistory_changelist') + f'?vendor__id={obj.vendor_id}'
        return format_html('<a href="{}">View Price History</a>', url)
    price_history_link.short_description = 'Price History'
    
    # Actions
    actions = ['activate_vendors', 'suspend_vendors', 'resend_verification', 'export_vendors']
    
    def activate_vendors(self, request, queryset):
        """Bulk activate vendors"""
        updated = queryset.update(status='ACTIVE', is_active=True)
        self.message_user(request, f'{updated} vendors were successfully activated.')
    activate_vendors.short_description = 'Activate selected vendors'
    
    def suspend_vendors(self, request, queryset):
        """Bulk suspend vendors"""
        updated = queryset.update(status='SUSPENDED', is_active=False)
        self.message_user(request, f'{updated} vendors were successfully suspended.')
    suspend_vendors.short_description = 'Suspend selected vendors'
    
    def resend_verification(self, request, queryset):
        """Resend verification email"""
        for vendor in queryset:
            if not vendor.is_email_verified:
                vendor.verification_token = vendor.generate_verification_token()
                vendor.verification_token_created_at = timezone.now()
                vendor.save()
                # Send email logic here
                self.message_user(request, f'Verification email sent to {vendor.email}')
    resend_verification.short_description = 'Resend verification email'
    
    def export_vendors(self, request, queryset):
        """Export selected vendors to CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="vendors_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'Name', 'Contact', 'Email', 'Phone', 'Status', 'Verified', 'Country'])
        
        for vendor in queryset:
            writer.writerow([
                vendor.vendor_id,
                vendor.vendor_name,
                vendor.contact_person,
                vendor.email,
                vendor.phone,
                vendor.status,
                'Yes' if vendor.is_email_verified else 'No',
                vendor.country
            ])
        
        return response
    export_vendors.short_description = 'Export selected vendors to CSV'
    
    def get_queryset(self, request):
        """Optimize queries with select_related"""
        return super().get_queryset(request).select_related('warehouse')
    
    def save_model(self, request, obj, form, change):
        """Handle vendor save"""
        if not obj.pk and obj.email:
            obj.status = 'PENDING'
        super().save_model(request, obj, form, change)


@admin.register(VendorProductMapping)
class VendorProductMappingAdmin(admin.ModelAdmin):
    """Admin configuration for VendorProductMapping model"""
    
    list_display = [
        'mapping_id',
        'vendor_link',
        'product_link',
        'vendor_product_code',
        'vendor_product_name',
        'agreed_price_display',
        'last_purchase_price_display',
        'min_order_quantity',
        'is_preferred_badge',
        'is_active_badge',
        'created_at'
    ]
    
    list_filter = [
        'is_preferred',
        'is_active',
        'vendor',
        'product',
        'created_at'
    ]
    
    search_fields = [
        'mapping_id',
        'vendor_product_code',
        'vendor_product_name',
        'vendor__vendor_name',
        'product__product_name'
    ]
    
    readonly_fields = [
        'mapping_id',
        'created_at',
        'updated_at',
        'last_purchase_price'
    ]
    
    list_editable = [
        'agreed_price',
        'min_order_quantity',
        'is_preferred',
        'is_active'
    ]
    
    list_per_page = 50
    
    fieldsets = (
        ('Vendor & Product', {
            'fields': (
                'vendor',
                'product'
            )
        }),
        ('Vendor Product Information', {
            'fields': (
                'vendor_product_code',
                'vendor_product_name',
                'vendor_description'
            )
        }),
        ('Pricing', {
            'fields': (
                'agreed_price',
                'last_purchase_price'
            )
        }),
        ('Business Terms', {
            'fields': (
                'min_order_quantity',
                'lead_time',
                'is_preferred',
                'is_active'
            )
        }),
        ('Audit Information', {
            'fields': (
                'mapping_id',
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def vendor_link(self, obj):
        """Link to vendor"""
        url = reverse('admin:vendors_vendor_change', args=[obj.vendor.vendor_id])
        return format_html('<a href="{}">{}</a>', url, obj.vendor.vendor_name)
    vendor_link.short_description = 'Vendor'
    vendor_link.admin_order_field = 'vendor__vendor_name'
    
    def product_link(self, obj):
        """Link to product"""
        url = reverse('admin:products_product_change', args=[obj.product.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product.product_name)
    product_link.short_description = 'Product'
    product_link.admin_order_field = 'product__product_name'
    
    def agreed_price_display(self, obj):
        """Display agreed price with currency"""
        return format_html('₹{:.2f}', obj.agreed_price)
    agreed_price_display.short_description = 'Agreed Price'
    
    def last_purchase_price_display(self, obj):
        """Display last purchase price"""
        if obj.last_purchase_price:
            return format_html('₹{:.2f}', obj.last_purchase_price)
        return '-'
    last_purchase_price_display.short_description = 'Last Purchase'
    
    def is_preferred_badge(self, obj):
        """Display preferred badge"""
        if obj.is_preferred:
            return format_html('<span style="color: #28a745;">★ Preferred</span>')
        return '-'
    is_preferred_badge.short_description = 'Preferred'
    
    def is_active_badge(self, obj):
        """Display active badge"""
        if obj.is_active:
            return format_html('<span style="color: #28a745;">Active</span>')
        return format_html('<span style="color: #dc3545;">Inactive</span>')
    is_active_badge.short_description = 'Status'
    
    def get_queryset(self, request):
        """Optimize queries with select_related"""
        return super().get_queryset(request).select_related('vendor', 'product')


@admin.register(PurchasePriceHistory)
class PurchasePriceHistoryAdmin(admin.ModelAdmin):
    """Admin configuration for PurchasePriceHistory model"""
    
    list_display = [
        'history_id',
        'product_link',
        'vendor_link',
        'quantity',
        'unit_price_display',
        'total_amount_display',
        'purchase_date',
        'invoice_number'
    ]
    
    list_filter = [
        'purchase_date',
        'vendor',
        'product',
        'created_at'
    ]
    
    search_fields = [
        'history_id',
        'invoice_number',
        'product__product_name',
        'vendor__vendor_name'
    ]
    
    readonly_fields = [
        'history_id',
        'created_at'
    ]
    
    list_per_page = 50
    
    date_hierarchy = 'purchase_date'
    
    fieldsets = (
        ('Purchase Details', {
            'fields': (
                'product',
                'vendor',
                'purchase_order',
                'quantity',
                'unit_price',
                'total_amount',
                'purchase_date'
            )
        }),
        ('Reference', {
            'fields': (
                'invoice_number',
            )
        }),
        ('Audit Information', {
            'fields': (
                'history_id',
                'created_at'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def product_link(self, obj):
        """Link to product"""
        url = reverse('admin:products_product_change', args=[obj.product.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product.product_name)
    product_link.short_description = 'Product'
    
    def vendor_link(self, obj):
        """Link to vendor"""
        url = reverse('admin:vendors_vendor_change', args=[obj.vendor.vendor_id])
        return format_html('<a href="{}">{}</a>', url, obj.vendor.vendor_name)
    vendor_link.short_description = 'Vendor'
    
    def unit_price_display(self, obj):
        """Display unit price with currency"""
        return format_html('₹{:.2f}', obj.unit_price)
    unit_price_display.short_description = 'Unit Price'
    
    def total_amount_display(self, obj):
        """Display total amount with currency"""
        return format_html('<strong>₹{:.2f}</strong>', obj.total_amount)
    total_amount_display.short_description = 'Total Amount'
    
    def get_queryset(self, request):
        """Optimize queries with select_related"""
        return super().get_queryset(request).select_related('product', 'vendor', 'purchase_order')
    
    def has_add_permission(self, request):
        """Prevent manual addition - should come from invoice processing"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent manual changes"""
        return False

