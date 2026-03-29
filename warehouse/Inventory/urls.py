from django.urls import path
from .views import *

urlpatterns = [
    # ================= INBOUND =================
    path("inbound/create/", InboundCreateView.as_view(), name="inbound-create"),
    path("inbound/<str:inbound_id>/putaway-plan/", GeneratePutawayPlanView.as_view(), name="putaway-plan"),
    path("inbound/<str:inbound_id>/confirm-putaway/", ConfirmPutawayView.as_view(), name="confirm-putaway"),
    
    # ================= OUTBOUND =================
    path("outbound/create/", OutboundCreateView.as_view(), name="outbound-create"),
    path("outbound/<str:outbound_id>/pick-plan/", GeneratePickPlanView.as_view(), name="pick-plan"),
    path("outbound/<str:outbound_id>/confirm-pick/", ConfirmPickView.as_view(), name="confirm-pick"),
    path("outbound/pick/<str:product_id>/", OptimizedOutboundView.as_view(), name="optimized-outbound"),
    
    # ================= ZONES =================
    path("zones/", ListZoneView.as_view(), name="zone-list"),
    path("zones/create/", CreateZoneView.as_view(), name="zone-create"),
    path("zones/<str:zone_id>/", GetZoneView.as_view(), name="zone-detail"),
    path("zones/<str:zone_id>/update/", UpdateZoneView.as_view(), name="zone-update"),
    path("zones/<str:zone_id>/delete/", DeleteZoneView.as_view(), name="zone-delete"),
    
    # ================= RACKS =================
    path("racks/", ListRackView.as_view(), name="rack-list"),
    path("racks/create/", CreateRackView.as_view(), name="rack-create"),
    path("racks/<str:rack_id>/", GetRackView.as_view(), name="rack-detail"),
    path("racks/<str:rack_id>/update/", UpdateRackView.as_view(), name="rack-update"),
    path("racks/<str:rack_id>/delete/", DeleteRackView.as_view(), name="rack-delete"),
    
    # ================= SHELVES =================
    path("shelves/", ListShelfView.as_view(), name="shelf-list"),
    path("shelves/create/", CreateShelfView.as_view(), name="shelf-create"),
    path("shelves/<str:shelf_id>/", GetShelfView.as_view(), name="shelf-detail"),
    path("shelves/<str:shelf_id>/update/", UpdateShelfView.as_view(), name="shelf-update"),
    path("shelves/<str:shelf_id>/delete/", DeleteShelfView.as_view(), name="shelf-delete"),
    
    # ================= BINS =================
    path("bins/", ListBinView.as_view(), name="bin-list"),
    path("bins/available/", ListAvailableBinsView.as_view(), name="bin-available"),
    path("bins/create/", CreateBinView.as_view(), name="bin-create"),
    path("bins/<str:bin_id>/", GetBinView.as_view(), name="bin-detail"),
    path("bins/<str:bin_id>/update/", UpdateBinView.as_view(), name="bin-update"),
    path("bins/<str:bin_id>/delete/", DeleteBinView.as_view(), name="bin-delete"),
    
    # ================= INVENTORY =================
    path("inventory/", ListInventoryView.as_view(), name="inventory-list"),
    path("inventory/create/", CreateInventoryView.as_view(), name="inventory-create"),
    path("inventory/<str:inventory_id>/", GetInventoryView.as_view(), name="inventory-detail"),
    path("inventory/<str:inventory_id>/update/", UpdateInventoryView.as_view(), name="inventory-update"),
    path("inventory/<str:inventory_id>/delete/", DeleteInventoryView.as_view(), name="inventory-delete"),
    path("inventory/add-stock/<str:product_id>/", AddStockByProductView.as_view(), name="add-stock"),
    path("inventory/remove-stock/<str:product_id>/", RemoveStockByProductView.as_view(), name="remove-stock"),
    path("inventory/product-stock/<str:product_id>/", ProductStockView.as_view(), name="product-stock"),
    
    # ================= STOCK MOVEMENTS =================
    path("stock-movements/", StockMovementListView.as_view(), name="stock-movement-list"),
    path("stock-movements/product/<str:product_id>/", StockMovementByProductView.as_view(), name="stock-movement-by-product"),
    
    # ================= PURCHASE REQUESTS =================
    path("purchase-requests/", PurchaseRequestListView.as_view(), name="pr-list"),
    path("purchase-requests/<str:pr_id>/manager-approve/", ManagerApprovePR.as_view(), name="pr-manager-approve"),
    path("purchase-requests/<str:pr_id>/finance-approve/", FinanceApprovePR.as_view(), name="pr-finance-approve"),
    
    # ================= PURCHASE ORDERS =================
    path("purchase-orders/", PurchaseOrderListView.as_view(), name="po-list"),
    
    # ================= ASN (Advanced Shipping Notice) =================
    path("asn/", ASNListView.as_view(), name="asn-list"),
    path("asn/create/", ASNCreateView.as_view(), name="asn-create"),
    path("asn/<str:pk>/", ASNDetailView.as_view(), name="asn-detail"),
    
    # ================= ASN ITEMS =================
    path("asn-items/", ASNItemListView.as_view(), name="asn-item-list"),
    path("asn-items/create/", CreateASNItemView.as_view(), name="asn-item-create"),
    path("asn-items/<str:pk>/", ASNItemDetailView.as_view(), name="asn-item-detail"),
    
    # ================= GRN (Goods Receipt Note) =================
    # -- Supervisor endpoints --
    path("grn/supervisor/create/", SupervisorCreateGRN.as_view(), name="grn-supervisor-create"),
    path("grn/supervisor/add-items/", SupervisorAddGRNItems.as_view(), name="grn-supervisor-add-items"),
    path("grn/supervisor/my-grns/", SupervisorGRNListView.as_view(), name="grn-supervisor-list"),
    
    # -- QC endpoints --
    path("grn/qc/pending/", GRNQCPendingListView.as_view(), name="grn-qc-pending"),
    path("grn/qc/approve/<str:grn_id>/", QCApproveGRN.as_view(), name="grn-qc-approve"),
    path("grn-item/<str:pk>/qc/", QCUpdateGRNItem.as_view(), name="grn-item-qc-update"),
    
    # -- General GRN endpoints --
    path("grn/", GRNListView.as_view(), name="grn-list"),
    path("grn/create/", GRNCreateView.as_view(), name="grn-create"),
    path("grn/<str:pk>/", GRNDetailView.as_view(), name="grn-detail"),
    path("grn/<str:grn_id>/items/", GRNItemsByGRNView.as_view(), name="grn-items"),
    path("grn/<str:grn_id>/summary/", GRNSummaryView.as_view(), name="grn-summary"),
    
    # ================= GRN ITEMS =================
    path("grn-items/", GRNItemListView.as_view(), name="grn-item-list"),
    path("grn-items/create/", GRNItemCreateView.as_view(), name="grn-item-create"),
    path("grn-items/<str:pk>/", GRNItemDetailView.as_view(), name="grn-item-detail"),
]

# Optional: API versioning (uncomment if needed)
# urlpatterns = [
#     path("api/v1/", include(urlpatterns_v1)),
# ]