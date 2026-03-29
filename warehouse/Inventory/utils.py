from django.db.models import Sum, F, Q
from django.db import transaction
from django.utils import timezone
import logging
from .models import Inventory, PurchaseRequest, Bin, StockMovement
from products.models import Product

logger = logging.getLogger(__name__)


# ================= REORDER MANAGEMENT =================

def check_reorder(product):
    """
    Check if product needs reordering and create purchase request if needed.
    Uses transaction to prevent duplicate requests.
    """
    # Validate product
    if not product:
        logger.error("Cannot check reorder for None product")
        return False
    
    # Validate reorder level
    if product.re_order <= 0:
        logger.warning(f"Product {product.product_id} has invalid reorder level: {product.re_order}")
        return False
    
    # Check vendor exists
    if not product.vendor:
        logger.warning(f"Product {product.product_id} has no vendor assigned")
        return False
    
    # Get total stock
    total_stock = Inventory.objects.filter(
        product=product
    ).aggregate(total=Sum("quantity"))["total"] or 0
    
    # Check if below reorder level
    if total_stock > product.re_order:
        return False
    
    logger.info(f"Product {product.product_id} stock ({total_stock}) below reorder level ({product.re_order})")
    
    # Use transaction to prevent race conditions
    with transaction.atomic():
        # Double-check no pending PR exists
        existing_pr = PurchaseRequest.objects.select_for_update().filter(
            product=product,
            status__in=["PENDING", "MANAGER_APPROVED", "FINANCE_PENDING"]
        ).exists()
        
        if existing_pr:
            logger.info(f"Product {product.product_id} already has pending purchase request")
            return False
        
        # Calculate reorder quantity
        reorder_qty = calculate_reorder_quantity(product, total_stock)
        
        # Create purchase request
        try:
            pr = PurchaseRequest.objects.create(
                product=product,
                vendor=product.vendor,
                requested_quantity=reorder_qty,
                total_amount=reorder_qty * product.unit_price,
            )
            logger.info(f"Created purchase request {pr.pr_id} for product {product.product_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create purchase request: {str(e)}")
            return False


def calculate_reorder_quantity(product, current_stock):
    """
    Calculate optimal reorder quantity based on:
    - Reorder level
    - Lead time
    - Demand history (if available)
    - Safety stock
    """
    # Basic reorder quantity (2x reorder level)
    base_qty = product.re_order * 2
    
    # Add safety stock (20% of base quantity)
    safety_stock = int(base_qty * 0.2)
    
    # Consider ABC classification
    if product.ABC == 'A':
        # High value items - order less frequently
        multiplier = 1.5
    elif product.ABC == 'B':
        multiplier = 2
    else:
        # C items - order in bulk
        multiplier = 3
    
    reorder_qty = int((base_qty + safety_stock) * multiplier)
    
    # Ensure minimum order quantity
    min_order = getattr(product, 'min_order_quantity', 10)
    reorder_qty = max(reorder_qty, min_order)
    
    return reorder_qty


# ================= BIN ASSIGNMENT =================

def assign_bin(product, quantity):
    """
    Assign optimal bin for product storage.
    Returns the best available bin or raises exception.
    """
    if quantity <= 0:
        raise ValueError(f"Invalid quantity: {quantity}")
    
    # Get bins with available capacity
    bins = Bin.objects.filter(
        capacity__gt=F("current_load")
    ).select_related('shelf__rack__zone')
    
    if not bins.exists():
        raise Exception("No bins available for storage. Please create more bins or free up space.")
    
    # Apply ABC-based bin selection logic
    if product.ABC == "A":
        # High-value items: nearest to dispatch, with available capacity
        bins = bins.filter(
            current_load__lte=F("capacity") * 0.8  # Prefer bins with at least 20% space
        ).order_by("distance_from_dispatch", "current_load")
        
    elif product.ABC == "B":
        # Medium-value items: balance distance and utilization
        bins = bins.order_by(
            "distance_from_dispatch",
            F("capacity") - F("current_load")  # Prefer bins with more space
        )
        
    else:  # ABC == "C"
        # Low-value items: can go farther, prefer bins with more space
        bins = bins.order_by(
            "-distance_from_dispatch",  # Farthest first
            "-current_load"  # Prefer bins with more space
        )
    
    # Get the best bin
    best_bin = bins.first()
    
    if not best_bin:
        raise Exception("No suitable bin found for product placement")
    
    # Check if bin can accommodate the quantity
    available_space = best_bin.capacity - best_bin.current_load
    if available_space < quantity:
        logger.warning(f"Bin {best_bin.bin_id} has only {available_space} space, need {quantity}")
    
    logger.info(f"Assigned bin {best_bin.bin_id} for product {product.product_id}")
    return best_bin


# ================= PUTAWAY PLAN =================

def generate_putaway_plan(product, quantity):
    """
    Generate a putaway plan for received goods.
    Returns a list of bins with suggested quantities.
    """
    if quantity <= 0:
        raise ValueError(f"Invalid quantity: {quantity}")
    
    remaining_qty = quantity
    putaway_plan = []
    
    # Get available bins sorted by ABC logic
    bins = get_available_bins_for_putaway(product)
    
    for bin_obj in bins:
        if remaining_qty <= 0:
            break
        
        available_space = bin_obj.capacity - bin_obj.current_load
        
        if available_space <= 0:
            continue
        
        # Calculate quantity to put in this bin
        put_qty = min(remaining_qty, available_space)
        
        # Build location string
        location = f"{bin_obj.shelf.rack.zone.zone_type}-{bin_obj.shelf.rack.rack_id}-{bin_obj.shelf.shelf_id}-{bin_obj.bin_id}"
        
        putaway_plan.append({
            "bin_id": bin_obj.bin_id,
            "location": location,
            "quantity": put_qty,
            "available_space": available_space
        })
        
        remaining_qty -= put_qty
    
    if remaining_qty > 0:
        logger.warning(f"Only {quantity - remaining_qty} of {quantity} units could be planned. {remaining_qty} units need additional space.")
    
    return putaway_plan


def get_available_bins_for_putaway(product):
    """
    Get available bins sorted according to ABC classification.
    """
    # Base query for bins with available capacity
    bins = Bin.objects.filter(
        capacity__gt=F("current_load")
    ).select_related('shelf__rack__zone')
    
    if not bins.exists():
        return []
    
    # Sort based on ABC classification
    if product.ABC == "A":
        # High-value items: nearest to dispatch
        bins = bins.order_by("distance_from_dispatch", "-current_load")
    elif product.ABC == "B":
        # Medium-value items: balance distance and capacity
        bins = bins.order_by(
            "distance_from_dispatch",
            F("capacity") - F("current_load")
        )
    else:  # C items
        # Low-value items: farthest from dispatch, most space
        bins = bins.order_by(
            "-distance_from_dispatch",
            F("capacity") - F("current_load")
        )
    
    return bins


def confirm_putaway(product, plan, user):
    """
    Execute the putaway plan and update inventory.
    """
    if not plan:
        raise ValueError("Putaway plan is empty")
    
    with transaction.atomic():
        for item in plan:
            bin_id = item.get("bin_id")
            quantity = item.get("quantity")
            
            if not bin_id or not quantity:
                raise ValueError(f"Invalid plan item: {item}")
            
            try:
                bin_obj = Bin.objects.get(bin_id=bin_id)
            except Bin.DoesNotExist:
                raise ValueError(f"Bin {bin_id} not found")
            
            # Get or create inventory record
            inventory, created = Inventory.objects.get_or_create(
                product=product,
                bin=bin_obj,
                defaults={"quantity": 0}
            )
            
            previous_qty = inventory.quantity
            
            # Update inventory
            inventory.quantity += quantity
            inventory.save()
            
            # Update bin load
            bin_obj.current_load += quantity
            bin_obj.save()
            
            # Record stock movement
            StockMovement.objects.create(
                product=product,
                bin=bin_obj,
                movement_type="INBOUND",
                quantity=quantity,
                previous_stock=previous_qty,
                new_stock=inventory.quantity,
                reference=f"PUTAWAY_{product.product_id}",
                created_by=user
            )
            
            logger.info(f"Putaway confirmed: {quantity} units of {product.product_id} to bin {bin_id}")
    
    return True


# ================= PICK PLAN =================

def generate_pick_plan(product, quantity):
    """
    Generate picking plan for outbound orders.
    Returns a list of bins with suggested pick quantities.
    """
    if quantity <= 0:
        raise ValueError(f"Invalid quantity: {quantity}")
    
    remaining_qty = quantity
    pick_plan = []
    
    # Get inventory with positive quantity, sorted by distance
    inventories = Inventory.objects.filter(
        product=product,
        quantity__gt=0
    ).select_related('bin').order_by('bin__distance_from_dispatch')
    
    for inventory in inventories:
        if remaining_qty <= 0:
            break
        
        # Quantity available in this bin
        available_qty = inventory.quantity
        
        if available_qty <= 0:
            continue
        
        # Calculate quantity to pick from this bin
        pick_qty = min(remaining_qty, available_qty)
        
        # Build location string
        location = f"{inventory.bin.shelf.rack.zone.zone_type}-{inventory.bin.shelf.rack.rack_id}-{inventory.bin.shelf.shelf_id}-{inventory.bin.bin_id}"
        
        pick_plan.append({
            "bin_id": inventory.bin.bin_id,
            "location": location,
            "quantity": pick_qty,
            "available_quantity": available_qty,
            "distance": inventory.bin.distance_from_dispatch
        })
        
        remaining_qty -= pick_qty
    
    if remaining_qty > 0:
        raise Exception(f"Insufficient stock. Requested {quantity}, only {quantity - remaining_qty} available")
    
    return pick_plan


def confirm_pick(plan, user):
    """
    Execute the picking plan and update inventory.
    """
    if not plan:
        raise ValueError("Pick plan is empty")
    
    with transaction.atomic():
        for item in plan:
            bin_id = item.get("bin_id")
            quantity = item.get("quantity")
            product_id = item.get("product_id")  # May be passed
            
            if not bin_id or not quantity:
                raise ValueError(f"Invalid plan item: {item}")
            
            try:
                bin_obj = Bin.objects.get(bin_id=bin_id)
            except Bin.DoesNotExist:
                raise ValueError(f"Bin {bin_id} not found")
            
            # Find inventory in this bin
            if product_id:
                inventory = Inventory.objects.filter(
                    product_id=product_id,
                    bin=bin_obj
                ).first()
            else:
                # Get any inventory from this bin (should be filtered by product earlier)
                inventory = Inventory.objects.filter(bin=bin_obj).first()
            
            if not inventory:
                raise ValueError(f"No inventory found in bin {bin_id}")
            
            if inventory.quantity < quantity:
                raise ValueError(f"Insufficient stock in bin {bin_id}. Available: {inventory.quantity}, Requested: {quantity}")
            
            previous_qty = inventory.quantity
            
            # Update inventory
            inventory.quantity -= quantity
            inventory.save()
            
            # Update bin metrics
            bin_obj.current_load -= quantity
            bin_obj.pick_count += 1
            bin_obj.last_picked_at = timezone.now()
            bin_obj.save()
            
            # Record stock movement
            StockMovement.objects.create(
                product=inventory.product,
                bin=bin_obj,
                movement_type="OUTBOUND",
                quantity=quantity,
                previous_stock=previous_qty,
                new_stock=inventory.quantity,
                reference=f"PICK_{inventory.product.product_id}",
                created_by=user
            )
            
            logger.info(f"Pick confirmed: {quantity} units from bin {bin_id}")
    
    return True


# ================= UTILITY FUNCTIONS =================

def get_bin_utilization_report():
    """Generate bin utilization report"""
    bins = Bin.objects.select_related('shelf__rack__zone').all()
    
    report = []
    for bin_obj in bins:
        utilization = (bin_obj.current_load / bin_obj.capacity * 100) if bin_obj.capacity > 0 else 0
        
        report.append({
            'bin_id': bin_obj.bin_id,
            'zone': bin_obj.shelf.rack.zone.zone_type,
            'capacity': bin_obj.capacity,
            'current_load': bin_obj.current_load,
            'utilization': round(utilization, 2),
            'available_space': bin_obj.capacity - bin_obj.current_load,
            'pick_count': bin_obj.pick_count,
            'distance_from_dispatch': bin_obj.distance_from_dispatch
        })
    
    return sorted(report, key=lambda x: x['utilization'], reverse=True)


def get_stock_alerts():
    """Get products that need reordering"""
    products = Product.objects.filter(is_active=True)
    alerts = []
    
    for product in products:
        total_stock = Inventory.objects.filter(
            product=product
        ).aggregate(total=Sum("quantity"))["total"] or 0
        
        if total_stock <= product.re_order:
            alerts.append({
                'product_id': product.product_id,
                'product_name': product.product_name,
                'current_stock': total_stock,
                'reorder_level': product.re_order,
                'reorder_quantity': calculate_reorder_quantity(product, total_stock),
                'vendor': product.vendor.vendor_name if product.vendor else None
            })
    
    return sorted(alerts, key=lambda x: x['current_stock'])


def validate_putaway_plan(plan):
    """
    Validate putaway plan before execution.
    """
    if not plan:
        return False, "Plan is empty"
    
    for item in plan:
        if 'bin_id' not in item:
            return False, "Missing bin_id in plan item"
        
        if 'quantity' not in item:
            return False, "Missing quantity in plan item"
        
        if item['quantity'] <= 0:
            return False, f"Invalid quantity {item['quantity']} for bin {item['bin_id']}"
        
        try:
            bin_obj = Bin.objects.get(bin_id=item['bin_id'])
            available_space = bin_obj.capacity - bin_obj.current_load
            if item['quantity'] > available_space:
                return False, f"Bin {item['bin_id']} has only {available_space} space, but plan wants {item['quantity']}"
        except Bin.DoesNotExist:
            return False, f"Bin {item['bin_id']} not found"
    
    return True, "Plan valid"


def validate_pick_plan(plan):
    """
    Validate pick plan before execution.
    """
    if not plan:
        return False, "Plan is empty"
    
    for item in plan:
        if 'bin_id' not in item:
            return False, "Missing bin_id in plan item"
        
        if 'quantity' not in item:
            return False, "Missing quantity in plan item"
        
        if item['quantity'] <= 0:
            return False, f"Invalid quantity {item['quantity']} for bin {item['bin_id']}"
        
        try:
            bin_obj = Bin.objects.get(bin_id=item['bin_id'])
            inventory = Inventory.objects.filter(bin=bin_obj).first()
            if not inventory or inventory.quantity < item['quantity']:
                return False, f"Insufficient stock in bin {item['bin_id']}"
        except Bin.DoesNotExist:
            return False, f"Bin {item['bin_id']} not found"
    
    return True, "Plan valid"