from .models import Supplier
from django.core.mail import send_mail
from django.conf import settings

class SupplierService:

    @staticmethod
    def create_supplier(data):

        supplier = Supplier.objects.create(
            supplier_name=data.get("supplier_name"),
            contact_personname=data.get("contact_personname"),
            email=data.get("email"),
            phone=data.get("phone"),
            address=data.get("address"),
            city=data.get("city"),
            state=data.get("state"),
            country=data.get("country"),
            is_active=data.get("is_active", True)
        )

        if supplier.email:
            SupplierService.send_supplier_email(supplier)

        return supplier


    @staticmethod
    def send_supplier_email(supplier):

        subject = "Supplier Registration - GANU WAREHOUSE"

        message = f"""
Hello {supplier.contact_personname or supplier.supplier_name},

You have been successfully registered as a supplier in our Warehouse System.

Supplier ID : {supplier.supplier_id}
Supplier Name : {supplier.supplier_name}

Thank you for partnering with us.
GANU WAREHOUSE
Warehouse Management Team
"""

        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [supplier.email],
            fail_silently=False
        )


    @staticmethod
    def get_all_suppliers():
        return Supplier.objects.filter(is_active=True)


    @staticmethod
    def get_supplier_by_id(supplier_id):
        return Supplier.objects.filter(
            supplier_id=supplier_id,
            is_active=True
        ).first()


    @staticmethod
    def update_supplier(supplier, data):

        for field, value in data.items():
            setattr(supplier, field, value)

        supplier.save()
        return supplier


    @staticmethod
    def delete_supplier(supplier):
        # Soft delete
        supplier.is_active = False
        supplier.save()
        return supplier
    
    @staticmethod
    def get_deleted_suppliers():
        return Supplier.objects.filter(is_active=False)
    
    
    @staticmethod
    def restore_supplier(supplier_id):

        supplier = Supplier.objects.filter(
        supplier_id=supplier_id,
        is_active=False
        ).first()

        if supplier:
            supplier.is_active = True
            supplier.save()

        return supplier
    
    @staticmethod
    def get_inactive_suppliers():
        
        return Supplier.objects.filter(is_active=False)