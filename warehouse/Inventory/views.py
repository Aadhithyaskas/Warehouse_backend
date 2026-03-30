from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, F
from django.db import transaction
from django.core.mail import send_mail
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import models

from .utils import (
    check_reorder,
    assign_bin,
    generate_putaway_plan,
    confirm_putaway,
    generate_pick_plan,
    confirm_pick,
    get_bin_utilization_report,
    get_stock_alerts,
    validate_putaway_plan,
    validate_pick_plan
)
from .models import (
    Inventory, PurchaseRequest, PurchaseOrder, ASN, ASNItem, 
    GRN, GRNItem, StockMovement, Zone, Rack, Shelf, Bin,
    inbound_trans, outbound_trans
)
from .serializers import (
    InventorySerializer, PurchaseRequestSerializer, PurchaseOrderSerializer,
    ASNSerializer, ASNItemSerializer, GRNCreateSerializer, GRNItemCreateSerializer,
    GRNItemQCSerializer, GRNReadSerializer, GRNItemReadSerializer, BinSerializer
)
from .utils import (
    generate_putaway_plan, confirm_putaway,
    generate_pick_plan, confirm_pick
)
from products.models import Product


# ================= INBOUND =================

class InboundCreateView(APIView):
    """Create inbound transaction record"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        data = request.data
        po_id = data.get("po_id")

        if not po_id:
            return Response({"error": "po_id is required"}, status=400)

        # Verify PO exists
        try:
            purchase_order = PurchaseOrder.objects.get(po_id=po_id)
        except PurchaseOrder.DoesNotExist:
            return Response({"error": "Purchase Order not found"}, status=404)

        inbound = inbound_trans.objects.create(
            po_id=po_id,
            received_by=request.user,
            status="CREATED"
        )

        return Response({
            "message": "Inbound created",
            "inbound_id": inbound.inbound_id,
            "po_id": po_id,
            "status": inbound.status
        }, status=201)


class GeneratePutawayPlanView(APIView):
    """Generate putaway plan for received products"""

    def post(self, request, inbound_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        inbound = get_object_or_404(inbound_trans, inbound_id=inbound_id)

        # Validate inbound status
        if inbound.status != "CREATED":
            return Response({
                "error": f"Cannot generate plan for inbound with status '{inbound.status}'"
            }, status=400)

        product_id = request.data.get("product_id")
        quantity = request.data.get("quantity")

        if not product_id or not quantity:
            return Response({"error": "product_id and quantity are required"}, status=400)

        try:
            qty = int(quantity)
            if qty <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": "quantity must be a positive integer"}, status=400)

        product = get_object_or_404(Product, product_id=product_id)

        try:
            plan = generate_putaway_plan(product, qty)
        except Exception as e:
            return Response({"error": f"Failed to generate putaway plan: {str(e)}"}, status=500)

        return Response({
            "inbound_id": inbound_id,
            "product_id": product_id,
            "total_quantity": qty,
            "plan": [
                {
                    "bin_id": p["bin_id"],
                    "location": p["location"],
                    "quantity": p["quantity"]
                } for p in plan
            ]
        })


class ConfirmPutawayView(APIView):
    """Confirm putaway execution"""

    def post(self, request, inbound_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        inbound = get_object_or_404(inbound_trans, inbound_id=inbound_id)

        # Validate inbound status
        if inbound.status != "CREATED":
            return Response({
                "error": f"Cannot confirm putaway for inbound with status '{inbound.status}'"
            }, status=400)

        product_id = request.data.get("product_id")
        plan = request.data.get("plan")

        if not product_id or not plan:
            return Response({"error": "product_id and plan are required"}, status=400)

        if not isinstance(plan, list) or len(plan) == 0:
            return Response({"error": "plan must be a non-empty list"}, status=400)

        product = get_object_or_404(Product, product_id=product_id)

        try:
            with transaction.atomic():
                confirm_putaway(product, plan, request.user)
                inbound.status = "COMPLETED"
                inbound.save()
        except Exception as e:
            return Response({"error": f"Putaway failed: {str(e)}"}, status=500)

        return Response({
            "message": "Putaway completed successfully",
            "inbound_id": inbound_id,
            "product_id": product_id
        })


# ================= OUTBOUND =================

class OutboundCreateView(APIView):
    """Create outbound transaction record"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        data = request.data
        product_id = data.get("product_id")
        quantity = data.get("quantity")

        if not product_id or not quantity:
            return Response({"error": "product_id and quantity are required"}, status=400)

        try:
            qty = int(quantity)
            if qty <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": "quantity must be a positive integer"}, status=400)

        # Verify product exists
        try:
            product = Product.objects.get(product_id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        outbound = outbound_trans.objects.create(
            product_id=product_id,
            quantity=qty,
            created_by=request.user,
            status="CREATED"
        )

        return Response({
            "message": "Outbound created",
            "outbound_id": outbound.outbound_id,
            "product_id": product_id,
            "quantity": qty,
            "status": outbound.status
        }, status=201)


class GeneratePickPlanView(APIView):
    """Generate picking plan for outbound"""

    def post(self, request, outbound_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        outbound = get_object_or_404(outbound_trans, outbound_id=outbound_id)

        # Validate outbound status
        if outbound.status != "CREATED":
            return Response({
                "error": f"Cannot generate pick plan for outbound with status '{outbound.status}'"
            }, status=400)

        product = get_object_or_404(Product, product_id=outbound.product_id)
        qty = outbound.quantity

        # Check available stock
        total_stock = Inventory.objects.filter(product=product).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        if qty > total_stock:
            return Response({
                "error": f"Insufficient stock. Requested: {qty}, Available: {total_stock}"
            }, status=400)

        try:
            plan = generate_pick_plan(product, qty)
        except Exception as e:
            return Response({"error": f"Failed to generate pick plan: {str(e)}"}, status=500)

        return Response({
            "outbound_id": outbound_id,
            "product_id": product.product_id,
            "requested_quantity": qty,
            "total_available": total_stock,
            "plan": [
                {
                    "bin_id": p["bin_id"],
                    "location": p["location"],
                    "quantity": p["quantity"]
                } for p in plan
            ]
        })


class ConfirmPickView(APIView):
    """Confirm picking execution"""

    def post(self, request, outbound_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        outbound = get_object_or_404(outbound_trans, outbound_id=outbound_id)

        # Validate outbound status
        if outbound.status != "CREATED":
            return Response({
                "error": f"Cannot confirm pick for outbound with status '{outbound.status}'"
            }, status=400)

        plan = request.data.get("plan")

        if not plan:
            return Response({"error": "plan is required"}, status=400)

        if not isinstance(plan, list) or len(plan) == 0:
            return Response({"error": "plan must be a non-empty list"}, status=400)

        try:
            with transaction.atomic():
                confirm_pick(plan, request.user)
                outbound.status = "DISPATCHED"
                outbound.completed_at = timezone.now()
                outbound.save()
        except Exception as e:
            return Response({"error": f"Picking failed: {str(e)}"}, status=500)

        return Response({
            "message": "Picking completed successfully",
            "outbound_id": outbound_id,
            "status": outbound.status
        })


# ═══════════════════════════════════════════════════════════
# ZONE VIEWS
# ═══════════════════════════════════════════════════════════

class CreateZoneView(APIView):
    """Create a new zone"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        zone_type = request.data.get("zone_type")

        if not zone_type:
            return Response({"error": "zone_type is required"}, status=400)

        # Validate zone_type
        valid_types = ["RECEIVING", "STORAGE", "PICKING", "SHIPPING", "RETURNS"]
        if zone_type not in valid_types:
            return Response({
                "error": f"Invalid zone_type. Must be one of: {', '.join(valid_types)}"
            }, status=400)

        zone = Zone.objects.create(zone_type=zone_type)

        return Response({
            "message": "Zone created successfully",
            "zone_id": zone.zone_id,
            "zone_type": zone.zone_type
        }, status=201)


class ListZoneView(APIView):
    """List all zones"""

    def get(self, request):
        zones = Zone.objects.all()
        data = [{"zone_id": z.zone_id, "zone_type": z.zone_type} for z in zones]
        return Response({
            "count": len(data),
            "data": data
        })


class GetZoneView(APIView):
    """Get zone details"""

    def get(self, request, zone_id):
        zone = get_object_or_404(Zone, zone_id=zone_id)
        return Response({
            "zone_id": zone.zone_id,
            "zone_type": zone.zone_type,
            "created_at": zone.created_at,
            "updated_at": zone.updated_at
        })


class UpdateZoneView(APIView):
    """Update zone details"""

    def put(self, request, zone_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        zone = get_object_or_404(Zone, zone_id=zone_id)

        zone_type = request.data.get("zone_type")
        if zone_type:
            valid_types = ["RECEIVING", "STORAGE", "PICKING", "SHIPPING", "RETURNS"]
            if zone_type not in valid_types:
                return Response({
                    "error": f"Invalid zone_type. Must be one of: {', '.join(valid_types)}"
                }, status=400)
            zone.zone_type = zone_type

        zone.save()

        return Response({
            "message": "Zone updated successfully",
            "zone_id": zone.zone_id,
            "zone_type": zone.zone_type
        })


class DeleteZoneView(APIView):
    """Delete a zone"""

    def delete(self, request, zone_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        zone = get_object_or_404(Zone, zone_id=zone_id)

        # Check if zone has racks
        if Rack.objects.filter(zone=zone).exists():
            return Response({
                "error": "Cannot delete zone with existing racks. Remove racks first."
            }, status=400)

        zone.delete()

        return Response({"message": "Zone deleted successfully"})


# ═══════════════════════════════════════════════════════════
# RACK VIEWS
# ═══════════════════════════════════════════════════════════

class CreateRackView(APIView):
    """Create a new rack"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        zone_id = request.data.get("zone_id")

        if not zone_id:
            return Response({"error": "zone_id is required"}, status=400)

        zone = get_object_or_404(Zone, zone_id=zone_id)

        rack = Rack.objects.create(zone=zone)

        return Response({
            "message": "Rack created successfully",
            "rack_id": rack.rack_id,
            "zone_id": zone.zone_id
        }, status=201)


class ListRackView(APIView):
    """List all racks"""

    def get(self, request):
        racks = Rack.objects.select_related('zone').all()
        data = [{
            "rack_id": r.rack_id,
            "zone_id": r.zone.zone_id,
            "zone_type": r.zone.zone_type
        } for r in racks]
        return Response({
            "count": len(data),
            "data": data
        })


class GetRackView(APIView):
    """Get rack details"""

    def get(self, request, rack_id):
        rack = get_object_or_404(Rack.objects.select_related('zone'), rack_id=rack_id)
        return Response({
            "rack_id": rack.rack_id,
            "zone_id": rack.zone.zone_id,
            "zone_type": rack.zone.zone_type
        })


class UpdateRackView(APIView):
    """Update rack details"""

    def put(self, request, rack_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        rack = get_object_or_404(Rack, rack_id=rack_id)

        zone_id = request.data.get("zone_id")
        if zone_id:
            rack.zone = get_object_or_404(Zone, zone_id=zone_id)

        rack.save()

        return Response({
            "message": "Rack updated successfully",
            "rack_id": rack.rack_id,
            "zone_id": rack.zone.zone_id
        })


class DeleteRackView(APIView):
    """Delete a rack"""

    def delete(self, request, rack_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        rack = get_object_or_404(Rack, rack_id=rack_id)

        # Check if rack has shelves
        if Shelf.objects.filter(rack=rack).exists():
            return Response({
                "error": "Cannot delete rack with existing shelves. Remove shelves first."
            }, status=400)

        rack.delete()

        return Response({"message": "Rack deleted successfully"})


# ═══════════════════════════════════════════════════════════
# SHELF VIEWS
# ═══════════════════════════════════════════════════════════

class CreateShelfView(APIView):
    """Create a new shelf"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        rack_id = request.data.get("rack_id")

        if not rack_id:
            return Response({"error": "rack_id is required"}, status=400)

        rack = get_object_or_404(Rack, rack_id=rack_id)

        shelf = Shelf.objects.create(rack=rack)

        return Response({
            "message": "Shelf created successfully",
            "shelf_id": shelf.shelf_id,
            "rack_id": rack.rack_id
        }, status=201)


class ListShelfView(APIView):
    """List all shelves"""

    def get(self, request):
        shelves = Shelf.objects.select_related('rack__zone').all()
        data = [{
            "shelf_id": s.shelf_id,
            "rack_id": s.rack.rack_id,
            "zone_id": s.rack.zone.zone_id,
            "zone_type": s.rack.zone.zone_type
        } for s in shelves]
        return Response({
            "count": len(data),
            "data": data
        })


class GetShelfView(APIView):
    """Get shelf details"""

    def get(self, request, shelf_id):
        shelf = get_object_or_404(
            Shelf.objects.select_related('rack__zone'),
            shelf_id=shelf_id
        )
        return Response({
            "shelf_id": shelf.shelf_id,
            "rack_id": shelf.rack.rack_id,
            "zone_id": shelf.rack.zone.zone_id,
            "zone_type": shelf.rack.zone.zone_type
        })


class UpdateShelfView(APIView):
    """Update shelf details"""

    def put(self, request, shelf_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        shelf = get_object_or_404(Shelf, shelf_id=shelf_id)

        rack_id = request.data.get("rack_id")
        if rack_id:
            shelf.rack = get_object_or_404(Rack, rack_id=rack_id)

        shelf.save()

        return Response({
            "message": "Shelf updated successfully",
            "shelf_id": shelf.shelf_id,
            "rack_id": shelf.rack.rack_id
        })


class DeleteShelfView(APIView):
    """Delete a shelf"""

    def delete(self, request, shelf_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        shelf = get_object_or_404(Shelf, shelf_id=shelf_id)

        # Check if shelf has bins
        if Bin.objects.filter(shelf=shelf).exists():
            return Response({
                "error": "Cannot delete shelf with existing bins. Remove bins first."
            }, status=400)

        shelf.delete()

        return Response({"message": "Shelf deleted successfully"})


# ═══════════════════════════════════════════════════════════
# BIN VIEWS
# ═══════════════════════════════════════════════════════════

class CreateBinView(APIView):
    """Create a new bin"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        serializer = BinSerializer(data=request.data)
        if serializer.is_valid():
            bin_obj = serializer.save()
            return Response({
                "message": "Bin created successfully",
                "data": serializer.data
            }, status=201)
        return Response(serializer.errors, status=400)


class ListBinView(APIView):
    """List all bins"""

    def get(self, request):
        bins = Bin.objects.select_related('shelf__rack__zone').all()
        data = [{
            "bin_id": b.bin_id,
            "shelf_id": b.shelf.shelf_id,
            "rack_id": b.shelf.rack.rack_id,
            "zone_id": b.shelf.rack.zone.zone_id,
            "capacity": b.capacity,
            "current_load": b.current_load,
            "available_capacity": b.capacity - b.current_load,
            "distance_from_dispatch": b.distance_from_dispatch,
            "pick_count": b.pick_count
        } for b in bins]
        return Response({
            "count": len(data),
            "data": data
        })


class GetBinView(APIView):
    """Get bin details"""

    def get(self, request, bin_id):
        bin_obj = get_object_or_404(
            Bin.objects.select_related('shelf__rack__zone'),
            bin_id=bin_id
        )
        return Response({
            "bin_id": bin_obj.bin_id,
            "shelf_id": bin_obj.shelf.shelf_id,
            "rack_id": bin_obj.shelf.rack.rack_id,
            "zone_id": bin_obj.shelf.rack.zone.zone_id,
            "capacity": bin_obj.capacity,
            "current_load": bin_obj.current_load,
            "distance_from_dispatch": bin_obj.distance_from_dispatch,
            "pick_count": bin_obj.pick_count,
            "last_picked_at": bin_obj.last_picked_at
        })


class UpdateBinView(APIView):
    """Update bin details"""

    def put(self, request, bin_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        bin_obj = get_object_or_404(Bin, bin_id=bin_id)
        serializer = BinSerializer(bin_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Bin updated successfully"})
        return Response(serializer.errors, status=400)


class DeleteBinView(APIView):
    """Delete a bin"""

    def delete(self, request, bin_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        bin_obj = get_object_or_404(Bin, bin_id=bin_id)

        # Check if bin has inventory
        if Inventory.objects.filter(bin=bin_obj).exists():
            return Response({
                "error": "Cannot delete bin with existing inventory. Move inventory first."
            }, status=400)

        bin_obj.delete()
        return Response({"message": "Bin deleted successfully"})


class ListAvailableBinsView(APIView):
    """List bins with available capacity"""

    def get(self, request):
        bins = Bin.objects.filter(current_load__lt=models.F('capacity'))
        data = [{
            "bin_id": b.bin_id,
            "available_space": b.capacity - b.current_load,
            "capacity": b.capacity,
            "current_load": b.current_load,
            "distance_from_dispatch": b.distance_from_dispatch
        } for b in bins]
        return Response({
            "count": len(data),
            "data": data
        })


# ═══════════════════════════════════════════════════════════
# INVENTORY VIEWS
# ═══════════════════════════════════════════════════════════

class ListInventoryView(APIView):
    """List all inventory items"""

    def get(self, request):
        inventory = Inventory.objects.select_related(
            'product', 'bin__shelf__rack__zone'
        ).all()
        serializer = InventorySerializer(inventory, many=True)
        return Response({
            "count": inventory.count(),
            "data": serializer.data
        })


class GetInventoryView(APIView):
    """Get inventory details"""

    def get(self, request, inventory_id):
        inventory = get_object_or_404(
            Inventory.objects.select_related('product', 'bin'),
            inventory_id=inventory_id
        )
        serializer = InventorySerializer(inventory)
        return Response(serializer.data)

class UpdateInventoryView(APIView):
    """Update inventory safely (restricted)"""

    def put(self, request, inventory_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        inventory = get_object_or_404(Inventory, inventory_id=inventory_id)

        qty = request.data.get("quantity")

        if qty is not None:
            try:
                qty = int(qty)
                if qty < 0:
                    raise ValueError
            except:
                return Response({"error": "Invalid quantity"}, status=400)

            # capacity check
            if qty > inventory.bin.capacity:
                return Response({"error": "Exceeds bin capacity"}, status=400)

            inventory.quantity = qty
            inventory.save()

        return Response({"message": "Inventory updated"})


class DeleteInventoryView(APIView):
    """Delete inventory record"""

    def delete(self, request, inventory_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        inventory = get_object_or_404(Inventory, inventory_id=inventory_id)
        inventory.delete()
        return Response({"message": "Inventory deleted successfully"})


class StockMovementListView(APIView):
    """List recent stock movements"""

    def get(self, request):
        limit = request.query_params.get("limit", 100)
        try:
            limit = int(limit)
            if limit > 1000:
                limit = 1000
        except ValueError:
            limit = 100

        movements = StockMovement.objects.select_related(
            'product', 'bin'
        ).order_by('-created_at')[:limit]

        data = [{
            "movement_id": m.movement_id,
            "product": m.product.product_name,
            "product_id": m.product.product_id,
            "bin": m.bin.bin_id,
            "movement_type": m.movement_type,
            "quantity": m.quantity,
            "previous_stock": m.previous_stock,
            "new_stock": m.new_stock,
            "created_at": m.created_at
        } for m in movements]

        return Response({
            "count": len(data),
            "data": data
        })


class StockMovementByProductView(APIView):
    """List stock movements for a specific product"""

    def get(self, request, product_id):
        movements = StockMovement.objects.filter(
            product_id=product_id
        ).select_related('bin').order_by('-created_at')

        data = [{
            "movement_id": m.movement_id,
            "bin": m.bin.bin_id,
            "movement_type": m.movement_type,
            "quantity": m.quantity,
            "previous_stock": m.previous_stock,
            "new_stock": m.new_stock,
            "created_at": m.created_at
        } for m in movements]

        return Response({
            "count": len(data),
            "product_id": product_id,
            "data": data
        })

class CreateInventoryView(APIView):
    """Create inventory safely"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        product_id = request.data.get("product")
        bin_id = request.data.get("bin")

        if not product_id or not bin_id:
            return Response({"error": "product and bin required"}, status=400)

        product = get_object_or_404(Product, product_id=product_id)
        bin_obj = get_object_or_404(Bin, bin_id=bin_id)

        if Inventory.objects.filter(product=product, bin=bin_obj).exists():
            return Response({"error": "Inventory already exists"}, status=400)

        inventory = Inventory.objects.create(
            product=product,
            bin=bin_obj,
            quantity=request.data.get("quantity", 0)
        )

        return Response({
            "message": "Inventory created",
            "inventory_id": inventory.inventory_id
        }, status=201)

class AddStockByProductView(APIView):
    """Add stock using bin allocation (multi-bin supported)"""

    def post(self, request, product_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        try:
            qty = int(request.data.get("quantity"))
            if qty <= 0:
                raise ValueError
        except:
            return Response({"error": "Valid quantity required"}, status=400)

        product = get_object_or_404(Product, product_id=product_id)

        remaining = qty
        updates = []

        with transaction.atomic():
            while remaining > 0:
                bin_obj = assign_bin(product, remaining)

                if not bin_obj:
                    return Response({"error": "No bin available"}, status=400)

                available = bin_obj.capacity - bin_obj.current_load
                put_qty = min(remaining, available)

                inventory, _ = Inventory.objects.get_or_create(
                    product=product,
                    bin=bin_obj,
                    defaults={"quantity": 0}
                )

                prev = inventory.quantity
                inventory.quantity += put_qty
                inventory.save()

                # update bin
                bin_obj.current_load += put_qty
                bin_obj.save()

                StockMovement.objects.create(
                    product=product,
                    bin=bin_obj,
                    movement_type="STOCK_ADDITION",
                    quantity=put_qty,
                    previous_stock=prev,
                    new_stock=inventory.quantity
                )

                updates.append({
                    "bin": bin_obj.bin_id,
                    "added": put_qty
                })

                remaining -= put_qty

        check_reorder(product)

        return Response({
            "message": "Stock added",
            "total_added": qty,
            "distribution": updates
        })
class RemoveStockByProductView(APIView):
    """Remove stock using optimized picking"""

    def post(self, request, product_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        try:
            qty = int(request.data.get("quantity"))
            if qty <= 0:
                raise ValueError
        except:
            return Response({"error": "Valid quantity required"}, status=400)

        product = get_object_or_404(Product, product_id=product_id)

        inventories = Inventory.objects.select_related("bin").filter(
            product=product,
            quantity__gt=0
        )

        if not inventories.exists():
            return Response({"error": "No stock available"}, status=404)

        total = sum(i.quantity for i in inventories)
        if qty > total:
            return Response({"error": "Insufficient stock"}, status=400)

        # Optimize picking
        inventories = sorted(
            inventories,
            key=lambda x: (
                x.bin.distance_from_dispatch,
                x.bin.pick_count
            )
        )

        remaining = qty
        result = []

        with transaction.atomic():
            for inv in inventories:
                if remaining <= 0:
                    break

                pick = min(inv.quantity, remaining)
                prev = inv.quantity

                inv.quantity -= pick
                inv.save()

                bin_obj = inv.bin
                bin_obj.current_load -= pick
                bin_obj.pick_count += 1
                bin_obj.last_picked_at = timezone.now()
                bin_obj.save()

                StockMovement.objects.create(
                    product=product,
                    bin=bin_obj,
                    movement_type="STOCK_REMOVAL",
                    quantity=pick,
                    previous_stock=prev,
                    new_stock=inv.quantity
                )

                result.append({
                    "bin": bin_obj.bin_id,
                    "removed": pick
                })

                remaining -= pick

        check_reorder(product)

        return Response({
            "message": "Stock removed",
            "total_removed": qty,
            "distribution": result
        })


class ProductStockView(APIView):
    """Get total stock for a product"""

    def get(self, request, product_id):
        try:
            product = Product.objects.get(product_id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        total = Inventory.objects.filter(
            product_id=product_id
        ).aggregate(total=Sum("quantity"))["total"] or 0

        # Get bin-level breakdown
        bin_breakdown = Inventory.objects.filter(
            product_id=product_id,
            quantity__gt=0
        ).select_related('bin').values(
            'bin__bin_id', 'bin__distance_from_dispatch'
        ).annotate(quantity=Sum('quantity'))

        return Response({
            "product_id": product_id,
            "product_name": product.product_name,
            "total_stock": total,
            "bin_breakdown": [
                {
                    "bin_id": item["bin__bin_id"],
                    "quantity": item["quantity"],
                    "distance_from_dispatch": item["bin__distance_from_dispatch"]
                }
                for item in bin_breakdown
            ]
        })


# ═══════════════════════════════════════════════════════════
# PURCHASE REQUEST
# ═══════════════════════════════════════════════════════════

class PurchaseRequestListView(APIView):
    """List all purchase requests"""

    def get(self, request):
        prs = PurchaseRequest.objects.all().order_by('-created_at')
        serializer = PurchaseRequestSerializer(prs, many=True)
        return Response({
            "count": prs.count(),
            "data": serializer.data
        })


class ManagerApprovePR(APIView):
    """
    Manager approves a Purchase Request.
    - If total_amount > threshold: moves to Finance Pending
    - If total_amount <= threshold: directly approves and creates PO
    """

    THRESHOLD = 5000

    def post(self, request, pr_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        # TODO: Add manager permission check
        # if not request.user.has_perm('inventory.can_approve_pr'):
        #     return Response({"error": "Insufficient permissions"}, status=403)

        try:
            pr = PurchaseRequest.objects.get(pr_id=pr_id)
        except PurchaseRequest.DoesNotExist:
            return Response({"error": "Purchase Request not found"}, status=404)

        # Validate PR status
        valid_statuses = ["PENDING", "MANAGER_APPROVED", "FINANCE_PENDING"]
        if pr.status not in valid_statuses:
            return Response({
                "error": f"Cannot approve PR with status '{pr.status}'. "
                         f"Valid statuses: {', '.join(valid_statuses)}"
            }, status=400)

        if pr.status == "APPROVED":
            return Response({"error": "PR already approved"}, status=400)

        # Process based on amount
        if pr.total_amount > self.THRESHOLD:
            pr.status = "FINANCE_PENDING"
            pr.save()
            return Response({
                "message": "PR requires Finance Director approval",
                "pr_id": pr.pr_id,
                "status": pr.status,
                "total_amount": pr.total_amount,
                "threshold": self.THRESHOLD
            }, status=200)
        else:
            pr.status = "APPROVED"
            pr.approved_at = timezone.now()
            pr.save()

            try:
                with transaction.atomic():
                    po = PurchaseOrder.objects.create(
                        pr=pr,
                        vendor=pr.vendor,
                        order_quantity=pr.requested_quantity,
                        total_amount=pr.total_amount,
                        created_by=request.user
                    )

                    # Send email notification
                    try:
                        send_po_email(po)
                    except Exception as email_error:
                        # Log but don't fail the approval
                        print(f"Email sending failed: {email_error}")

                    return Response({
                        "message": "PR approved and PO created successfully",
                        "pr_id": pr.pr_id,
                        "po_id": po.po_id,
                        "status": pr.status
                    }, status=200)

            except Exception as e:
                # Revert PR status
                pr.status = "PENDING"
                pr.save()
                return Response({
                    "error": f"Failed to create Purchase Order: {str(e)}"
                }, status=500)


class FinanceApprovePR(APIView):
    """Finance approves a purchase request"""

    def post(self, request, pr_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        # TODO: Add finance permission check

        try:
            pr = PurchaseRequest.objects.get(pr_id=pr_id)
        except PurchaseRequest.DoesNotExist:
            return Response({"error": "Purchase Request not found"}, status=404)

        if pr.status != "FINANCE_PENDING":
            return Response({
                "error": f"Cannot approve PR with status '{pr.status}'. "
                         f"Expected status: FINANCE_PENDING"
            }, status=400)

        with transaction.atomic():
            pr.status = "APPROVED"
            pr.approved_at = timezone.now()
            pr.save()

            po = PurchaseOrder.objects.create(
                pr=pr,
                vendor=pr.vendor,
                order_quantity=pr.requested_quantity,
                total_amount=pr.total_amount,
                created_by=request.user
            )

            try:
                send_po_email(po)
            except Exception as email_error:
                print(f"Email sending failed: {email_error}")

        return Response({
            "message": "Finance approved. PO created",
            "pr_id": pr.pr_id,
            "po_id": po.po_id
        })


# ═══════════════════════════════════════════════════════════
# PURCHASE ORDER
# ═══════════════════════════════════════════════════════════

class PurchaseOrderListView(APIView):
    """List all purchase orders"""

    def get(self, request):
        pos = PurchaseOrder.objects.all().order_by("-created_at")
        serializer = PurchaseOrderSerializer(pos, many=True)
        return Response({
            "count": pos.count(),
            "data": serializer.data
        })


# ═══════════════════════════════════════════════════════════
# ASN (Advanced Shipping Notice)
# ═══════════════════════════════════════════════════════════

class ASNCreateView(APIView):
    """Create ASN"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        serializer = ASNSerializer(data=request.data)

        if serializer.is_valid():
            asn = serializer.save(created_by=request.user)
            return Response({
                "message": "ASN created successfully",
                "asn_id": asn.asn_id,
                "data": serializer.data
            }, status=201)

        return Response(serializer.errors, status=400)


class ASNListView(APIView):
    """List all ASNs"""

    def get(self, request):
        asns = ASN.objects.all().order_by("-created_at")
        serializer = ASNSerializer(asns, many=True)
        return Response({
            "count": asns.count(),
            "data": serializer.data
        })


class ASNDetailView(APIView):
    """Get ASN details"""

    def get(self, request, pk):
        asn = get_object_or_404(ASN, asn_id=pk)
        serializer = ASNSerializer(asn)
        return Response(serializer.data)


class CreateASNItemView(APIView):
    """Create ASN items"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        serializer = ASNItemSerializer(data=request.data, many=True)

        if serializer.is_valid():
            items = serializer.save()
            return Response({
                "message": "ASN Items created successfully",
                "count": len(items),
                "data": serializer.data
            }, status=201)

        return Response(serializer.errors, status=400)


class ASNItemListView(APIView):
    """List all ASN items"""

    def get(self, request):
        items = ASNItem.objects.all().order_by("-created_at")
        serializer = ASNItemSerializer(items, many=True)
        return Response({
            "count": items.count(),
            "data": serializer.data
        })


class ASNItemDetailView(APIView):
    """Get ASN item details"""

    def get(self, request, pk):
        item = get_object_or_404(ASNItem, asn_item_id=pk)
        serializer = ASNItemSerializer(item)
        return Response(serializer.data)


# ═══════════════════════════════════════════════════════════
# GRN (Goods Receipt Note) - SUPERVISOR
# ═══════════════════════════════════════════════════════════

class SupervisorCreateGRN(APIView):
    """Supervisor creates the GRN header"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        # TODO: Add supervisor permission check

        serializer = GRNCreateSerializer(data=request.data)
        if serializer.is_valid():
            grn = serializer.save(
                received_by=request.user,
                status="QC_PENDING"
            )
            return Response({
                "message": "GRN created successfully",
                "grn_id": grn.grn_id,
                "status": grn.status
            }, status=201)

        return Response(serializer.errors, status=400)


class SupervisorAddGRNItems(APIView):
    """Supervisor adds line items to GRN"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        # TODO: Add supervisor permission check

        serializer = GRNItemCreateSerializer(data=request.data, many=True)
        if serializer.is_valid():
            items = serializer.save()
            return Response({
                "message": f"{len(items)} GRN items added successfully",
                "data": serializer.data
            }, status=201)

        return Response(serializer.errors, status=400)


class SupervisorGRNListView(APIView):
    """Returns GRNs created by the logged-in supervisor"""

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        grns = GRN.objects.filter(received_by=request.user)

        status_filter = request.query_params.get("status")
        if status_filter:
            grns = grns.filter(status=status_filter)

        grns = grns.order_by("-created_at")

        return Response({
            "count": grns.count(),
            "data": GRNReadSerializer(grns, many=True).data
        })


# ═══════════════════════════════════════════════════════════
# GRN - QC (Quality Control)
# ═══════════════════════════════════════════════════════════

class QCUpdateGRNItem(APIView):
    """QC updates item with accepted/rejected quantities"""

    def put(self, request, pk):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        # TODO: Add QC permission check

        try:
            item = GRNItem.objects.get(pk=pk)
        except GRNItem.DoesNotExist:
            return Response({"error": "GRN item not found"}, status=404)

        if item.qc_status == "COMPLETED":
            return Response({"error": "Item already QC completed"}, status=400)

        # Validate that accepted + rejected <= received
        accepted = request.data.get("accepted_quantity")
        rejected = request.data.get("rejected_quantity")

        if accepted is not None and rejected is not None:
            try:
                total = accepted + rejected
                if total > item.received_quantity:
                    return Response({
                        "error": f"Accepted + rejected ({total}) exceeds received quantity ({item.received_quantity})"
                    }, status=400)
            except TypeError:
                return Response({"error": "Invalid quantity values"}, status=400)

        serializer = GRNItemQCSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(qc_status="COMPLETED")
            return Response({
                "message": "QC updated successfully",
                "data": serializer.data
            })

        return Response(serializer.errors, status=400)


class QCApproveGRN(APIView):
    """
    QC finalizes the GRN.
    - Ensures all items are QC completed
    - Adds accepted quantity to inventory
    - Tracks stock movement
    - Updates GRN status
    """

    def post(self, request, grn_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        # TODO: Add QC permission check

        try:
            grn = GRN.objects.get(grn_id=grn_id)
        except GRN.DoesNotExist:
            return Response({"error": "GRN not found"}, status=404)

        if grn.status != "QC_PENDING":
            return Response({
                "error": f"GRN status is '{grn.status}', expected 'QC_PENDING'"
            }, status=400)

        items = GRNItem.objects.filter(grn=grn)

        if not items.exists():
            return Response({"error": "No GRN items found"}, status=400)

        # Ensure all items are QC completed
        incomplete = items.filter(qc_status="PENDING")
        if incomplete.exists():
            return Response({
                "error": f"{incomplete.count()} item(s) not yet QC'd",
                "pending_items": list(incomplete.values_list("grn_item_id", flat=True))
            }, status=400)

        total_accepted = 0
        total_rejected = 0
        inventory_updates = []

        with transaction.atomic():
            for item in items:
                total_accepted += item.accepted_quantity
                total_rejected += item.rejected_quantity

                remaining_qty = item.accepted_quantity

                while remaining_qty > 0:
                    bin_obj = assign_bin(item.product, remaining_qty)

                    if bin_obj is None:
                        raise Exception(f"No suitable bin found for product {item.product.product_name}")

                    available_space = bin_obj.capacity - bin_obj.current_load

                    if available_space <= 0:
                        raise Exception(f"Bin {bin_obj.bin_id} is full")

                    put_qty = min(remaining_qty, available_space)

                    inventory, created = Inventory.objects.get_or_create(
                        product=item.product,
                        bin=bin_obj,
                        defaults={"quantity": 0}
                    )

                    prev_qty = inventory.quantity

                    inventory.quantity += put_qty
                    inventory.save()

                    # Update bin load
                    bin_obj.current_load += put_qty
                    bin_obj.save()

                    # Track stock movement
                    StockMovement.objects.create(
                        product=item.product,
                        bin=bin_obj,
                        movement_type="INBOUND",
                        quantity=put_qty,
                        previous_stock=prev_qty,
                        new_stock=inventory.quantity,
                        reference=f"GRN-{grn.grn_id}"
                    )

                    inventory_updates.append({
                        "product": item.product.product_name,
                        "bin": bin_obj.bin_id,
                        "quantity": put_qty
                    })

                    remaining_qty -= put_qty

            # Mark GRN as completed
            grn.status = "COMPLETED"
            grn.qc_verified_by = request.user
            grn.completed_at = timezone.now()
            grn.save()

        return Response({
            "message": "GRN approved and inventory updated",
            "grn_id": grn_id,
            "total_accepted": total_accepted,
            "total_rejected": total_rejected,
            "inventory_updates": inventory_updates
        }, status=200)


class GRNQCPendingListView(APIView):
    """Returns all GRNs waiting for QC"""

    def get(self, request):
        grns = GRN.objects.filter(status="QC_PENDING").order_by("-created_at")
        serializer = GRNReadSerializer(grns, many=True)
        return Response({
            "count": grns.count(),
            "data": serializer.data
        })


# ═══════════════════════════════════════════════════════════
# GRN - GENERAL READ
# ═══════════════════════════════════════════════════════════

class GRNCreateView(APIView):
    """Generic GRN create for direct creation"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        serializer = GRNCreateSerializer(data=request.data)
        if serializer.is_valid():
            grn = serializer.save()
            return Response({
                "message": "GRN created",
                "grn_id": grn.grn_id,
                "data": serializer.data
            }, status=201)
        return Response(serializer.errors, status=400)


class GRNListView(APIView):
    """List all GRNs"""

    def get(self, request):
        grns = GRN.objects.all().order_by("-created_at")
        serializer = GRNReadSerializer(grns, many=True)
        return Response({
            "count": grns.count(),
            "data": serializer.data
        })


class GRNDetailView(APIView):
    """Get GRN details"""

    def get(self, request, pk):
        grn = get_object_or_404(GRN, grn_id=pk)
        serializer = GRNReadSerializer(grn)
        return Response(serializer.data)


class GRNItemsByGRNView(APIView):
    """Get all items for a specific GRN"""

    def get(self, request, grn_id):
        grn = get_object_or_404(GRN, grn_id=grn_id)
        items = GRNItem.objects.filter(grn=grn)
        serializer = GRNItemReadSerializer(items, many=True)
        return Response({
            "grn_id": grn_id,
            "count": items.count(),
            "data": serializer.data
        })


class GRNSummaryView(APIView):
    """Get summary for a specific GRN"""

    def get(self, request, grn_id):
        grn = get_object_or_404(GRN, grn_id=grn_id)

        result = GRNItem.objects.filter(grn=grn).aggregate(
            received=Sum("received_quantity"),
            accepted=Sum("accepted_quantity"),
            rejected=Sum("rejected_quantity")
        )

        return Response({
            "grn_id": grn_id,
            "po_id": grn.po.po_id if grn.po else None,
            "asn_id": grn.asn.asn_id if grn.asn else None,
            "status": grn.status,
            "received_by": grn.received_by.username if grn.received_by else None,
            "qc_verified_by": grn.qc_verified_by.username if grn.qc_verified_by else None,
            "created_at": grn.created_at,
            "completed_at": grn.completed_at,
            **{k: v or 0 for k, v in result.items()}
        })


# ═══════════════════════════════════════════════════════════
# GRN ITEMS - GENERAL
# ═══════════════════════════════════════════════════════════

class GRNItemCreateView(APIView):
    """Generic GRN item create"""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        serializer = GRNItemCreateSerializer(data=request.data, many=True)
        if serializer.is_valid():
            items = serializer.save()
            return Response({
                "message": f"{len(items)} GRN items created",
                "data": serializer.data
            }, status=201)
        return Response(serializer.errors, status=400)


class GRNItemListView(APIView):
    """List all GRN items"""

    def get(self, request):
        items = GRNItem.objects.all().order_by("-created_at")
        serializer = GRNItemReadSerializer(items, many=True)
        return Response({
            "count": items.count(),
            "data": serializer.data
        })


class GRNItemDetailView(APIView):
    """Get GRN item details"""

    def get(self, request, pk):
        item = get_object_or_404(GRNItem, pk=pk)
        serializer = GRNItemReadSerializer(item)
        return Response(serializer.data)


# ═══════════════════════════════════════════════════════════
# OPTIMIZED OUTBOUND
# ═══════════════════════════════════════════════════════════

class OptimizedOutboundView(APIView):
    """
    Handles outbound picking with:
    - Distance-based picking (closest to dispatch first)
    - Balanced bin usage (prefer bins with fewer picks)
    - Multi-bin allocation
    - Complete stock movement tracking
    """

    def post(self, request, product_id):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        try:
            qty = int(request.data.get("quantity"))
            if qty <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": "Quantity must be a positive integer"}, status=400)

        try:
            product = Product.objects.get(product_id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        # Get all inventory with positive quantity
        inventories = Inventory.objects.select_related("bin").filter(
            product=product,
            quantity__gt=0
        ).order_by("bin__distance_from_dispatch")

        if not inventories.exists():
            return Response({"error": "No stock available for this product"}, status=404)

        total_available = sum(inv.quantity for inv in inventories)

        if qty > total_available:
            return Response({
                "error": f"Insufficient stock. Requested: {qty}, Available: {total_available}"
            }, status=400)

        # Sort for optimal picking: distance first, then pick count (balance usage)
        inventories = sorted(
            inventories,
            key=lambda x: (
                x.bin.distance_from_dispatch,
                x.bin.pick_count  # Prefer bins with fewer picks for balancing
            )
        )

        remaining = qty
        picked_bins = []

        with transaction.atomic():
            for inv in inventories:
                if remaining <= 0:
                    break

                pick_qty = min(inv.quantity, remaining)

                prev_qty = inv.quantity

                # Update inventory
                inv.quantity -= pick_qty
                inv.save()

                # Update bin metrics
                bin_obj = inv.bin
                bin_obj.current_load -= pick_qty
                bin_obj.pick_count += 1
                bin_obj.last_picked_at = timezone.now()
                bin_obj.save()

                # Track movement
                StockMovement.objects.create(
                    product=product,
                    bin=bin_obj,
                    movement_type="OUTBOUND",
                    quantity=pick_qty,
                    previous_stock=prev_qty,
                    new_stock=inv.quantity,
                    reference=f"OUTBOUND-{request.user.id}"
                )

                picked_bins.append({
                    "bin_id": bin_obj.bin_id,
                    "location": f"Rack {bin_obj.shelf.rack.rack_id}, Shelf {bin_obj.shelf.shelf_id}",
                    "distance_from_dispatch": bin_obj.distance_from_dispatch,
                    "picked_quantity": pick_qty,
                    "remaining_in_bin": inv.quantity
                })

                remaining -= pick_qty

        # Check if we need to reorder
        check_reorder(product)

        return Response({
            "message": "Outbound picking completed",
            "product_id": product_id,
            "product_name": product.product_name,
            "requested_quantity": qty,
            "picked_quantity": qty - remaining,
            "picked_from_bins": picked_bins,
            "timestamp": timezone.now()
        }, status=200)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def send_po_email(po):
    """Send purchase order email to vendor"""
    subject = f"Purchase Order {po.po_id} - {po.pr.product.product_name}"
    message = f"""
Dear {po.vendor.name},

A purchase order has been created for your reference:

Purchase Order Number: {po.po_id}
Product: {po.pr.product.product_name}
Quantity: {po.order_quantity}
Total Amount: {po.total_amount}
Created Date: {po.created_at}

Please arrange the shipment accordingly.

Thank you,
Warehouse Management System
"""
    send_mail(
        subject,
        message,
        "warehouse@company.com",
        [po.vendor.email],
        fail_silently=False
    )