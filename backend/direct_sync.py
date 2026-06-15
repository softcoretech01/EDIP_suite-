"""
Self-contained Qdrant sync — no MySQL connection required.
All schema info is baked in from the real DB (captured by check_all_tables.py).
"""
import sys
sys.path.insert(0, '.')

from app.vector_db.qdrant_service import QdrantService
from app.embeddings.metadata_embedder import MetadataEmbedder

qdrant = QdrantService()
embedder = MetadataEmbedder()

TENANT_ID = 1
CONNECTION_ID = 2

# Full schema: (database, table, columns_string, description)
SCHEMA = [
    # ── Sales_Masters ───────────────────────────────────────────────────────────
    ("Sales_Masters", "Invoice_Details",
     "id (int), invoice_id (int), item_id (int), name (varchar), ordered_qty (decimal), supplied_qty (decimal), pending_qty (decimal), unit_price (decimal)",
     "Stores line items for each Sales Invoice. Join to Invoice_Header on invoice_id. Keywords: invoice items, billed quantity, invoice line items."
    ),
    ("Sales_Masters", "Invoice_Header",
     "invoice_id (int), so_id (int), cpo_ref (varchar), customer_name (varchar), amount (decimal), tax_amount (decimal), tax_type (varchar), total (decimal), created_at (datetime), updated_at (datetime)",
     "Stores all Sales Invoices. IMPORTANT: Use column 'total' (NOT grand_total) for invoice value. "
     "Use created_at for date filtering. ORDER BY total DESC to find highest invoice. "
     "Keywords: invoice, billing, high value invoice, invoice count, invoice total, which invoice."
    ),
    ("Sales_Masters", "SalesOrder_Details",
     "so_details_id (int), So_number (varchar), item_id (int), name (varchar), ordered_qty (decimal), supplied_qty (decimal), pending_qty (decimal), unit_price (decimal)",
     "Stores line items for each Sales Order. Join to SalesOrder_Header on So_number. "
     "Keywords: items ordered, quantities, ordered qty, pending qty, sales items."
    ),
    ("Sales_Masters", "SalesOrder_Header",
     "id (int), So_number (varchar), customer_name (varchar), date (date), delivery_schedule (varchar), invoice_generated (tinyint), created_at (datetime), updated_at (datetime)",
     "Stores all Sales Orders (SO). Use created_at for time filtering. Join to SalesOrder_Details on So_number. "
     "Keywords: sales order, SO, customer order, how many orders, total orders, sales this month."
    ),
    # ── Purchase_Masters ────────────────────────────────────────────────────────
    ("Purchase_Masters", "grn_Details",
     "grn_item_id (int), grn_id (int), item_id (int), po_qty (decimal), received_qty (decimal), batch_lot_number (varchar), mfg_date (date), expiry_date (date), created_at (datetime)",
     "Stores line items for each GRN. Join to grn_Header on grn_id. Use received_qty for quantity received. "
     "Keywords: received quantity, GRN items, received items."
    ),
    ("Purchase_Masters", "grn_Header",
     "grn_id (int), grn_number (varchar), po_id (int), supplier_id (int), grn_date (date), created_at (datetime), updated_at (datetime)",
     "Stores Goods Receipt Notes (GRN) — records of items physically received from suppliers. "
     "Use grn_date for date filtering. Total GRN = COUNT(grn_id). "
     "Keywords: GRN, goods received, total GRN, stock receipt, received items."
    ),
    ("Purchase_Masters", "import_landed_costs_Details",
     "detail_id (int), import_landed_cost_id (int), item_id (int), qty (decimal), fob_val_lcy (decimal), allocated_overhead (decimal), total_landed_cost (decimal), landed_unit_cost (decimal)",
     "Line items for import landed costs. Keywords: landed cost items, freight per item."
    ),
    ("Purchase_Masters", "import_landed_costs_Header",
     "import_landed_cost_id (int), import_po_id (int), duty_percent (decimal), cess_percent (decimal), gst_percent (decimal), include_gst (tinyint), sea_freight (decimal), road_freight (decimal), local_transport (decimal), liner_charges (decimal), insurance_cost (decimal), handling_charges (decimal), packing_charges (decimal), aging_charges (decimal), total_customs_duty (decimal), total_freight (decimal), total_port_charges (decimal), total_overhead (decimal), total_landed_cost (decimal), created_at (datetime), updated_at (datetime), is_posted (tinyint)",
     "Stores landed cost records for imported goods (duties, sea freight, insurance). "
     "Keywords: landed cost, import cost, freight cost, customs duty."
    ),
    ("Purchase_Masters", "import_purchase_orders_Details",
     "detail_id (int), import_po_id (int), item_id (int), currency_id (int), qty (decimal), fcy_unit_price (decimal), total_fcy (decimal)",
     "Line items for Import Purchase Orders. Keywords: import items, imported quantity."
    ),
    ("Purchase_Masters", "import_purchase_orders_Header",
     "import_po_id (int), import_po_number (varchar), supplier_id (int), po_date (date), currency_id (int), exchange_rate (decimal), payment_terms (varchar), total_fcy (decimal), total_lcy (decimal), status (varchar), created_at (datetime), updated_at (datetime)",
     "Stores Import Purchase Orders — POs for imported goods. "
     "Keywords: import PO, import purchase, import order."
    ),
    ("Purchase_Masters", "inventory_batches",
     "batch_id (int), batch_no (varchar), item_id (int), current_qty (decimal), mfg_date (date), expiry_date (date), landed_unit_cost (decimal), final_selling_price (decimal), margin_percent (decimal), status (varchar), source_type (varchar), po_reference (varchar), grn_reference (varchar), IPO_reference (varchar), created_at (datetime), updated_at (datetime), is_posted (tinyint), inward_qty (decimal), outward_qty (decimal), damaged_qty (decimal), damage_remarks (varchar)",
     "Stores inventory stock batches showing current stock levels. Use current_qty for stock level. "
     "Keywords: stock, inventory, batch, current stock, warehouse stock, stock level."
    ),
    ("Purchase_Masters", "local_landed_cost_Details",
     "landed_cost_item_id (int), landed_cost_id (int), item_id (int), qty (decimal), unit_price (decimal), val_lcy (decimal), allocated_overhead (decimal), total_landed_cost (decimal), landed_unit_cost (decimal), created_at (datetime)",
     "Line items for local landed costs. Keywords: local cost items."
    ),
    ("Purchase_Masters", "local_landed_cost_Header",
     "landed_cost_id (int), grn_id (int), insurance_charges (decimal), handling_charges (decimal), packing_charges (decimal), aging_charges (decimal), total_lcy (decimal), total_overhead (decimal), total_landed_cost (decimal), created_at (datetime), updated_at (datetime), is_posted (tinyint)",
     "Stores landed cost records for locally purchased goods. "
     "Keywords: local landed cost, freight, additional charges."
    ),
    ("Purchase_Masters", "purchase_order_Details",
     "po_item_id (int), po_id (int), item_id (int), quantity (decimal), uom (varchar), unit_price (decimal), tax_rate (decimal), line_total (decimal), created_at (datetime)",
     "Stores line items for Purchase Orders. Join to purchase_orders_Header on po_id. "
     "Keywords: purchased items, order quantity, PO line items."
    ),
    ("Purchase_Masters", "purchase_order_delivery_schedules",
     "schedule_id (int), po_id (int), expected_delivery_date (date), target_quantity (decimal), created_at (datetime)",
     "Stores delivery schedules for Purchase Orders. "
     "Keywords: delivery schedule, expected delivery, PO delivery date."
    ),
    ("Purchase_Masters", "purchase_orders_Header",
     "po_id (int), po_number (varchar), pr_id (int), supplier_id (int), po_date (date), payment_terms (varchar), sub_total (decimal), tax_total (decimal), grand_total (decimal), created_at (datetime), updated_at (datetime)",
     "Stores all Purchase Orders (PO). Use po_date for date filtering. Use grand_total for total amount. "
     "Keywords: purchase order, PO, procurement, vendor order, total purchase."
    ),
    ("Purchase_Masters", "purchase_requisition_Details",
     "pr_id (int), item_id (int), requested_quantity (decimal), uom (varchar), reason_for_request (varchar), created_at (datetime), unit_price (decimal), total_price (decimal)",
     "Stores the line items for Purchase Requisitions. Join to purchase_requisitions_Header on pr_id. "
     "Keywords: PR items, requisition items, requested quantity, items in PR."
    ),
    ("Purchase_Masters", "purchase_requisitions_Header",
     "pr_id (int), pr_number (varchar), pr_date (date), required_by_date (date), department (varchar), requested_by (varchar), notes (text), created_at (datetime), updated_at (datetime), priority (varchar)",
     "Stores Purchase Requisitions (PR). Use pr_number to look up a specific PR (e.g. PR-001). "
     "Keywords: PR, purchase requisition, PR-001, PR number."
    ),
    ("Purchase_Masters", "purchase_return_Details",
     "return_item_id (int), return_id (int), item_id (int), inwarded_qty (decimal), return_qty (decimal), return_reason (varchar), created_at (datetime)",
     "Line items for Purchase Returns. Keywords: returned items, return quantity."
    ),
    ("Purchase_Masters", "purchase_return_Header",
     "return_id (int), return_number (varchar), grn_id (int), supplier_id (int), return_date (date), debit_note_status (varchar), refund_total (decimal), created_at (datetime), updated_at (datetime)",
     "Stores Purchase Returns — items returned to suppliers. "
     "Keywords: purchase return, debit note, return to supplier."
    ),
    # ── masters ─────────────────────────────────────────────────────────────────
    ("masters", "currencies",
     "id (int), code (varchar), name (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Currency master. Keywords: currency, exchange rate, foreign currency."
    ),
    ("masters", "customer_types",
     "id (int), name (varchar), label (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Customer type categories. Keywords: customer type, client type."
    ),
    ("masters", "customers",
     "id (int), name (varchar), email (varchar), phone (varchar), customer_type_id (int), active (tinyint), billingAddress (text), shippingAddress (text), gstDetails (text), creditLimit (decimal), payment_term_id (int), price_category_id (int), contactPersons (text), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar), sales_person_id (int)",
     "Master list of all customers/clients. Real columns: id, name, email, phone, creditLimit, active. "
     "Keywords: customer, client, buyer, all customers, customer list, pending payments."
    ),
    ("masters", "documents",
     "id (int), name (varchar), category (varchar), uploaded_by (varchar), upload_date (datetime), size (int), version (varchar), linked_transaction (varchar), file_path (varchar), history (text)",
     "Stores document records. Keywords: document, attachment, file."
    ),
    ("masters", "gst_rates",
     "id (int), rate (decimal), name (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "GST tax rates. Keywords: GST, tax rate, tax percentage."
    ),
    ("masters", "item_categories",
     "id (int), name (varchar), groupId (int), updatedBy (varchar), updatedDate (datetime), modifiedBy (varchar), modifiedDate (datetime)",
     "Item category master. Keywords: item category, product category."
    ),
    ("masters", "item_groups",
     "id (int), name (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Item group master. Keywords: item group, product group."
    ),
    ("masters", "items",
     "id (int), name (varchar), group_id (int), category_id (int), brand (varchar), model (varchar), size (varchar), color (varchar), uom_id (int), hsnCode (varchar), gst_percent_id (int), minStock (decimal), reorderLevel (decimal), batchApplicable (tinyint), serialApplicable (tinyint), isImported (tinyint), active (tinyint), standardPrice (decimal), buildersPrice (decimal), dealersPrice (decimal), contractorsPrice (decimal), houseOwnersPrice (decimal), image (varchar), updatedBy (varchar), updatedDate (datetime), modifiedBy (varchar), modifiedDate (datetime)",
     "Master list of all inventory items/products. Join to any Details table using item_id = items.id. "
     "Use name for item name, standardPrice for price, reorderLevel for reorder. "
     "Keywords: item, product, inventory item, all items, list items, item name."
    ),
    ("masters", "payment_terms",
     "id (int), name (varchar), label (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Payment terms master. Keywords: payment terms, payment days, credit period."
    ),
    ("masters", "price_categories",
     "id (int), name (varchar), label (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Price category master. Keywords: price category, pricing tier."
    ),
    ("masters", "role_permissions",
     "role_name (varchar), permissions (text)",
     "User role permissions. Keywords: role, permission, access control."
    ),
    ("masters", "supplier_types",
     "id (int), name (varchar), label (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Supplier type categories. Keywords: supplier type, vendor type."
    ),
    ("masters", "suppliers",
     "id (int), name (varchar), email (varchar), phone (varchar), type (varchar), currency (varchar), leadTime (int), active (tinyint), taxDetails (text), paymentTerms (text), importDetails (text), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Master list of all suppliers/vendors. Real columns: id, name, email, phone, type, currency, leadTime, active. "
     "Keywords: supplier, vendor, vendor list, all suppliers, supplier name, which supplier."
    ),
    ("masters", "tax_registration_types",
     "id (int), name (varchar), label (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Tax registration types. Keywords: tax registration, GST registration."
    ),
    ("masters", "uoms",
     "id (int), name (varchar), updatedBy (varchar), updatedDate (datetime), modifiedDate (datetime), modifiedBy (varchar)",
     "Units of Measurement master. Keywords: UOM, unit of measure, unit."
    ),
    ("masters", "users",
     "id (int), name (varchar), role (varchar), email (varchar), department (varchar), status (varchar), monthly_target (decimal)",
     "ERP system users/staff. Keywords: user, staff, employee, sales person, sales target."
    ),
]

count = 0
for (schema, table, columns_str, description) in SCHEMA:
    full_name = f"{schema}.{table}"
    full_text = f"Table {full_name}\nDescription: {description}\nColumns: {columns_str}"
    vector = embedder.embed_text(full_text)
    qdrant.upsert_table_metadata(
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        table_name=full_name,
        description=description,
        columns=columns_str,
        vector=vector
    )
    count += 1
    print(f"[OK] {full_name}")

print(f"\nDone! {count} tables synced to Qdrant.")
