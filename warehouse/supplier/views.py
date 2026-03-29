import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services import SupplierService


@csrf_exempt
def create_supplier(request):

    if request.method == "POST":
        try:
            data = json.loads(request.body)

            supplier = SupplierService.create_supplier(data)

            return JsonResponse({
                "message": "Supplier created successfully",
                "supplier_id": supplier.supplier_id
            }, status=201)

        except Exception as e:
            return JsonResponse({
                "error": str(e)
            }, status=400)

    return JsonResponse({"error": "Invalid method"}, status=405)


# ACTIVE SUPPLIERS
def get_all_suppliers(request):

    suppliers = SupplierService.get_all_suppliers()

    data = list(suppliers.values())

    return JsonResponse(data, safe=False)


# INACTIVE SUPPLIERS (SOFT DELETED)
def get_inactive_suppliers(request):

    suppliers = SupplierService.get_inactive_suppliers()

    data = list(suppliers.values())

    return JsonResponse(data, safe=False)


def get_supplier_by_id(request, supplier_id):

    supplier = SupplierService.get_supplier_by_id(supplier_id)

    if supplier:
        return JsonResponse({
            "supplier_id": supplier.supplier_id,
            "supplier_name": supplier.supplier_name,
            "contact_personname": supplier.contact_personname,
            "email": supplier.email,
            "phone": supplier.phone,
            "address": supplier.address,
            "city": supplier.city,
            "state": supplier.state,
            "country": supplier.country,
            "is_active": supplier.is_active
        })

    return JsonResponse({"error": "Supplier not found"}, status=404)


@csrf_exempt
def update_supplier(request, supplier_id):

    if request.method == "PUT":

        try:
            data = json.loads(request.body)

            supplier = SupplierService.get_supplier_by_id(supplier_id)

            if not supplier:
                return JsonResponse({"error": "Supplier not found"}, status=404)

            SupplierService.update_supplier(supplier, data)

            return JsonResponse({
                "message": "Supplier updated successfully"
            })

        except Exception as e:
            return JsonResponse({
                "error": str(e)
            }, status=400)

    return JsonResponse({"error": "Invalid method"}, status=405)


@csrf_exempt
def delete_supplier(request, supplier_id):

    if request.method == "DELETE":

        supplier = SupplierService.get_supplier_by_id(supplier_id)

        if not supplier:
            return JsonResponse({"error": "Supplier not found"}, status=404)

        supplier.is_active = False
        supplier.save()

        return JsonResponse({
            "message": "Supplier deleted successfully (soft delete)"
        })

    return JsonResponse({"error": "Invalid method"}, status=405)


@csrf_exempt
def restore_supplier(request, supplier_id):

    if request.method == "PUT":

        supplier = SupplierService.restore_supplier(supplier_id)

        if not supplier:
            return JsonResponse({"error": "Supplier not found"}, status=404)

        return JsonResponse({
            "message": "Supplier restored successfully"
        })

    return JsonResponse({"error": "Invalid method"}, status=405)