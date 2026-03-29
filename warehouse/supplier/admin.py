from django.contrib import admin
from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):

    list_display = (
        "supplier_id",
        "supplier_name",
        "email",
        "phone",
        "city",
        "is_active",
        "created_at"
    )

    search_fields = (
        "supplier_name",
        "supplier_id",
        "email"
    )

    list_filter = (
        "city",
        "state",
        "is_active"
    )